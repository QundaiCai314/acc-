import copy
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError
from rdflib import Graph, Namespace, RDF

from app.main import create_app
from app.models import Scenario
from app.planner import compare


EXAMPLE = Path(__file__).resolve().parents[1] / 'examples' / 'scenario.json'


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(EXAMPLE.read_text(encoding='utf-8'))

    def test_comparison_and_constraints(self):
        scenario = Scenario.model_validate(self.payload)
        plans = compare(scenario)
        self.assertEqual([p['assignments'][0]['site_id'] for p in plans], ['A', 'B', 'C'])
        for plan in plans:
            self.assertIn('道路不可达', plan['unassigned']['D'])
            self.assertEqual(plan['solver_status'], 'OPTIMAL')
        self.payload['teams'].append({'id': 'team-2', 'skills': ['search', 'lifting']})
        for site in self.payload['sites']:
            site['equipment'] = {'lifting-kit': 1}
        for plan in compare(Scenario.model_validate(self.payload)):
            self.assertEqual(len(plan['assignments']), 1)

    def test_all_blocked(self):
        for site in self.payload['sites']:
            site['accessible'] = False
        for plan in compare(Scenario.model_validate(self.payload)):
            self.assertEqual(plan['assignments'], [])
            self.assertEqual(plan['people_covered'], 0)
            self.assertEqual(len(plan['unassigned']), 4)

    def test_skill_time_and_risk_exclusions(self):
        self.payload['sites'][0]['required_skills'] = ['medical']
        self.payload['sites'][1]['work_minutes'] = 121
        self.payload['sites'][2]['risk'] = 5
        plan = compare(Scenario.model_validate(self.payload))[0]
        self.assertFalse(plan['assignments'])
        self.assertIn('没有具备所需技能的队伍', plan['unassigned']['A'])
        self.assertIn('无法在本轮时间窗口内完成', plan['unassigned']['B'])
        self.assertIn('超过允许风险等级', plan['unassigned']['C'])

    def test_validation(self):
        mutations = [
            lambda p: p['sites'][0].update(evidence_ids=['missing']),
            lambda p: p['equipment'].update(crane=-1),
            lambda p: p['teams'].append(copy.deepcopy(p['teams'][0])),
            lambda p: p['evidence'][0].update(observed_at='2026-10-18T10:00:00'),
            lambda p: p.update(exercise=False),
        ]
        for mutate in mutations:
            payload = copy.deepcopy(self.payload)
            mutate(payload)
            with self.assertRaises(ValidationError):
                Scenario.model_validate(payload)

    def test_api_persistence_graph_and_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'test.db'
            with TestClient(create_app(db)) as client:
                self.assertEqual(client.get('/health').status_code, 200)
                response = client.post('/scenarios', json=self.payload)
                self.assertEqual(response.status_code, 201, response.text)
                scenario_id = response.json()['id']
                response = client.get(f'/scenarios/{scenario_id}/graph')
                self.assertEqual(response.status_code, 200)
                graph = Graph().parse(data=response.text, format='turtle')
                vocab = Namespace('urn:disaster:vocab:')
                self.assertEqual(len(list(graph.subjects(RDF.type, vocab.Site))), 4)
                self.assertEqual(len(list(graph.triples((None, vocab.evidence_ids, None)))), 4)
                response = client.post(f'/scenarios/{scenario_id}/plans')
                self.assertEqual(response.status_code, 201, response.text)
                self.assertEqual(len(response.json()['plans']), 3)
                plan_id = response.json()['plans'][0]['id']
                decision = {'reviewer': 'demo-reviewer', 'action': 'approve', 'note': '演练确认'}
                self.assertEqual(client.post(f'/plans/{plan_id}/decision', json=decision).status_code, 201)
                self.assertEqual(client.post(f'/plans/{plan_id}/decision', json=decision).status_code, 409)
                self.assertEqual(client.post('/scenarios', json={'title': 'incomplete'}).status_code, 422)
                self.assertEqual(client.get('/plans/00000000-0000-0000-0000-000000000000').status_code, 404)
            with TestClient(create_app(db)) as client:
                plan = client.get(f'/plans/{plan_id}').json()
                self.assertEqual(plan['decision']['action'], 'approve')
                self.assertEqual(plan['scenario_id'], scenario_id)
                self.assertEqual(client.get(f'/scenarios/{scenario_id}').json()['snapshot']['title'], self.payload['title'])


if __name__ == '__main__':
    unittest.main()
