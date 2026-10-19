"""Provider endpoints with bounded responses and separate, unverified web references."""
import base64
import json
import struct
import zlib
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from . import vision
from .models import StrictModel
from .settings import setting
from .spatial import get
from .spatial_models import Dataset


router = APIRouter(tags=['integrations'])


class SearchInput(StrictModel):
    query: str = Field(min_length=2, max_length=1000)
    max_results: int = Field(default=5, ge=1, le=10)


class ProbeInput(StrictModel):
    provider: Literal['vision', 'question', 'anysearch']


def anysearch(payload: SearchInput):
    key = setting('ANYSEARCH_API_KEY')
    headers = {'X-Anysearch-Client': 'disaster-spatial-rag/0.3.0'}
    if key:
        headers['Authorization'] = f'Bearer {key}'
    try:
        # Fixed official host: application callers cannot redirect credentials to another endpoint.
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            with client.stream('POST', 'https://api.anysearch.com/v1/search', headers=headers,
                               json=payload.model_dump()) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 2_000_000:
                        raise ValueError('Search response too large')
        envelope = json.loads(body)
        if envelope.get('code', 0) != 0:
            raise ValueError('Search provider returned an error')
        rows = envelope['data']['results']
        if not isinstance(rows, list):
            raise ValueError('Invalid results')
        results = []
        for row in rows[:payload.max_results]:
            url = row.get('url', '')
            parsed = urlsplit(url)
            if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
                continue
            title, content = row.get('title', ''), row.get('content') or row.get('snippet') or ''
            if not isinstance(title, str) or not isinstance(content, str):
                raise ValueError('Invalid search result fields')
            results.append({'url': url[:4000], 'title': title[:1000], 'content': content[:20000]})
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise HTTPException(502, 'AnySearch request failed or returned an invalid response') from exc
    return {'provider': 'anysearch', 'query': payload.query, 'results': results,
            'retrieved_at': datetime.now(timezone.utc).isoformat(), 'origin': 'web_unverified',
            'limitations': ['网络资料仅用于背景参考，未审核，不进入现场图片证据或空间事实推理']}


@router.post('/spatial/datasets/{dataset_id}/references/search', status_code=201)
def search_references(dataset_id: UUID, payload: SearchInput, request: Request):
    store = request.app.state.store
    get(store, 'spatial_dataset', dataset_id)
    return store.save('web_reference', {**anysearch(payload), 'dataset_id': str(dataset_id)})


@router.get('/spatial/references/{reference_id}')
def read_reference(reference_id: UUID, request: Request):
    return get(request.app.state.store, 'web_reference', reference_id)


@router.get('/integrations')
def integration_status():
    return {
        'vision': {'configured': all(setting(k) for k in ('VISION_CHAT_URL', 'VISION_MODEL', 'VISION_API_KEY')),
                   'model': setting('VISION_MODEL')},
        'question': {'configured': all(setting('QUESTION_'+s, setting('VISION_'+s)) for s in ('CHAT_URL', 'MODEL', 'API_KEY')),
                     'model': setting('QUESTION_MODEL', setting('VISION_MODEL'))},
        'anysearch': {'configured': True, 'authentication': 'api_key' if setting('ANYSEARCH_API_KEY') else 'anonymous'},
        'xingyun3d': {'purpose': 'digital_avatar', 'registration_provider': False,
                      'status': 'requires_avatar_application_credentials'},
        'note': 'Configured does not mean verified; POST /integrations/probe makes a real provider request',
    }


@router.post('/integrations/probe')
def probe(payload: ProbeInput):
    if payload.provider == 'anysearch':
        result = anysearch(SearchInput(query='USGS earthquake preparedness', max_results=1))
        return {'provider': 'anysearch', 'status': 'verified', 'result_count': len(result['results'])}
    ds = Dataset(title='Synthetic provider probe', coordinate_basis='exercise', map_source='Synthetic probe',
                 curator='probe', entities=[{'id': 'building-a', 'name': 'A楼', 'kind': 'building',
                                            'coordinates': {'latitude': 0, 'longitude': 0}}])
    try:
        if payload.provider == 'question':
            result, audit = vision.interpret_question('A楼100米内最近24小时哪些入口可见障碍物？', ds)
            valid = result.center_entity_id == 'building-a' and result.radius_m == 100
        else:
            # A correctly checksummed blank PNG tests the protocol, not recognition accuracy.
            def chunk(kind, data):
                return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind+data))
            png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 32, 32, 8, 2, 0, 0, 0))
                   + chunk(b'IDAT', zlib.compress((b'\0'+b'\xff'*96)*32)) + chunk(b'IEND', b''))
            content = base64.b64encode(png).decode('ascii')
            result, audit = vision.analyze({'mime_type': 'image/png', 'content_base64': content}, ds)
            valid = True
    except vision.VisionUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except vision.VisionFailure as exc:
        raise HTTPException(502, str(exc)) from exc
    return {'provider': payload.provider, 'status': 'verified' if valid else 'semantic_check_failed',
            'model': audit['model'], 'provider_host': audit['provider_host'],
            'note': 'Synthetic probe only; field accuracy is not established'}
