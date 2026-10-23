"""Import validated real inputs into a local backend, keeping every artifact pending.

Run validate_real_geometry first. Reuses matching snapshots after interruption;
never approves, withdraws, updates or calls a model. Local single-writer utility.
"""
import json
from pathlib import Path

import httpx

from app.geometry_models import Registration, RoadNetwork
from app.spatial_models import Dataset


def main():
    root = Path('data/real-geometry')
    payloads = json.loads((root/'payloads.json').read_text('utf8'))
    checkpoint = root/'live-import.json'
    saved = json.loads(checkpoint.read_text('utf8')) if checkpoint.exists() else {}

    def save():
        temporary = checkpoint.with_suffix('.tmp')
        temporary.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf8')
        temporary.replace(checkpoint)

    with httpx.Client(base_url='http://127.0.0.1:8000', timeout=30, trust_env=False) as client:
        response = client.get('/health')
        response.raise_for_status()
        if response.json()['access_mode'] != 'local':
            raise ValueError('This importer is for the local preview backend only')

        def records(url, key):
            offset = 0
            while offset is not None:
                response = client.get(url, params={'offset': offset, 'limit': 200})
                response.raise_for_status()
                page = response.json()
                yield from page[key]
                offset = page['next_offset']

        def ensure(key, url, collection, model):
            expected_model = model.model_validate(payloads[key])
            expected = expected_model.model_dump(mode='json')
            matches = [r for r in records(url, collection) if model.model_validate(r['snapshot']) == expected_model]
            if len(matches) > 1:
                raise ValueError(f'Ambiguous duplicate imports for {key}; inspect before continuing')
            if matches:
                record = matches[0]
            else:
                response = client.post(url, json=expected)
                response.raise_for_status()
                record = response.json()
            saved[key] = {'id': record['id'], 'url': url, 'snapshot': record['snapshot']}
            save()
            return record['id']

        road = ensure('road_dataset', '/spatial/datasets', 'datasets', Dataset)
        scan = ensure('scan_dataset', '/spatial/datasets', 'datasets', Dataset)
        for key, ds, endpoint, model in (
            ('network', road, 'networks', RoadNetwork),
            ('registration', scan, 'registrations', Registration),
        ):
            # Lists and writes have different endpoints; recover even if interrupted after POST.
            listing = f'/spatial/datasets/{ds}/artifacts'
            expected_model = model.model_validate(payloads[key])
            expected = expected_model.model_dump(mode='json')
            kind = 'road_network' if key == 'network' else 'registration'
            # Compare validated models: modes is a set and its JSON order may vary across processes.
            matches = [r for r in records(listing, 'artifacts') if r['artifact_type'] == kind
                       and model.model_validate(r['snapshot']) == expected_model]
            if matches:
                record = next((r for r in matches if r['id'] == saved.get(key, {}).get('id')), matches[0])
            else:
                response = client.post(f'/spatial/datasets/{ds}/{endpoint}', json=expected)
                response.raise_for_status()
                record = response.json()
            saved[key] = {'id': record['id'], 'dataset_id': ds}
            save()
            response = client.get(f'/spatial/artifacts/{record["id"]}')
            response.raise_for_status()
            current = response.json()
            if current['review'] is not None or current['withdrawals']:
                raise ValueError(f'{key} was already reviewed; importer will not alter its decision')
        print(json.dumps({k: v['id'] for k, v in saved.items()}, indent=2))


if __name__ == '__main__':
    main()
