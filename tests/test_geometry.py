import copy
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from app.geometry import enu_to_wgs84, register
from app.geometry_models import ReasonIntent, Registration
from app.main import create_app
from examples.demo_spatial import diagram_png


ROOT = Path(__file__).resolve().parents[1]
NOW = '2026-10-19T00:00:00Z'
VALIDITY = {'valid_from': '2026-10-18T00:00:00Z', 'valid_until': '2026-10-20T00:00:00Z',
            'source_note': 'Synthetic geometry fixture, not a surveyed site'}


def registration_payload():
    controls = [[0,0,0], [4,0,0], [0,4,0], [0,0,4]]
    return {**VALIDITY, 'scene_name': 'Synthetic scene', 'origin': {'latitude': 0, 'longitude': 0},
            'origin_altitude_m': 0, 'max_rmse_m': .01, 'max_error_m': .02,
            'control_points': [{'label': f'p{i}', 'scene': p, 'enu_m': p} for i,p in enumerate(controls)],
            'check_points': [{'label': 'independent', 'scene': [2,2,2], 'enu_m': [2,2,2]}],
            'objects': [{'entity_id': 'entrance-near', 'min_corner': [0,0,5], 'max_corner': [1,1,6]},
                        {'entity_id': 'building-a', 'min_corner': [0,0,0], 'max_corner': [3,3,3]}]}


def network_payload():
    return {**VALIDITY, 'edges': [
        {'id': 'direct', 'source': 'building-a', 'target': 'entrance-far', 'length_m': 230,
         'status': 'blocked', 'modes': ['walk','vehicle'], 'source_note': 'Closed in exercise'},
        {'id': 'first', 'source': 'building-a', 'target': 'entrance-near', 'length_m': 60,
         'status': 'open', 'modes': ['walk','vehicle'], 'source_note': 'Reviewed in exercise'},
        {'id': 'second', 'source': 'entrance-near', 'target': 'entrance-far', 'length_m': 200,
         'status': 'open', 'modes': ['walk'], 'bidirectional': False, 'source_note': 'Pedestrian one-way'},
    ]}


class GeometryTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.client = self.enterContext(TestClient(create_app(Path(folder)/'geometry.db',mode='local')))
        self.ds = self.post('/spatial/datasets', json.loads((ROOT/'examples/spatial_dataset.json').read_text(encoding='utf-8')))['id']
        self.base = f'/spatial/datasets/{self.ds}'

    def post(self, url, payload, status=None):
        response = self.client.post(url, json=payload)
        if status is None:
            self.assertIn(response.status_code, (200,201), response.text)
        else:
            self.assertEqual(response.status_code,status,response.text)
        return response.json()

    def approve(self, identifier):
        return self.post(f'/spatial/artifacts/{identifier}/review',{'action':'approve','note':'Synthetic review'})

    def test_routing_detour_direction_modes_and_validity(self):
        network = self.post(self.base+'/networks',network_payload())['id']
        query = {'network_id':network,'start_entity_id':'building-a','end_entity_id':'entrance-far','as_of':NOW}
        self.post(self.base+'/route',query,409)
        self.approve(network)
        route = self.post(self.base+'/route',query)
        self.assertEqual(route['distance_m'],260)
        self.assertEqual([e['id'] for e in route['edges']],['first','second'])
        self.assertEqual(route['excluded_edges'],[{'edge_id':'direct','reason':'blocked'}])
        self.assertEqual(self.post(self.base+'/route',{**query,'mode':'vehicle'})['status'],'unreachable')
        self.assertEqual(self.post(self.base+'/route',{**query,'avoid_edge_ids':['first']})['status'],'unreachable')
        self.assertEqual(self.post(self.base+'/route',{**query,'start_entity_id':'entrance-far','end_entity_id':'building-a'})['status'],'unreachable')
        self.post(self.base+'/route',{**query,'as_of':'2026-10-21T00:00:00Z'},409)
        self.post(self.base+'/route',{**query,'avoid_edge_ids':['missing']},422)
        self.post(f'/spatial/artifacts/{network}/withdraw',{'reviewer':'test','note':'Changed road conditions'})
        self.post(self.base+'/route',query,409)
        self.post(f'/spatial/artifacts/{network}/withdraw',{'reviewer':'test','note':'repeat'},409)

    def test_unknown_roads_invalid_lengths_and_dataset_isolation(self):
        payload = network_payload()
        payload['edges'][1]['status']='unknown'
        network = self.post(self.base+'/networks',payload)['id']
        self.approve(network)
        query={'network_id':network,'start_entity_id':'building-a','end_entity_id':'entrance-far','as_of':NOW}
        self.assertEqual(self.post(self.base+'/route',query)['status'],'unreachable')
        payload['edges'][0]['length_m']=1
        self.post(self.base+'/networks',payload,422)
        other=self.post('/spatial/datasets',json.loads((ROOT/'examples/spatial_dataset.json').read_text(encoding='utf-8')))['id']
        self.post(f'/spatial/datasets/{other}/route',query,422)

    def test_topology_is_explicit_and_does_not_override_safety_gates(self):
        payload = network_payload()
        payload['edges'][1]['status'] = 'unknown'
        network = self.post(self.base+'/networks', payload)['id']
        query = {'network_id': network, 'start_entity_id': 'building-a',
                 'end_entity_id': 'entrance-far', 'as_of': NOW, 'basis': 'mapped_topology'}
        self.post(self.base+'/route', query, 409)
        self.approve(network)
        result = self.post(self.base+'/route', query)
        self.assertEqual(result['distance_m'], 260)
        self.assertEqual(result['unverified_edge_ids'], ['first'])
        self.assertEqual(result['edges'][0]['status'], 'unknown')
        self.assertIn({'edge_id': 'direct', 'reason': 'blocked'}, result['excluded_edges'])
        self.assertEqual(self.post(self.base+'/route', {**query, 'basis': 'reviewed_status'})['status'], 'unreachable')
        self.assertEqual(self.post(self.base+'/route', {**query, 'mode': 'vehicle'})['status'], 'unreachable')
        self.assertEqual(self.post(self.base+'/route', {**query, 'avoid_edge_ids': ['first']})['status'], 'unreachable')
        self.assertEqual(self.post(self.base+'/route', {**query, 'start_entity_id': 'entrance-far',
                                                      'end_entity_id': 'building-a'})['status'], 'unreachable')

    def test_local_registration_never_invents_geography(self):
        payload = registration_payload()
        payload.update(target_frame='local', origin=None, origin_altitude_m=None)
        for point in payload['control_points'] + payload['check_points']:
            point['local_m'] = point.pop('enu_m')
        registration = self.post(self.base+'/registrations', payload)
        self.assertNotIn('matrix_scene_to_enu', registration['computed'])
        self.assertEqual(registration['computed']['axis_order'], ['x', 'y', 'z'])
        endpoint = f'/spatial/registrations/{registration["id"]}/transform'
        query = {'as_of': NOW, 'points': [[1, 2, 3]]}
        self.post(endpoint, query, 409)
        self.approve(registration['id'])
        result = self.post(endpoint, query)
        self.assertIsNone(result['wgs84'])
        self.assertNotIn('enu_m', result)
        np.testing.assert_allclose(result['local_m'], query['points'], atol=1e-10)
        self.post(self.base+'/reason', {'as_of': NOW, 'registration_id': registration['id'],
                  'all_of': [{'relation': 'above', 'reference_entity_id': 'building-a'}]}, 422)
        bad = copy.deepcopy(payload)
        bad['origin'] = {'latitude': 0, 'longitude': 0}
        self.post(self.base+'/registrations', bad, 422)
        bad = copy.deepcopy(payload)
        bad['control_points'][0]['enu_m'] = [0, 0, 0]
        self.post(self.base+'/registrations', bad, 422)

    def test_registration_review_transform_and_independent_check(self):
        registration=self.post(self.base+'/registrations',registration_payload())
        endpoint=f'/spatial/registrations/{registration["id"]}/transform'
        query={'as_of':NOW,'points':[[0,0,0],[100,0,0]]}
        self.post(endpoint,query,409)
        self.approve(registration['id'])
        transformed=self.post(endpoint,query)
        np.testing.assert_allclose(transformed['enu_m'],query['points'],atol=1e-10)
        self.assertAlmostEqual(transformed['wgs84'][1]['longitude'],.000898315,places=8)
        self.assertLess(transformed['check_rmse_m'],1e-10)
        self.post(endpoint,{'as_of':NOW,'points':[[10001,0,0]]},422)
        bad=registration_payload()
        bad['check_points'][0]['enu_m']=[2,2,3]
        self.post(self.base+'/registrations',bad,422)
        bad=registration_payload()
        bad['check_points'][0]['scene']=[0,0,0]
        self.post(self.base+'/registrations',bad,422)
        bad=registration_payload()
        bad['control_points']=[{'label':f'p{i}','scene':[i,0,0],'enu_m':[i,0,0]} for i in range(3)]
        self.post(self.base+'/registrations',bad,422)

    def test_similarity_rotation_units_and_polar_origin(self):
        payload=registration_payload()
        payload['scene_unit_m']=.01
        payload['solve_scale']=True
        rotation=np.array([[0,-1,0],[1,0,0],[0,0,1]])
        translation=np.array([10,20,30])
        for p in payload['control_points']+payload['check_points']:
            p['enu_m']=(rotation@np.array(p['scene'])*.02+translation).tolist()
        result=register(Registration.model_validate(payload))
        matrix=np.array(result['matrix_scene_to_enu'])
        np.testing.assert_allclose(matrix[:3,:3],rotation*.02,atol=1e-10)
        np.testing.assert_allclose(matrix[:3,3],translation,atol=1e-10)
        self.assertAlmostEqual(result['estimated_scale'],2)
        polar=enu_to_wgs84([[0,0,0]],{'latitude':90,'longitude':12},100)[0]
        self.assertAlmostEqual(polar['latitude'],90)
        self.assertAlmostEqual(polar['altitude_m'],100,places=5)

    def test_multihop_join_3d_and_road_proofs(self):
        relations=self.post(self.base+'/relations',{**VALIDITY,'relations':[
            {'subject':'entrance-near','predicate':'inside','object':'entrance-far','source_note':'Synthetic containment'},
            {'subject':'entrance-far','predicate':'inside','object':'building-a','source_note':'Synthetic containment'}]})['id']
        registration=self.post(self.base+'/registrations',registration_payload())['id']
        network=self.post(self.base+'/networks',network_payload())['id']
        for identifier in (relations,registration,network):self.approve(identifier)
        query={'as_of':NOW,'kind':'entrance','relation_set_id':relations,'registration_id':registration,'network_id':network,
               'all_of':[{'relation':'inside','reference_entity_id':'building-a'},
                         {'relation':'near','reference_entity_id':'building-a','distance_m':100},
                         {'relation':'above','reference_entity_id':'building-a'},
                         {'relation':'reachable_from','reference_entity_id':'building-a'}]}
        result=self.post(self.base+'/reason',query)
        self.assertEqual([m['entity_id'] for m in result['matches']],['entrance-near'])
        self.assertEqual(len(result['matches'][0]['proofs'][0]['path']),2)
        self.assertEqual(len(result['artifact_citations']),3)
        self.assertFalse(self.post(self.base+'/reason',{**query,'max_hops':1})['matches'])
        self.post(f'/spatial/artifacts/{relations}/withdraw',{'reviewer':'test','note':'No longer valid'})
        self.post(self.base+'/reason',query,409)

    def test_cycles_nontransitive_blocks_missing_coordinates_and_validation(self):
        relations=[{'subject':'entrance-near','predicate':'inside','object':'building-a','source_note':'test'},
                   {'subject':'building-a','predicate':'part_of','object':'entrance-near','source_note':'test'}]
        self.post(self.base+'/relations',{**VALIDITY,'relations':relations},422)
        relations=[{'subject':'entrance-near','predicate':'blocks','object':'entrance-far','source_note':'test'},
                   {'subject':'entrance-far','predicate':'blocks','object':'building-a','source_note':'test'}]
        identifier=self.post(self.base+'/relations',{**VALIDITY,'relations':relations})['id']
        self.approve(identifier)
        query={'as_of':NOW,'relation_set_id':identifier,'all_of':[{'relation':'blocks','reference_entity_id':'building-a'}]}
        self.assertEqual([m['entity_id'] for m in self.post(self.base+'/reason',query)['matches']],['entrance-far'])
        query={'as_of':NOW,'kind':'entrance','all_of':[{'relation':'near','reference_entity_id':'building-a','distance_m':100}]}
        self.assertIn('entrance-unlocated',self.post(self.base+'/reason',query)['unknown_entities'])
        self.post(self.base+'/reason',{**query,'all_of':[{'relation':'above','reference_entity_id':'building-a'}]},422)
        self.post(self.base+'/reason',{**query,'all_of':[{'relation':'near','reference_entity_id':'building-a'}]},422)

    def test_natural_reasoning_is_validated_and_uses_deterministic_proofs(self):
        intent=ReasonIntent.model_validate({'query':{'as_of':NOW,'kind':'entrance',
            'all_of':[{'relation':'near','reference_entity_id':'building-a','distance_m':100}]},'clarification':None})
        with patch('app.geometry.vision.interpret_relations',return_value=(intent,{})):
            result=self.post(self.base+'/reason/ask',{'question':'A楼100米内有哪些入口？'})
        self.assertEqual(result['status'],'answered')
        self.assertEqual(result['evidence']['matches'][0]['entity_id'],'entrance-near')
        self.assertEqual(self.client.get('/spatial/runs/'+result['run_id']).status_code,200)
        intent=ReasonIntent(query=None,clarification='请指定距离范围')
        with patch('app.geometry.vision.interpret_relations',return_value=(intent,{})):
            self.assertEqual(self.post(self.base+'/reason/ask',{'question':'附近有什么？'})['status'],'clarification_needed')

    def test_withdrawn_linked_evidence_disables_route_and_relation(self):
        image=self.post(self.base+'/images',{'name':'synthetic.png','captured_at':NOW,'source':'Synthetic',
            'evidence_basis':'exercise','mime_type':'image/png','content_base64':base64.b64encode(diagram_png()).decode()})['id']
        annotation=self.post(self.base+'/annotations',{'image_id':image,'source_note':'Synthetic',
            'annotation':{'entity_id':'entrance-near','observation':'no_obstacle_visible','description':'Test only',
                          'bbox':{'x_min':0,'y_min':0,'x_max':1,'y_max':1},'confidence':.5}})['id']
        network=network_payload()
        network['edges'][1]['annotation_ids']=[annotation]
        network_id=self.post(self.base+'/networks',network)['id']
        relations=self.post(self.base+'/relations',{**VALIDITY,'relations':[
            {'subject':'entrance-near','predicate':'part_of','object':'building-a',
             'source_note':'Synthetic','annotation_ids':[annotation]}]})['id']
        for identifier in (network_id,relations):self.approve(identifier)
        route={'network_id':network_id,'as_of':NOW,'start_entity_id':'building-a','end_entity_id':'entrance-far'}
        query={'relation_set_id':relations,'as_of':NOW,'all_of':[{'relation':'part_of','reference_entity_id':'building-a'}]}
        self.assertEqual(self.post(self.base+'/route',route)['status'],'unreachable')
        self.assertFalse(self.post(self.base+'/reason',query)['matches'])
        self.post(f'/spatial/annotations/{annotation}/review',{'reviewer':'test','action':'approve','note':'Synthetic'})
        self.assertEqual(self.post(self.base+'/route',route)['status'],'reachable')
        matched=self.post(self.base+'/reason',query)['matches']
        self.assertEqual(matched[0]['image_citations'][0]['annotation_id'],annotation)
        self.post(f'/spatial/annotations/{annotation}/withdraw',{'reviewer':'test','note':'Withdraw source'})
        self.assertEqual(self.post(self.base+'/route',route)['status'],'unreachable')
        self.assertFalse(self.post(self.base+'/reason',query)['matches'])

    def test_natural_reasoning_refuses_silently_dropped_conditions(self):
        intent=ReasonIntent.model_validate({'query':{'as_of':NOW,'kind':'entrance',
            'all_of':[{'relation':'near','reference_entity_id':'building-a','distance_m':100}]},'clarification':None})
        with patch('app.geometry.vision.interpret_relations',return_value=(intent,{})),patch('app.geometry.reason') as execute:
            result=self.post(self.base+'/reason/ask',{'question':'A楼100米内，属于A楼、位于A楼上方且可步行到达的入口？'})
        self.assertEqual(result['status'],'clarification_needed')
        self.assertEqual(result['missing_conditions'],['above','part_of','reachable_from'])
        execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
