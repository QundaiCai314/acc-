"""Deterministic geometry and graph queries over explicitly approved snapshots."""
import heapq
import math
import re
import sqlite3
from collections import deque
from datetime import datetime, timedelta
from itertools import product
from uuid import UUID

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request

from .access import principal
from .evidence_time import capture_bounds
from .geometry_models import (
    ArtifactReview, ReasonQuery, Registration, RelationSet, RoadNetwork, RouteQuery, TransformQuery,
)
from .spatial import distance_m, get
from .spatial_models import Dataset, NaturalQuestion, Retraction
from . import vision


router = APIRouter(prefix='/spatial', tags=['spatial-geometry'])
ARTIFACTS = {'road_network': RoadNetwork, 'registration': Registration, 'relation_set': RelationSet}


def dataset(store, identifier):
    return Dataset.model_validate(get(store, 'spatial_dataset', identifier)['snapshot'])


def artifact(store, identifier, kind=None):
    record = get(store, 'spatial_artifact', identifier)
    if kind and record['artifact_type'] != kind:
        raise HTTPException(422, f'Expected {kind}')
    return record


def active_artifact(store, identifier, dataset_id, kind, as_of):
    record = artifact(store, identifier, kind)
    if record['dataset_id'] != str(dataset_id):
        raise HTTPException(422, 'Artifact belongs to another dataset')
    review = store.decision(record['id'])
    withdrawn = {r['artifact_id'] for r in store.list_records('artifact_retraction', str(dataset_id))}
    if review is None or review['action'] != 'approve' or record['id'] in withdrawn:
        raise HTTPException(409, 'Artifact is not currently approved')
    snapshot = record['snapshot']
    if not datetime.fromisoformat(snapshot['valid_from']) <= as_of <= datetime.fromisoformat(snapshot['valid_until']):
        raise HTTPException(409, 'Artifact is outside its validity interval')
    return record, review


def validate_references(store, ds, dataset_id, payload):
    entities = {e.id: e for e in ds.entities}
    referenced, annotation_ids = set(), []
    if isinstance(payload, RoadNetwork):
        for edge in payload.edges:
            referenced.update((edge.source, edge.target))
            annotation_ids.extend(edge.annotation_ids)
            a, b = entities.get(edge.source), entities.get(edge.target)
            if a and b and a.coordinates and b.coordinates and edge.length_m + 0.1 < distance_m(a.coordinates, b.coordinates):
                raise HTTPException(422, 'Road length is shorter than straight-line distance')
    elif isinstance(payload, RelationSet):
        for relation in payload.relations:
            referenced.update((relation.subject, relation.object))
            annotation_ids.extend(relation.annotation_ids)
    else:
        referenced.update(o.entity_id for o in payload.objects)
    if referenced - entities.keys():
        raise HTTPException(422, 'Unknown map entity')
    for identifier in annotation_ids:
        annotation = get(store, 'annotation', identifier)
        if annotation['dataset_id'] != str(dataset_id):
            raise HTTPException(422, 'Evidence belongs to another dataset')


def register(payload: Registration):
    source = np.array([p.scene for p in payload.control_points]) * payload.scene_unit_m
    target = np.array([p.target for p in payload.control_points])
    x, y = source - source.mean(axis=0), target - target.mean(axis=0)
    # Three non-collinear points determine a proper 3D rigid transform; no reflection is allowed.
    for points in (x, y):
        singular = np.linalg.svd(points, compute_uv=False)
        if singular[0] < 1e-8 or singular[1] / singular[0] < 1e-6:
            raise HTTPException(422, 'Control points are collinear or ill-conditioned')
    u, singular, vt = np.linalg.svd(x.T @ y)
    sign = np.ones(3)
    sign[-1] = 1 if np.linalg.det(vt.T @ u.T) > 0 else -1
    rotation = vt.T @ np.diag(sign) @ u.T
    scale = float(np.sum(singular * sign) / np.sum(x*x)) if payload.solve_scale else 1.0
    if not 0.0001 <= scale <= 10000:
        raise HTTPException(422, 'Estimated scale is outside supported range')
    translation = target.mean(axis=0) - scale * rotation @ source.mean(axis=0)
    matrix = np.eye(4)
    matrix[:3, :3] = scale * rotation * payload.scene_unit_m
    matrix[:3, 3] = translation
    fit_errors = np.linalg.norm(source @ (scale * rotation).T + translation - target, axis=1)
    check_source = np.array([p.scene for p in payload.check_points])
    check_target = np.array([p.target for p in payload.check_points])
    check_errors = np.linalg.norm(check_source @ matrix[:3, :3].T + translation - check_target, axis=1)
    fit_rmse, check_rmse = (float(np.sqrt(np.mean(e*e))) for e in (fit_errors, check_errors))
    if max(fit_rmse, check_rmse) > payload.max_rmse_m or max(*fit_errors, *check_errors) > payload.max_error_m:
        raise HTTPException(422, 'Registration exceeds fit or independent-check error thresholds')
    objects = {}
    for obj in payload.objects:
        corners = np.array(list(product(*zip(obj.min_corner, obj.max_corner))))
        aligned = corners @ matrix[:3, :3].T + translation
        if np.any(np.linalg.norm(aligned, axis=1) > 10000):
            raise HTTPException(422, 'Aligned scene objects must stay within 10 km of origin')
        suffix = 'enu_m' if payload.target_frame == 'enu' else 'local_m'
        objects[obj.entity_id] = {f'corners_{suffix}': aligned.tolist(), f'min_{suffix}': aligned.min(axis=0).tolist(),
                                  f'max_{suffix}': aligned.max(axis=0).tolist()}
    return {f'matrix_scene_to_{payload.target_frame}': matrix.tolist(), 'estimated_scale': scale,
            'fit_rmse_m': fit_rmse, 'check_rmse_m': check_rmse,
            'fit_residuals_m': fit_errors.tolist(), 'check_residuals_m': check_errors.tolist(),
            'objects': objects, 'target_frame': payload.target_frame,
            'axis_order': ['east', 'north', 'up'] if payload.target_frame == 'enu' else ['x', 'y', 'z'],
            'max_control_error_m': float(max(*fit_errors, *check_errors))}


def enu_to_wgs84(points, origin, altitude):
    """WGS84 ellipsoid ENU -> ECEF -> geodetic, including polar origins."""
    lat, lon = math.radians(origin['latitude']), math.radians(origin['longitude'])
    a, e2 = 6378137.0, 6.69437999014e-3
    n = a / math.sqrt(1 - e2 * math.sin(lat)**2)
    anchor = np.array([(n+altitude)*math.cos(lat)*math.cos(lon),
                       (n+altitude)*math.cos(lat)*math.sin(lon), (n*(1-e2)+altitude)*math.sin(lat)])
    rotation = np.array([[-math.sin(lon), -math.sin(lat)*math.cos(lon), math.cos(lat)*math.cos(lon)],
                         [math.cos(lon), -math.sin(lat)*math.sin(lon), math.cos(lat)*math.sin(lon)],
                         [0, math.cos(lat), math.sin(lat)]])
    output = []
    for x, y, z in np.asarray(points) @ rotation.T + anchor:
        p = math.hypot(x, y)
        phi = math.atan2(z, p*(1-e2))
        for _ in range(12):
            normal = a / math.sqrt(1-e2*math.sin(phi)**2)
            phi = math.atan2(z + e2*normal*math.sin(phi), p)
        normal = a / math.sqrt(1-e2*math.sin(phi)**2)
        height = p/math.cos(phi)-normal if p > 1e-5 else abs(z)-a*math.sqrt(1-e2)
        output.append({'latitude': math.degrees(phi), 'longitude': math.degrees(math.atan2(y, x)),
                       'altitude_m': height})
    return output


def create_artifact(store, dataset_id, kind, payload):
    ds = dataset(store, dataset_id)
    validate_references(store, ds, dataset_id, payload)
    computed = register(payload) if kind == 'registration' else None
    return store.save('spatial_artifact', {'dataset_id': str(dataset_id), 'artifact_type': kind,
                                         'snapshot': payload.model_dump(mode='json'), 'computed': computed})


@router.post('/datasets/{dataset_id}/networks', status_code=201)
def add_network(dataset_id: UUID, payload: RoadNetwork, request: Request):
    return create_artifact(request.app.state.store, dataset_id, 'road_network', payload)


@router.post('/datasets/{dataset_id}/registrations', status_code=201)
def add_registration(dataset_id: UUID, payload: Registration, request: Request):
    return create_artifact(request.app.state.store, dataset_id, 'registration', payload)


@router.post('/datasets/{dataset_id}/relations', status_code=201)
def add_relations(dataset_id: UUID, payload: RelationSet, request: Request):
    return create_artifact(request.app.state.store, dataset_id, 'relation_set', payload)


@router.get('/datasets/{dataset_id}/artifacts')
def list_artifacts(dataset_id: UUID, request: Request, limit: int = Query(100, ge=1, le=200),
                   offset: int = Query(0, ge=0)):
    store = request.app.state.store
    dataset(store, dataset_id)
    records = store.list_records('spatial_artifact', str(dataset_id), limit + 1, offset)
    withdrawn = {r['artifact_id'] for r in store.list_records('artifact_retraction', str(dataset_id))}
    result = []
    for record in records[:limit]:
        review = store.decision(record['id'])
        status = 'pending_review' if review is None else ('approved' if review['action'] == 'approve' else 'rejected')
        result.append({**record, 'review': review, 'status': 'withdrawn' if record['id'] in withdrawn else status})
    return {'artifacts': result, 'next_offset': offset+limit if len(records) > limit else None}


@router.get('/artifacts/{artifact_id}')
def read_artifact(artifact_id: UUID, request: Request):
    store = request.app.state.store
    record = artifact(store, artifact_id)
    withdrawals = [r for r in store.list_records('artifact_retraction', record['dataset_id']) if r['artifact_id'] == str(artifact_id)]
    return {**record, 'review': store.decision(str(artifact_id)), 'withdrawals': withdrawals}


@router.post('/artifacts/{artifact_id}/review', status_code=201)
def review_artifact(artifact_id: UUID, payload: ArtifactReview, request: Request):
    store = request.app.state.store
    record = artifact(store, artifact_id)
    parsed = ARTIFACTS[record['artifact_type']].model_validate(record['snapshot'])
    validate_references(store, dataset(store, record['dataset_id']), record['dataset_id'], parsed)
    try:
        return store.decide(str(artifact_id), {**payload.model_dump(), 'reviewer': principal.get().user_id})
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, 'Artifact already reviewed; submit a new snapshot to revise it') from exc


@router.post('/artifacts/{artifact_id}/withdraw', status_code=201)
def withdraw_artifact(artifact_id: UUID, payload: Retraction, request: Request):
    store = request.app.state.store
    record = artifact(store, artifact_id)
    review = store.decision(str(artifact_id))
    if review is None or review['action'] != 'approve':
        raise HTTPException(409, 'Only approved artifacts can be withdrawn')
    try:
        return store.save('artifact_retraction', {**payload.model_dump(), 'artifact_id': str(artifact_id),
                                                'dataset_id': record['dataset_id']})
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, 'Artifact already withdrawn') from exc


def evidence_records(store, dataset_id, as_of, max_age_hours=None):
    withdrawn = {r['annotation_id'] for r in store.list_records('annotation_retraction', str(dataset_id))}
    result = {}
    for record, review in store.reviewed_records(str(dataset_id)):
        if record['id'] in withdrawn or review['action'] != 'approve':
            continue
        image = get(store, 'spatial_image', record['image_id'], metadata=True)
        earliest, latest = capture_bounds(image)
        if latest > as_of or (max_age_hours is not None and earliest < as_of - timedelta(hours=max_age_hours)):
            continue
        result[record['id']] = {'annotation_id': record['id'], 'image_id': image['id'],
                                'image_url': f'/spatial/images/{image["id"]}/content',
                                'captured_at': image.get('captured_at'), 'captured_on': image.get('captured_on'),
                                'source': image['source'],
                                'evidence_basis': image['evidence_basis'], 'annotation': review['approved_annotation'],
                                'camera_pose': image.get('camera_pose'),
                                'reviewer': review['reviewer'], 'reviewed_at': review['created_at']}
    return result


def shortest_path(network, start, end, mode, avoided, evidence, basis='reviewed_status'):
    graph, excluded = {}, []
    for edge in network['snapshot']['edges']:
        reason = None
        if edge['status'] == 'blocked' or (edge['status'] == 'unknown' and basis != 'mapped_topology'):
            reason = edge['status']
        elif mode not in edge['modes']:
            reason = 'mode_not_allowed'
        elif edge['id'] in avoided:
            reason = 'requested_avoidance'
        elif any(identifier not in evidence for identifier in edge['annotation_ids']):
            reason = 'supporting_evidence_unavailable'
        elif any(evidence[identifier]['annotation']['observation'] == 'obstacle_visible' for identifier in edge['annotation_ids']):
            reason = 'reviewed_obstacle_evidence'
        if reason:
            excluded.append({'edge_id': edge['id'], 'reason': reason})
            continue
        graph.setdefault(edge['source'], []).append((edge['target'], edge))
        if edge['bidirectional']:
            graph.setdefault(edge['target'], []).append((edge['source'], edge))
    queue, distances, previous = [(0.0, start)], {start: 0.0}, {}
    while queue:
        distance, node = heapq.heappop(queue)
        if distance != distances[node]:
            continue
        if node == end:
            nodes, edges = [end], []
            while node != start:
                parent, edge = previous[node]
                nodes.append(parent)
                edges.append(edge)
                node = parent
            return {'status': 'reachable', 'distance_m': distance, 'entity_ids': nodes[::-1],
                    'edges': edges[::-1], 'excluded_edges': excluded}
        for target, edge in graph.get(node, ()):
            candidate = distance + edge['length_m']
            if candidate < distances.get(target, math.inf):
                distances[target] = candidate
                previous[target] = node, edge
                heapq.heappush(queue, (candidate, target))
    return {'status': 'unreachable', 'distance_m': None, 'entity_ids': [], 'edges': [], 'excluded_edges': excluded}


def artifact_citation(record, review):
    return {'artifact_id': record['id'], 'artifact_type': record['artifact_type'],
            'source_note': record['snapshot']['source_note'], 'reviewer': review['reviewer'],
            'reviewed_at': review['created_at'], 'valid_from': record['snapshot']['valid_from'],
            'valid_until': record['snapshot']['valid_until']}


@router.post('/datasets/{dataset_id}/route')
def route(dataset_id: UUID, payload: RouteQuery, request: Request):
    store = request.app.state.store
    ds = dataset(store, dataset_id)
    known = {e.id for e in ds.entities}
    if payload.start_entity_id not in known or payload.end_entity_id not in known:
        raise HTTPException(422, 'Unknown route endpoint')
    network, review = active_artifact(store, payload.network_id, dataset_id, 'road_network', payload.as_of)
    if payload.avoid_edge_ids - {e['id'] for e in network['snapshot']['edges']}:
        raise HTTPException(422, 'Unknown avoided edge')
    evidence = evidence_records(store, dataset_id, payload.as_of)
    result = shortest_path(network, payload.start_entity_id, payload.end_entity_id, payload.mode,
                           payload.avoid_edge_ids, evidence, payload.basis)
    ids = {identifier for edge in result['edges'] for identifier in edge['annotation_ids']}
    return {**result, 'basis': payload.basis,
            'unverified_edge_ids': [e['id'] for e in result['edges'] if e['status'] == 'unknown'],
            'dataset_id': str(dataset_id), 'coordinate_basis': ds.coordinate_basis,
            'query': payload.model_dump(mode='json'), 'network': artifact_citation(network, review),
            'citations': [evidence[i] for i in sorted(ids)],
            'limitations': ['仅表示审核路网快照中的连通性，不是现场通行安全保证',
                            ('仅地图拓扑：允许经过状态未知的地图道路，不表示已核实通行；明确封闭道路仍排除'
                             if payload.basis == 'mapped_topology' else '封闭和未知道路不参与通行状态查询'),
                            'as_of 不回放历史审核状态']}


@router.post('/registrations/{registration_id}/transform')
def transform(registration_id: UUID, payload: TransformQuery, request: Request):
    store = request.app.state.store
    record = artifact(store, registration_id, 'registration')
    record, review = active_artifact(store, registration_id, record['dataset_id'], 'registration', payload.as_of)
    frame = record['snapshot'].get('target_frame', 'enu')
    matrix = np.array(record['computed'][f'matrix_scene_to_{frame}'])
    points = np.array(payload.points) @ matrix[:3, :3].T + matrix[:3, 3]
    if np.any(np.linalg.norm(points, axis=1) > 10000):
        raise HTTPException(422, 'Transformed points exceed the 10 km local-frame limit')
    return {f'{frame}_m': points.tolist(), 'target_frame': frame,
            'coordinate_basis': dataset(store, record['dataset_id']).coordinate_basis,
            'wgs84': (enu_to_wgs84(points, record['snapshot']['origin'], record['snapshot']['origin_altitude_m'])
                      if frame == 'enu' else None),
            'registration': artifact_citation(record, review),
            'check_rmse_m': record['computed']['check_rmse_m'],
            'limitations': ['配准精度取决于输入控制点及检查点；转换结果不会自动覆盖地图坐标'] +
                            (['局部坐标轴方向未地理标定，不能生成 WGS84 位置或认定地理上下关系'] if frame == 'local' else [])}


def relation_path(relations, start, target, predicate, max_hops, evidence):
    graph = {}
    for relation in relations:
        if relation['predicate'] != predicate or any(i not in evidence for i in relation['annotation_ids']):
            continue
        graph.setdefault(relation['subject'], []).append((relation['object'], relation))
        if predicate == 'connects_to':
            graph.setdefault(relation['object'], []).append((relation['subject'], relation))
    queue, seen = deque([(start, [])]), {start}
    while queue:
        node, path = queue.popleft()
        if len(path) >= max_hops:
            continue
        for other, relation in graph.get(node, ()):
            if other == target:
                return path + [relation]
            # Blocking is directional and not transitive.
            if other not in seen and predicate != 'blocks':
                seen.add(other)
                queue.append((other, path + [relation]))
    return None


def omitted_conditions(question, query):
    """Conservative coverage guard for explicit supported terms, not a general language parser."""
    patterns = {'above': r'上方|上面|高于|\babove\b', 'below': r'下方|下面|低于|\bbelow\b',
                'reachable_from': r'可达|到达|reachable', 'part_of': r'属于|组成部分|part_of',
                'north_of': r'以北|北侧|北面|north_of', 'south_of': r'以南|南侧|南面|south_of',
                'east_of': r'以东|东侧|东面|east_of', 'west_of': r'以西|西侧|西面|west_of'}
    selected = {c.relation for c in query.all_of}
    missing = [name for name, pattern in patterns.items() if re.search(pattern, question, re.I) and name not in selected]
    distances = re.findall(r'(\d+(?:\.\d+)?)\s*(千米|公里|米|km\b|m\b)', question, re.I)
    for amount, unit in distances:
        distance = float(amount) * (1000 if unit.lower() in ('千米','公里','km') else 1)
        if not any(c.relation == 'near' and math.isclose(c.distance_m, distance) for c in query.all_of):
            missing.append('near')
    return sorted(set(missing))


@router.post('/datasets/{dataset_id}/reason')
def reason(dataset_id: UUID, payload: ReasonQuery, request: Request):
    store = request.app.state.store
    ds = dataset(store, dataset_id)
    entities = {e.id: e for e in ds.entities}
    if any(c.reference_entity_id not in entities for c in payload.all_of):
        raise HTTPException(422, 'Unknown reference entity')
    artifacts, citations = {}, []
    needed = {'relation_set': any(c.relation in ('inside', 'part_of', 'connects_to', 'blocks') for c in payload.all_of),
              'registration': any(c.relation in ('above', 'below') for c in payload.all_of),
              'road_network': any(c.relation == 'reachable_from' for c in payload.all_of)}
    ids = {'relation_set': payload.relation_set_id, 'registration': payload.registration_id, 'road_network': payload.network_id}
    for kind, required in needed.items():
        if required:
            if ids[kind] is None:
                raise HTTPException(422, f'{kind} ID required for these conditions')
            record, review = active_artifact(store, ids[kind], dataset_id, kind, payload.as_of)
            if kind == 'registration' and record['snapshot'].get('target_frame', 'enu') != 'enu':
                raise HTTPException(422, 'Geographic above/below reasoning requires an ENU registration')
            artifacts[kind] = record
            citations.append(artifact_citation(record, review))
    evidence = evidence_records(store, dataset_id, payload.as_of, payload.max_age_hours)
    matches, unknown = [], []
    for entity in ds.entities:
        if payload.kind is not None and entity.kind != payload.kind:
            continue
        proofs, missing, matched = [], False, True
        supporting_ids = set()
        for condition in payload.all_of:
            reference = entities[condition.reference_entity_id]
            predicate = condition.relation
            proof = None
            if entity.id == reference.id:
                matched = False
                break
            if predicate in ('near', 'north_of', 'south_of', 'east_of', 'west_of'):
                if entity.coordinates is None or reference.coordinates is None:
                    missing = True
                else:
                    distance = distance_m(entity.coordinates, reference.coordinates)
                    delta_lat = entity.coordinates.latitude - reference.coordinates.latitude
                    delta_lon = (entity.coordinates.longitude - reference.coordinates.longitude + 180) % 360 - 180
                    holds = {'near': distance <= (condition.distance_m or 0), 'north_of': delta_lat > 1e-8,
                             'south_of': delta_lat < -1e-8, 'east_of': 1e-8 < delta_lon < 180-1e-8,
                             'west_of': -180+1e-8 < delta_lon < -1e-8}[predicate]
                    if holds:
                        proof = {'rule': predicate, 'distance_m': distance, 'map_dataset_id': str(dataset_id)}
            elif predicate in ('above', 'below'):
                registration = artifacts['registration']
                objects = registration['computed']['objects']
                a, b = objects.get(entity.id), objects.get(reference.id)
                if a is None or b is None:
                    missing = True
                else:
                    # Use disjoint vertical extents, not overlapping rotated bounding-box centers.
                    margin = registration['snapshot']['max_error_m'] * 2
                    gap = (a['min_enu_m'][2] - b['max_enu_m'][2] if predicate == 'above'
                           else b['min_enu_m'][2] - a['max_enu_m'][2])
                    if gap > margin:
                        proof = {'rule': predicate, 'vertical_gap_m': gap, 'error_margin_m': margin,
                                 'artifact_id': registration['id']}
            elif predicate == 'reachable_from':
                network = artifacts['road_network']
                path = shortest_path(network, reference.id, entity.id, payload.mode, set(), evidence)
                if path['status'] == 'reachable':
                    proof = {'rule': predicate, 'artifact_id': network['id'], 'path': path}
                    supporting_ids.update(i for edge in path['edges'] for i in edge['annotation_ids'])
            else:
                relations = artifacts['relation_set']
                path = relation_path(relations['snapshot']['relations'], entity.id, reference.id,
                                     predicate, payload.max_hops, evidence)
                if path:
                    proof = {'rule': predicate, 'artifact_id': relations['id'], 'path': path}
                    supporting_ids.update(i for relation in path for i in relation['annotation_ids'])
            if proof is None:
                matched = False
                break
            proofs.append({'reference_entity_id': reference.id, **proof})
        observations = [e for e in evidence.values() if e['annotation']['entity_id'] == entity.id
                        and e['annotation']['observation'] == payload.observation]
        if payload.observation is not None and not observations:
            matched = False
        if matched:
            supporting_ids.update(e['annotation_id'] for e in observations)
            matches.append({'entity_id': entity.id, 'entity_name': entity.name, 'proofs': proofs,
                            'image_citations': [evidence[i] for i in sorted(supporting_ids)]})
        elif missing:
            unknown.append(entity.id)
    return {'status': 'matches_found' if matches else 'insufficient_evidence', 'matches': matches,
            'dataset_id': str(dataset_id), 'coordinate_basis': ds.coordinate_basis,
            'query': payload.model_dump(mode='json'), 'artifact_citations': citations, 'unknown_entities': unknown,
            'limitations': ['仅执行 all_of 中明确请求的关系；未找到关系不等于关系不存在',
                            'inside、part_of、connects_to 仅对同一谓词做有界多跳；blocks 不传递',
                            '上下关系比较配准后的物体垂直范围，误差余量不代表统计置信区间',
                            '方向依据 WGS84 点位；可达性依赖审核路网，不表示安全通行']}


@router.post('/datasets/{dataset_id}/reason/ask')
def ask_relations(dataset_id: UUID, payload: NaturalQuestion, request: Request):
    store = request.app.state.store
    ds = dataset(store, dataset_id)
    withdrawn = {r['artifact_id'] for r in store.list_records('artifact_retraction', str(dataset_id))}
    catalog = []
    for record in store.list_records('spatial_artifact', str(dataset_id)):
        review = store.decision(record['id'])
        if review and review['action'] == 'approve' and record['id'] not in withdrawn:
            catalog.append({'id': record['id'], 'artifact_type': record['artifact_type'],
                            'source_note': record['snapshot']['source_note'],
                            'valid_from': record['snapshot']['valid_from'], 'valid_until': record['snapshot']['valid_until']})
    if len(catalog) > 100:
        raise HTTPException(422, 'Too many approved snapshots for automatic selection; use structured /reason')
    try:
        intent, audit = vision.interpret_relations(payload.question, ds, catalog)
    except vision.VisionUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except vision.VisionFailure as exc:
        raise HTTPException(502, str(exc)) from exc
    run = store.save('vision_run', {**audit, 'dataset_id': str(dataset_id), 'question': payload.question,
                                    'interpreted_query': intent.model_dump(mode='json')})
    if intent.query is None:
        return {'status': 'clarification_needed', 'answer': intent.clarification, 'run_id': run['id'], 'evidence': None}
    missing = omitted_conditions(payload.question, intent.query)
    if missing:
        return {'status': 'clarification_needed', 'run_id': run['id'], 'evidence': None,
                'answer': '问题中的部分条件未被完整解析，请拆开描述各项条件，或使用结构化 reason 接口。',
                'missing_conditions': missing, 'interpreted_query': intent.query.model_dump(mode='json')}
    try:
        evidence = reason(dataset_id, intent.query, request)
    except HTTPException as exc:
        if exc.status_code not in (409, 422):
            raise
        return {'status': 'clarification_needed', 'run_id': run['id'], 'evidence': None,
                'answer': '解析的条件或所需审核工件当前不可用，请核对工件 ID、审核状态及有效时间。',
                'query_error': exc.detail, 'interpreted_query': intent.query.model_dump(mode='json')}
    names = [m['entity_name'] for m in evidence['matches']]
    labels = {'near':'距离不超过', 'part_of':'属于', 'inside':'位于内部', 'above':'整体高于', 'below':'整体低于',
              'reachable_from':'可沿审核路网从该处到达', 'north_of':'位于北侧', 'south_of':'位于南侧',
              'east_of':'位于东侧', 'west_of':'位于西侧', 'connects_to':'存在连接关系', 'blocks':'存在阻挡关系'}
    entities = {e.id:e.name for e in ds.entities}
    conditions = [f'{entities[c.reference_entity_id]}：{labels[c.relation]}' +
                  (f' {c.distance_m:g} 米' if c.distance_m is not None else '') for c in intent.query.all_of]
    answer = '按以下解析条件查询：' + '；'.join(conditions) + '。'
    answer += '符合条件的对象：' + '、'.join(names) if names else '没有足够证据确认符合条件的对象。'
    if ds.coordinate_basis == 'exercise':
        answer = '【演练坐标】' + answer
    return {'status': 'answered', 'answer': answer, 'run_id': run['id'], 'interpreted_conditions': conditions, 'evidence': evidence}
