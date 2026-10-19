import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from .graph import export_turtle
from .models import Decision, Scenario
from .planner import compare
from .store import Store, ReviewLeaseConflict
from .spatial import router as spatial_router
from .geometry import router as geometry_router
from .integrations import router as integrations_router
from .access import AccessConfig, AccessMiddleware, authorize, principal
from .settings import ConfigurationError


def create_app(db_path: Path | None = None, *, mode: str | None = None, access_config: Path | None = None) -> FastAPI:
    mode = mode or os.getenv('DISASTER_MODE', 'local')
    if mode not in ('local', 'team'):
        raise ValueError('DISASTER_MODE must be local or team')
    access_config = access_config or Path(os.getenv('DISASTER_ACCESS_CONFIG', 'data/access.json'))
    @asynccontextmanager
    async def lifespan(app):
        if mode == 'team':
            AccessConfig.model_validate_json(access_config.read_text(encoding='utf-8'))
        app.state.store = Store(db_path or Path(os.getenv('DISASTER_DB_PATH', 'data/disaster.db')))
        yield

    app = FastAPI(title='AI Disaster Commander — Spatial RAG', version='0.3.0', lifespan=lifespan,
                  dependencies=[Depends(authorize)])
    app.add_middleware(AccessMiddleware, mode=mode, config_path=access_config)
    origins = [s.strip() for s in os.getenv('DISASTER_CORS_ORIGINS', '').split(',') if s.strip()]
    if '*' in origins:
        raise ValueError('List exact CORS origins; wildcard is not supported')
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['GET', 'POST'],
                           allow_headers=['Authorization', 'Content-Type', 'Idempotency-Key'])
    app.include_router(spatial_router)
    app.include_router(geometry_router)
    app.include_router(integrations_router)

    @app.exception_handler(ConfigurationError)
    async def invalid_provider_config(request, exc):
        return JSONResponse({'detail': 'Provider configuration is unreadable or invalid'}, status_code=503)

    @app.exception_handler(ReviewLeaseConflict)
    async def review_conflict(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=409)

    def get(kind: str, identifier: UUID):
        record = app.state.store.get(kind, str(identifier))
        if record is None:
            raise HTTPException(404, detail=f'{kind} not found')
        return record

    @app.get('/health')
    def health():
        return {'status': 'ok', 'mode': 'exercise', 'access_mode': mode, 'version': app.version}

    @app.get('/auth/me')
    def me():
        return principal.get()

    @app.post('/scenarios', status_code=201)
    def create_scenario(scenario: Scenario):
        return app.state.store.save('scenario', {'snapshot': scenario.model_dump(mode='json')})

    @app.get('/scenarios/{scenario_id}')
    def read_scenario(scenario_id: UUID):
        return get('scenario', scenario_id)

    @app.get('/scenarios/{scenario_id}/graph')
    def graph(scenario_id: UUID):
        scenario = Scenario.model_validate(get('scenario', scenario_id)['snapshot'])
        return Response(export_turtle(str(scenario_id), scenario), media_type='text/turtle')

    @app.post('/scenarios/{scenario_id}/plans', status_code=201)
    def create_plans(scenario_id: UUID):
        scenario = Scenario.model_validate(get('scenario', scenario_id)['snapshot'])
        try:
            candidates = compare(scenario)
        except RuntimeError as exc:
            raise HTTPException(503, detail='Planner unavailable; retry or simplify scenario') from exc
        return {'scenario_id': str(scenario_id), 'plans': [
            app.state.store.save('plan', {**candidate, 'scenario_id': str(scenario_id)})
            for candidate in candidates]}

    @app.get('/plans/{plan_id}')
    def read_plan(plan_id: UUID):
        return {**get('plan', plan_id), 'decision': app.state.store.decision(str(plan_id))}

    @app.post('/plans/{plan_id}/decision', status_code=201)
    def decide(plan_id: UUID, decision: Decision):
        get('plan', plan_id)
        try:
            return app.state.store.decide(str(plan_id), decision.model_dump())
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, detail='Plan already has a final decision; create a new plan to reconsider') from exc

    return app


app = create_app()
