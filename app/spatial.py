import base64
import hashlib
import math
import re
import sqlite3
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from . import vision
from .access import attributed, team_mode
from .spatial_models import (
    Annotation, Dataset, ImageInput, ImportedProposal, NaturalAnswer, NaturalQuestion,
    QueryIntent, Retraction, Review, SpatialAnswer, SpatialQuery,
)


router = APIRouter(prefix='/spatial', tags=['spatial-rag'])


def get(store, kind, identifier, metadata=False):
    record = store.get(kind, str(identifier), metadata=metadata)
    if record is None:
        raise HTTPException(404, f'{kind} not found')
    return record


def validate_link(dataset: Dataset, annotation: Annotation, require_link=False):
    if annotation.entity_id is None:
        if require_link:
            raise HTTPException(422, 'Approval requires a confirmed map entity')
    elif annotation.entity_id not in {e.id for e in dataset.entities}:
        raise HTTPException(422, 'Unknown map entity in this dataset')


def distance_m(a, b):
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    dlat = lat2 - lat1
    dlon = math.radians(b.longitude - a.longitude)
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_008.8 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, value))))


@router.post('/datasets', status_code=201)
def create_dataset(payload: Dataset, request: Request):
    snapshot = payload.model_dump(mode='json')
    snapshot['curator'] = attributed({'curator': payload.curator})['curator']
    return request.app.state.store.save('spatial_dataset', {'snapshot': snapshot})


@router.get('/datasets/{dataset_id}')
def read_dataset(dataset_id: UUID, request: Request):
    return get(request.app.state.store, 'spatial_dataset', dataset_id)


@router.get('/datasets')
def list_datasets(request: Request, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    records = request.app.state.store.list_records('spatial_dataset', None, limit+1, offset)
    return {'datasets': records[:limit], 'next_offset': offset+limit if len(records) > limit else None}


@router.get('/datasets/{dataset_id}/images')
def list_images(dataset_id: UUID, request: Request, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    store = request.app.state.store
    get(store, 'spatial_dataset', dataset_id)
    records = store.list_records('spatial_image', str(dataset_id), limit+1, offset, metadata=True)
    return {'images': records[:limit], 'next_offset': offset+limit if len(records) > limit else None}


@router.post('/datasets/{dataset_id}/images', status_code=201)
def add_image(dataset_id: UUID, payload: ImageInput, request: Request):
    store = request.app.state.store
    get(store, 'spatial_dataset', dataset_id)
    data = base64.b64decode(payload.content_base64)
    record = store.save('spatial_image', {
        **payload.model_dump(mode='json'), 'dataset_id': str(dataset_id),
        'sha256': hashlib.sha256(data).hexdigest(),
    })
    return {k: v for k, v in record.items() if k != 'content_base64'}


@router.get('/images/{image_id}')
def read_image(image_id: UUID, request: Request):
    record = get(request.app.state.store, 'spatial_image', image_id, metadata=True)
    return {k: v for k, v in record.items() if k != 'content_base64'}


@router.get('/images/{image_id}/content')
def image_content(image_id: UUID, request: Request):
    image = get(request.app.state.store, 'spatial_image', image_id)
    return Response(base64.b64decode(image['content_base64']), media_type=image['mime_type'],
                    headers={'X-Content-Type-Options': 'nosniff'})


@router.post('/images/{image_id}/analyze', status_code=201)
def analyze_image(image_id: UUID, request: Request):
    store = request.app.state.store
    image = get(store, 'spatial_image', image_id)
    dataset = Dataset.model_validate(get(store, 'spatial_dataset', image['dataset_id'])['snapshot'])
    key = request.headers.get('Idempotency-Key')
    if team_mode.get() and not key:
        raise HTTPException(422, 'Team-mode image analysis requires Idempotency-Key')
    if key and not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', key):
        raise HTTPException(422, 'Idempotency-Key must be 1-128 ASCII letters, digits, hyphens or underscores')
    scope = f'analyze:{image_id}'
    if key:
        status, cached = store.claim_operation(scope, key)
        if status == 'complete':
            return cached
        if status != 'claimed':
            raise HTTPException(409, 'Analysis is pending or failed; inspect before explicitly retrying with a new key')
    try:
        batch, audit = vision.analyze(image, dataset)
    except vision.VisionUnavailable as exc:
        if key:
            store.finish_operation(scope, key, None)
        raise HTTPException(503, str(exc)) from exc
    except vision.VisionFailure as exc:
        if key:
            store.finish_operation(scope, key, None)
        raise HTTPException(502, str(exc)) from exc
    run = store.save('vision_run', {**audit, 'image_id': str(image_id), 'dataset_id': image['dataset_id']})
    candidates = store.save_many('annotation', [
        {'dataset_id': image['dataset_id'], 'image_id': str(image_id), 'origin': 'ai',
         'run_id': run['id'], 'annotation': a.model_dump(mode='json')}
        for a in batch.annotations
    ])
    result = {'run_id': run['id'], 'status': 'pending_review', 'annotations': candidates}
    if key:
        store.finish_operation(scope, key, result)
    return result


@router.get('/runs/{run_id}')
def read_run(run_id: UUID, request: Request):
    return get(request.app.state.store, 'vision_run', run_id)


@router.post('/datasets/{dataset_id}/annotations', status_code=201)
def import_annotation(dataset_id: UUID, payload: ImportedProposal, request: Request):
    store = request.app.state.store
    dataset = Dataset.model_validate(get(store, 'spatial_dataset', dataset_id)['snapshot'])
    image = get(store, 'spatial_image', payload.image_id)
    if image['dataset_id'] != str(dataset_id):
        raise HTTPException(422, 'Image belongs to another dataset')
    validate_link(dataset, payload.annotation)
    return store.save('annotation', {**payload.model_dump(mode='json'), 'dataset_id': str(dataset_id),
                                     'origin': 'imported_unverified'})


@router.get('/datasets/{dataset_id}/annotations')
def list_annotations(dataset_id: UUID, request: Request, limit: int = Query(100, ge=1, le=200),
                     offset: int = Query(0, ge=0)):
    store = request.app.state.store
    get(store, 'spatial_dataset', dataset_id)
    withdrawn = {r['annotation_id'] for r in store.list_records('annotation_retraction', str(dataset_id))}
    result = []
    records = store.list_records('annotation', str(dataset_id), limit + 1, offset)
    for record in records[:limit]:
        review = store.decision(record['id'])
        status = 'pending_review' if review is None else ('approved' if review['action'] == 'approve' else 'rejected')
        if record['id'] in withdrawn:
            status = 'withdrawn'
        result.append({**record, 'review': review, 'status': status})
    return {'annotations': result, 'next_offset': offset + limit if len(records) > limit else None}


@router.post('/annotations/{annotation_id}/review', status_code=201)
def review_annotation(annotation_id: UUID, payload: Review, request: Request):
    store = request.app.state.store
    record = get(store, 'annotation', annotation_id)
    dataset = Dataset.model_validate(get(store, 'spatial_dataset', record['dataset_id'])['snapshot'])
    effective = payload.corrected_annotation or Annotation.model_validate(record['annotation'])
    if payload.action == 'approve':
        validate_link(dataset, effective, require_link=True)
    try:
        return store.decide(str(annotation_id), {
            **payload.model_dump(mode='json'),
            'approved_annotation': effective.model_dump(mode='json') if payload.action == 'approve' else None,
        })
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, 'Already reviewed; withdraw an approval and submit a new candidate to revise') from exc


@router.post('/annotations/{annotation_id}/withdraw', status_code=201)
def withdraw_annotation(annotation_id: UUID, payload: Retraction, request: Request):
    store = request.app.state.store
    record = get(store, 'annotation', annotation_id)
    review = store.decision(str(annotation_id))
    if review is None or review['action'] != 'approve':
        raise HTTPException(409, 'Only approved annotations can be withdrawn')
    if any(r['annotation_id'] == str(annotation_id)
           for r in store.list_records('annotation_retraction', record['dataset_id'])):
        raise HTTPException(409, 'Annotation already withdrawn')
    try:
        return store.save('annotation_retraction', {
            **payload.model_dump(), 'annotation_id': str(annotation_id), 'dataset_id': record['dataset_id'],
        })
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, 'Annotation already withdrawn') from exc


@router.post('/datasets/{dataset_id}/query', response_model=SpatialAnswer)
def query(dataset_id: UUID, payload: SpatialQuery, request: Request):
    store = request.app.state.store
    dataset = Dataset.model_validate(get(store, 'spatial_dataset', dataset_id)['snapshot'])
    entities = {e.id: e for e in dataset.entities}
    center = entities.get(payload.center_entity_id)
    if center is None:
        raise HTTPException(422, 'Unknown center entity')
    if center.coordinates is None:
        raise HTTPException(422, 'Center has no coordinates; cannot calculate distance')
    # Read retractions after reviews; a completed withdrawal is excluded from subsequent queries.
    reviewed = store.reviewed_records(str(dataset_id))
    withdrawn = {r['annotation_id'] for r in store.list_records('annotation_retraction', str(dataset_id))}
    citations = []
    older_matches = []
    cutoff = payload.as_of - timedelta(hours=payload.max_age_hours)
    for record, review in reviewed:
        if review['action'] != 'approve' or record['id'] in withdrawn:
            continue
        annotation = Annotation.model_validate(review['approved_annotation'])
        entity = entities[annotation.entity_id]
        if entity.kind != payload.kind or entity.coordinates is None or annotation.observation != payload.observation:
            continue
        distance = distance_m(center.coordinates, entity.coordinates)
        if distance > payload.radius_m:
            continue
        image = get(store, 'spatial_image', record['image_id'], metadata=True)
        captured_at = datetime.fromisoformat(image['captured_at'])
        if captured_at < cutoff:
            older_matches.append((entity.name, captured_at, image['evidence_basis']))
            continue
        if captured_at > payload.as_of:
            continue
        citations.append({
            'annotation_id': record['id'], 'image_id': image['id'],
            'image_url': f"/spatial/images/{image['id']}/content",
            'entity_id': entity.id, 'entity_name': entity.name,
            'coordinates': entity.coordinates, 'distance_m': round(distance, 2),
            'captured_at': captured_at, 'source': image['source'], 'evidence_basis': image['evidence_basis'],
            'origin': record['origin'], 'annotation': annotation,
            'reviewer': review['reviewer'], 'review_note': review['note'], 'reviewed_at': review['created_at'],
        })
    citations.sort(key=lambda c: (c['distance_m'], c['entity_id'], c['annotation_id']))
    labels = {'obstacle_visible': '可见障碍物', 'no_obstacle_visible': '画面中未见明显障碍物', 'unknown': '情况不明确'}
    if citations:
        entries = [f"{c['entity_name']}（约 {c['distance_m']} 米，图片时间 {c['captured_at'].isoformat()}）[{i}]"
                   for i, c in enumerate(citations, 1)]
        answer = f'在指定时间窗口和 {payload.radius_m:g} 米范围内，找到已审核的“{labels[payload.observation]}”记录：' + '；'.join(entries)
    else:
        answer = '未检索到满足空间、时间和审核条件的记录，无法据此判断现场有无障碍物或是否可通行。'
        if older_matches:
            newest_name, newest_at, _ = max(older_matches, key=lambda item: item[1])
            answer += (f'本次查询截止 {payload.as_of.isoformat()}，回溯 {payload.max_age_hours} 小时；'
                       f'同范围、同类别且符合观察条件的已审核记录中，有 {len(older_matches)} 条早于本次时间窗口，'
                       f'其中最新一条为“{newest_name}”于 {newest_at.isoformat()} 采集；'
                       '可扩大查询时间范围查看，但这些记录不代表当前状态。')
    if dataset.coordinate_basis == 'exercise':
        answer = '【演练坐标】' + answer
    if (any(c['evidence_basis'] == 'exercise' for c in citations)
            or (not citations and any(item[2] == 'exercise' for item in older_matches))):
        answer = '【包含演练图片证据】' + answer
    return {
        'dataset_id': dataset_id, 'status': 'evidence_found' if citations else 'insufficient_evidence',
        'answer': answer, 'coordinate_basis': dataset.coordinate_basis, 'query': payload, 'citations': citations,
        'older_evidence_count': len(older_matches),
        'missing_coordinates': [e.id for e in dataset.entities if e.kind == payload.kind and e.coordinates is None],
        'limitations': ['距离是 WGS84 点位间球面距离，不是步行距离或建筑边界距离',
                        '结果表示图片采集时的观察记录，不表示当前通行安全；可能存在其他相反记录',
                        '只检索当前仍有效的人工审核结果；as_of 限制图片时间，不是历史审核状态回放',
                        '置信度是模型或录入者自报，未经过概率校准；人工审核也不保证现场事实无误'],
    }


@router.post('/datasets/{dataset_id}/ask', response_model=NaturalAnswer)
def ask(dataset_id: UUID, payload: NaturalQuestion, request: Request):
    store = request.app.state.store
    dataset = Dataset.model_validate(get(store, 'spatial_dataset', dataset_id)['snapshot'])
    try:
        intent, audit = vision.interpret_question(payload.question, dataset)
    except vision.VisionUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except vision.VisionFailure as exc:
        raise HTTPException(502, str(exc)) from exc
    run = store.save('vision_run', {**audit, 'dataset_id': str(dataset_id), 'question': payload.question,
                                    'interpreted_query': intent.model_dump(mode='json')})
    center = next((e for e in dataset.entities if e.id == intent.center_entity_id), None)
    clarification = None
    if center is None:
        clarification = '无法从问题中确定查询中心，请指定地图上的建筑或地点名称。'
    elif center.coordinates is None:
        clarification = f'“{center.name}”在地图上没有坐标，无法计算距离，请改用有坐标的地点作为中心。'
    elif intent.radius_m is None:
        clarification = '问题中没有明确查询半径，请指定距离范围，例如 100 米。'
    if clarification:
        return {'status': 'clarification_needed', 'answer': clarification, 'run_id': run['id'],
                'interpreted_query': intent, 'evidence': None, 'clarification': clarification}
    if intent.max_age_hours is None:
        intent = intent.model_copy(update={'max_age_hours': 24})
    query_payload = SpatialQuery.model_validate(intent.model_dump() | {'as_of': datetime.now().astimezone()})
    evidence = query(dataset_id, query_payload, request)
    return {'status': 'answered', 'answer': evidence['answer'], 'run_id': run['id'],
            'interpreted_query': intent, 'evidence': evidence, 'clarification': None}
