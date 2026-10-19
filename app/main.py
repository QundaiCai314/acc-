import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from .graph import export_turtle
from .models import Decision, Scenario
from .planner import compare
from .store import Store
from .spatial import router as spatial_router


def create_app(db_path: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(db_path or Path(os.getenv('DISASTER_DB_PATH', 'data/disaster.db')))
        yield

    app = FastAPI(title='AI Disaster Commander — Spatial RAG', version='0.2.0', lifespan=lifespan)
    app.include_router(spatial_router)

    def get(kind: str, identifier: UUID):
        record = app.state.store.get(kind, str(identifier))
        if record is None:
            raise HTTPException(404, detail=f'{kind} not found')
        return record

    @app.get('/health')
    def health():
        return {'status': 'ok', 'mode': 'exercise', 'version': app.version}

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
