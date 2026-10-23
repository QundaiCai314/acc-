"""Download hash-locked real inputs and validate geometry in a disposable database.

Run: python -m examples.validate_real_geometry
Outputs ignored raw data/payloads under data/real-geometry. No live approvals,
model calls, fabricated GPS, road observations or modified source scans.
"""
import argparse
import copy
import hashlib
import json
import math
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from app.geometry import shortest_path
from app.main import create_app
from app.spatial import distance_m
from app.spatial_models import Coordinates

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'data/real-geometry'
SOURCES = {
    'roads.osm': (
        'https://raw.githubusercontent.com/gboeing/osmnx/main/tests/input_data/planet_10.068,48.135_10.071,48.137.osm',
        '280febb5b8b084cd4f29c138f5f65f8b219efdca7070bc7233a85ef972fab2a9'),
    'car_cloud400.csv': (
        'https://raw.githubusercontent.com/norlab-ulaval/libpointmatcher/master/examples/data/car_cloud400.csv',
        'f612b04c53c3dddb050062e6233ecc188f90280b9c4e5ce048b06b5f3d42ff22'),
    'car_cloud401.csv': (
        'https://raw.githubusercontent.com/norlab-ulaval/libpointmatcher/master/examples/data/car_cloud401.csv',
        '9073e1e188d4e054c749d4d221e5663dd94426e0df449b51cc33aaa86a89d469'),
    'carCloudList.csv': (
        'https://raw.githubusercontent.com/norlab-ulaval/libpointmatcher/master/examples/data/carCloudList.csv',
        '7ad9f6a6c27607807605c45ac18b4507757027c510657c571cd75b7d1b750bf5'),
}


def save(name, value):
    (CACHE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')


def inputs():
    CACHE.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, (url, expected) in SOURCES.items():
        path = CACHE / name
        if not path.exists():
            request = urllib.request.Request(url, headers={'User-Agent': 'AI-Disaster-Commander-validation/0.3'})
            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read(10_000_001)
            if len(content) > 10_000_000 or hashlib.sha256(content).hexdigest() != expected:
                raise ValueError(f'Unexpected source data: {name}')
            path.write_bytes(content)
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f'Source hash mismatch: {name}; do not silently replace validation inputs')
        manifest.append({'file': name, 'url': url, 'sha256': expected, 'bytes': len(content)})
    return manifest


def make_roads(validity):
    root = ET.parse(CACHE / 'roads.osm').getroot()
    coordinates = {n.attrib['id']: Coordinates(latitude=float(n.attrib['lat']), longitude=float(n.attrib['lon']))
                   for n in root.findall('node')}
    edges, used, omitted = [], set(), []
    for way in root.findall('way'):
        tags = {t.attrib['k']: t.attrib['v'] for t in way.findall('tag')}
        if 'highway' not in tags:
            continue
        refs = [n.attrib['ref'] for n in way.findall('nd')]
        # This bounded source adapter supports only these classes, not general OSM routing.
        if tags['highway'] not in ('residential', 'track') or tags.get('access') in ('no', 'private'):
            omitted.append({'way_id': way.attrib['id'], 'reason': 'unsupported_class_or_restricted_access', 'tags': tags})
            continue
        if len(refs) < 2:
            omitted.append({'way_id': way.attrib['id'], 'reason': 'clipped_way_has_no_segment'})
            continue
        modes = ['walk'] if tags['highway'] == 'track' else ['walk', 'vehicle']
        if tags.get('foot') in ('no', 'private'):
            modes.remove('walk')
        if tags.get('motor_vehicle') in ('no', 'private') and 'vehicle' in modes:
            modes.remove('vehicle')
        if not modes:
            continue
        if tags.get('oneway') not in (None, 'no') or 'oneway:foot' in tags or 'restriction' in tags:
            raise ValueError('This source adapter needs an explicit rule for directional/restriction tags')
        for index, (a, b) in enumerate(zip(refs, refs[1:])):
            if a not in coordinates or b not in coordinates:
                raise ValueError('Source contains an unresolved road node')
            used.update((a, b))
            edges.append({'id': f'osm-w{way.attrib["id"]}-{index}', 'source': f'osm-n{a}', 'target': f'osm-n{b}',
                          'length_m': distance_m(coordinates[a], coordinates[b]), 'bidirectional': True,
                          'modes': modes, 'status': 'unknown', 'annotation_ids': [],
                          'source_note': json.dumps({'way_id': way.attrib['id'], 'tags': tags,
                                                    'basis': 'OSM mapped segment, not a field road-condition observation'})})
    dataset = {'title': 'Real OSM topology | 48.135-48.137N, 10.068-10.071E | 2020 archive',
               'coordinate_basis': 'measured', 'curator': 'public-source-import',
               'map_source': 'OpenStreetMap contributors / ODbL 1.0; OSMnx archived extract; '
                             f'source snapshot {root.attrib.get("timestamp")}; mapped GPS, not survey-grade or live traffic.',
               'entities': [{'id': f'osm-n{n}', 'name': f'OSM road node {n}', 'kind': 'road',
                             'coordinates': coordinates[n].model_dump()} for n in sorted(used)]}
    network = {**validity, 'source_note': dataset['map_source'] + ' Usage interval is administrative only; '
               'all field conditions UNKNOWN. Only mapped_topology can traverse unknown edges after review.', 'edges': edges}
    return dataset, network, {'snapshot_at': root.attrib.get('timestamp'), 'omitted': omitted,
                              'node_count': len(used), 'edge_count': len(edges)}


def make_registration(validity):
    reference = np.loadtxt(CACHE/'car_cloud400.csv', delimiter=',', skiprows=1, usecols=(0, 1, 2))
    reading = np.loadtxt(CACHE/'car_cloud401.csv')
    upstream = np.loadtxt(CACHE/'carCloudList.csv', delimiter=',', skiprows=2, usecols=range(1, 17)).reshape(4, 4)
    indices = np.unique(np.linspace(0, len(reading)-1, 250, dtype=int))
    aligned = reading[indices] @ upstream[:3, :3].T + upstream[:3, 3]
    pairs, distances, targets = [], [], set()
    # Bounded exact matching uses existing NumPy, not another point-cloud dependency.
    # Upstream alignment establishes candidate correspondences, not survey ground truth.
    for source_id, point in zip(indices, aligned):
        squared = ((reference-point)**2).sum(axis=1)
        target_id = int(squared.argmin())
        error = float(math.sqrt(squared[target_id]))
        distances.append(error)
        if error < .2 and target_id not in targets:
            targets.add(target_id)
            pairs.append({'label': f's{source_id}-r{target_id}', 'scene': reading[source_id].tolist(),
                          'local_m': reference[target_id].tolist()})
    if len(pairs) < 80:
        raise ValueError('Not enough distinct source-backed correspondences')
    selected = [pairs[i] for i in np.linspace(0, len(pairs)-1, 80, dtype=int)]
    payload = {**validity, 'source_note': 'libpointmatcher car dataset: real two-scan point pairs; '
               'upstream-reference-assisted nearest neighbors <0.2m, 40 control / 40 held-out pairs. '
               'Not surveyed GCPs, no known geographic origin or vertical axis. Administrative usage interval only.',
               'scene_name': 'libpointmatcher car_cloud401 -> car_cloud400 | unlocated real scans',
               'target_frame': 'local', 'scene_unit_m': 1, 'solve_scale': False,
               'control_points': selected[::2], 'check_points': selected[1::2], 'objects': [],
               'max_rmse_m': .15, 'max_error_m': .30}
    dataset = {'title': 'Real 3D scans | libpointmatcher car | no geographic origin',
               'coordinate_basis': 'measured', 'curator': 'public-source-import',
               'map_source': 'libpointmatcher public car scan dataset; original scan points in metres; '
                             'no GPS, geographic axes or survey accuracy provided. This dataset has no map location.',
               'entities': [{'id': 'scan-reference', 'name': 'car_cloud400 reference scan (unlocated)', 'kind': 'other'}]}
    return dataset, payload, {'reference_points': len(reference), 'reading_points': len(reading),
                             'candidate_samples': len(indices), 'eligible_distinct_pairs': len(pairs),
                             'selected_pairs': 80, 'selection_threshold_m': .2,
                             'raw_sample_nearest_neighbor_quantiles_m': np.quantile(distances, [.5, .9, 1]).tolist(),
                             'upstream_matrix': upstream.tolist()}


def oracle(network, mode):
    nodes = sorted({e[k] for e in network['edges'] for k in ('source', 'target')})
    index = {n: i for i, n in enumerate(nodes)}
    matrix = np.full((len(nodes), len(nodes)), np.inf)
    np.fill_diagonal(matrix, 0)
    for edge in network['edges']:
        if mode not in edge['modes']:
            continue
        a, b = index[edge['source']], index[edge['target']]
        matrix[a, b] = min(matrix[a, b], edge['length_m'])
        if edge['bidirectional']:
            matrix[b, a] = min(matrix[b, a], edge['length_m'])
    # Independent Floyd-Warshall oracle checks the application's Dijkstra.
    for k in range(len(nodes)):
        matrix = np.minimum(matrix, matrix[:, k, None] + matrix[None, k, :])
    for i, start in enumerate(nodes):
        for j, end in enumerate(nodes):
            result = shortest_path({'snapshot': network}, start, end, mode, set(), {}, 'mapped_topology')
            expected = matrix[i, j]
            assert (result['status'] == 'reachable') == bool(np.isfinite(expected))
            if np.isfinite(expected):
                assert math.isclose(result['distance_m'], expected, abs_tol=1e-8)
    longest = np.where(np.isfinite(matrix), matrix, -1)
    i, j = np.unravel_index(longest.argmax(), longest.shape)
    return {'comparisons': len(nodes)**2, 'reachable_pairs': int(np.isfinite(matrix).sum()),
            'start': nodes[i], 'end': nodes[j], 'distance_m': float(matrix[i, j])}


def validate(road_ds, network, scan_ds, registration, as_of):
    road_checks = {mode: oracle(network, mode) for mode in ('walk', 'vehicle')}
    with tempfile.TemporaryDirectory() as folder, TestClient(create_app(Path(folder)/'validation.db', mode='local')) as client:
        def post(url, payload, expected):
            response = client.post(url, json=payload)
            if response.status_code != expected:
                raise AssertionError((url, response.status_code, response.text[:1000]))
            return response.json()
        rd = post('/spatial/datasets', road_ds, 201)['id']
        sd = post('/spatial/datasets', scan_ds, 201)['id']
        net = post(f'/spatial/datasets/{rd}/networks', network, 201)
        reg = post(f'/spatial/datasets/{sd}/registrations', registration, 201)
        query = {'network_id': net['id'], 'start_entity_id': road_checks['walk']['start'],
                 'end_entity_id': road_checks['walk']['end'], 'as_of': as_of, 'basis': 'mapped_topology'}
        post(f'/spatial/datasets/{rd}/route', query, 409)
        transform_query = {'as_of': as_of, 'points': [p['scene'] for p in registration['check_points']]}
        post(f'/spatial/registrations/{reg["id"]}/transform', transform_query, 409)
        # Test-only approvals in a disposable DB, explicitly attributed to automation.
        # No production decision or claimed human review is made by this script.
        for identifier in (net['id'], reg['id']):
            post(f'/spatial/artifacts/{identifier}/review', {'action': 'approve',
                 'note': 'AUTOMATED API CONTRACT CHECK IN DISPOSABLE DB; not a human field review'}, 201)
        route = post(f'/spatial/datasets/{rd}/route', query, 200)
        assert math.isclose(route['distance_m'], road_checks['walk']['distance_m'], abs_tol=1e-8)
        assert all(e['status'] == 'unknown' for e in route['edges'])
        guarded = post(f'/spatial/datasets/{rd}/route', {**query, 'basis': 'reviewed_status'}, 200)
        assert guarded['status'] == 'unreachable'
        transformed = post(f'/spatial/registrations/{reg["id"]}/transform', transform_query, 200)
        assert transformed['wgs84'] is None and 'enu_m' not in transformed
        errors = np.linalg.norm(np.array(transformed['local_m']) -
                               np.array([p['local_m'] for p in registration['check_points']]), axis=1)
        assert math.isclose(float(np.sqrt(np.mean(errors**2))), reg['computed']['check_rmse_m'], abs_tol=1e-10)
        bad = copy.deepcopy(registration)
        bad['check_points'][0]['local_m'][0] += 1
        post(f'/spatial/datasets/{sd}/registrations', bad, 422)
        for identifier in (net['id'], reg['id']):
            post(f'/spatial/artifacts/{identifier}/withdraw', {'reviewer': 'automated-test',
                 'note': 'Disposable validation completed'}, 201)
        post(f'/spatial/datasets/{rd}/route', query, 409)
        post(f'/spatial/registrations/{reg["id"]}/transform', transform_query, 409)
    return {'oracle': road_checks, 'sample_topology_route': route, 'default_route': guarded['status'],
            'registration': reg['computed'], 'held_out_transform_errors_m': errors.tolist(),
            'pending_gate': 409, 'withdrawn_gate': 409, 'corrupted_check_point': 422,
            'review_scope': 'Automated contract checks in deleted temporary DB only; all live imports remain pending.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    manifest = inputs()
    now = datetime.now(timezone.utc)
    validity = {'valid_from': now.isoformat(), 'valid_until': (now+timedelta(days=7)).isoformat()}
    road_ds, network, road_source = make_roads(validity)
    scan_ds, registration, scan_source = make_registration(validity)
    payloads = {'road_dataset': road_ds, 'network': network, 'scan_dataset': scan_ds, 'registration': registration}
    save('payloads.json', payloads)
    result = validate(road_ds, network, scan_ds, registration, now.isoformat())
    estimated = np.array(result['registration']['matrix_scene_to_local'])
    upstream = np.array(scan_source['upstream_matrix'])
    u, _, vt = np.linalg.svd(upstream[:3, :3])
    angle = math.degrees(math.acos(float(np.clip((np.trace(estimated[:3, :3] @ (u@vt).T)-1)/2, -1, 1))))
    translation_error = float(np.linalg.norm(estimated[:3, 3] - upstream[:3, 3]))
    assert angle < .5 and translation_error < .08, (angle, translation_error)
    result['upstream_comparison'] = {'rotation_difference_deg': angle, 'translation_difference_m': translation_error,
                                     'limits': {'rotation_deg': .5, 'translation_m': .08}}
    report = {'validated_at': now.isoformat(), 'sources': manifest, 'road_source': road_source,
              'scan_source': scan_source, 'result': result,
              'limits': ['Two independent validation datasets, not the Haiti disaster photo site.',
                         'OSM archive: static mapped connectivity, no observed road states or live traffic.',
                         'Real scans: reference-assisted pairs, conditional hold-out error, not surveyed GCP accuracy.',
                         'No WGS84 origin or known vertical axis for the 3D dataset; no absolute georeferencing claim.',
                         'Artifact validity is an administrative usage interval, not source acquisition time.']}
    save('validation.json', report)
    print(json.dumps({'roads': road_source['node_count'], 'segments': road_source['edge_count'],
                      'route_m': result['sample_topology_route']['distance_m'],
                      'check_rmse_m': result['registration']['check_rmse_m'],
                      'upstream_comparison': result['upstream_comparison']}, indent=2))


if __name__ == '__main__':
    main()
