"""Disposable team backend for browser checks. Never calls paid providers.

Run only for tests: python -m examples.frontend_test_server
The public test tokens below authorize only this temporary test database.
"""
import hashlib
import json
import os
import tempfile
from pathlib import Path

import uvicorn

from app import integrations, vision
from app.main import create_app
from app.spatial_models import ProposalBatch, QueryIntent


def main():
    def analyze(image, dataset):
        return ProposalBatch.model_validate({'annotations': [{
            'entity_id': 'east', 'observation': 'obstacle_visible',
            'description': '合成模型测试：入口可见障碍物。', 'confidence': .8,
            'bbox': {'x_min': .1, 'y_min': .1, 'x_max': .8, 'y_max': .8},
        }]}), {'model': 'browser-fixture', 'raw_response': 'synthetic fixture'}

    def interpret(question, dataset):
        return QueryIntent(center_entity_id='building-a', radius_m=100, kind='entrance',
                           observation='obstacle_visible', max_age_hours=24), {'model': 'browser-fixture'}

    vision.analyze = analyze
    vision.interpret_question = interpret
    # Fail closed if a new UI path attempts a provider call outside these fixtures.
    def reject_provider(*args, **kwargs):
        raise vision.VisionFailure('Browser test: unmocked provider call is disabled')
    vision.request_json = reject_provider
    integrations.anysearch = lambda payload: {
        'provider': 'fixture', 'origin': 'web_unverified', 'query': payload.query,
        'retrieved_at': '2026-10-20T00:00:00Z',
        'results': [{'url': 'https://www.usgs.gov/', 'title': 'USGS / 测试背景资料',
                     'content': '固定测试响应，不是现场证据。'}]}
    with tempfile.TemporaryDirectory(prefix='disaster-frontend-') as folder:
        directory = Path(folder)
        users = [{'user_id': role, 'workspace': workspace, 'role': role,
                  'token_sha256': hashlib.sha256(token.encode()).hexdigest()}
                 for role, workspace, token in [
                     ('admin', 'browser-test', 'frontend-test-admin'),
                     ('viewer', 'browser-test', 'frontend-test-viewer'),
                     ('admin', 'isolated-test', 'frontend-test-isolated')]]
        config = directory / 'access.json'
        config.write_text(json.dumps({'users': users, 'requests_per_minute': 10000,
                                      'model_requests_per_minute': 100}), encoding='utf-8')
        os.environ['DISASTER_CORS_ORIGINS'] = 'http://127.0.0.1:8080,http://localhost:8080'
        app = create_app(directory / 'test.db', mode='team', access_config=config)
        uvicorn.run(app, host='127.0.0.1', port=8002, log_level='warning')


if __name__ == '__main__':
    main()
