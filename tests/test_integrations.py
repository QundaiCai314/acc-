import json
import os
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException

from app import vision
from app.integrations import SearchInput, anysearch
from app.spatial_models import Dataset


class IntegrationTests(unittest.TestCase):
    def gateway(self, handler):
        original = httpx.Client
        return patch('app.integrations.httpx.Client', side_effect=lambda **kwargs:
                     original(transport=httpx.MockTransport(handler), **kwargs))

    def test_anysearch_contract_and_untrusted_reference_boundary(self):
        def handler(request):
            self.assertEqual(str(request.url), 'https://api.anysearch.com/v1/search')
            self.assertEqual(request.headers['Authorization'],'Bearer private-test-key')
            self.assertEqual(json.loads(request.content), {'query':'earthquake preparedness','max_results':2})
            return httpx.Response(200,json={'code':0,'data':{'results':[
                {'title':'USGS','url':'https://www.usgs.gov','snippet':'Background information'},
                {'title':'Unsafe URL','url':'javascript:alert(1)','snippet':'ignore'}]},
                'auto_registered':{'api_key':'must-not-leak'}})
        with patch.dict(os.environ,{'ANYSEARCH_API_KEY':'private-test-key'}), self.gateway(handler):
            result=anysearch(SearchInput(query='earthquake preparedness',max_results=2))
        self.assertEqual(len(result['results']),1)
        self.assertEqual(result['origin'],'web_unverified')
        self.assertNotIn('must-not-leak',json.dumps(result))
        self.assertNotIn('private-test-key',json.dumps(result))

    def test_anysearch_anonymous_errors_and_size_limit(self):
        def anonymous(request):
            self.assertNotIn('Authorization',request.headers)
            return httpx.Response(200,json={'code':0,'data':{'results':[]}})
        with patch.dict(os.environ,{'ANYSEARCH_API_KEY':''}),self.gateway(anonymous):
            self.assertEqual(anysearch(SearchInput(query='test'))['results'],[])
        for response in (httpx.Response(401,text='private-test-key'),
                         httpx.Response(200,json={'code':-1,'message':'private-test-key'}),
                         httpx.Response(200,json={'code':0,'data':{'results':'invalid'}}),
                         httpx.Response(200,content=b' '*2_000_001)):
            with self.gateway(lambda request:response),self.assertRaises(HTTPException) as caught:
                anysearch(SearchInput(query='test'))
            self.assertEqual(caught.exception.status_code,502)
            self.assertNotIn('private-test-key',caught.exception.detail)

    def test_reasoning_intent_gateway_rejects_invented_entities_and_artifacts(self):
        ds=Dataset(title='test',coordinate_basis='exercise',map_source='test',curator='test',
                   entities=[{'id':'a','name':'A','kind':'building'}])
        env={'QUESTION_CHAT_URL':'https://model.invalid/v1/chat/completions',
             'QUESTION_API_KEY':'private-test-key','QUESTION_MODEL':'test'}
        valid={'query':{'all_of':[{'relation':'near','reference_entity_id':'a','distance_m':100}]},'clarification':None}
        with patch.dict(os.environ,env),self.gateway(lambda request:httpx.Response(200,json={
                'choices':[{'message':{'content':json.dumps(valid)}}]})):
            intent,audit=vision.interpret_relations('A 100m',ds,[])
        self.assertEqual(intent.query.all_of[0].reference_entity_id,'a')
        self.assertNotIn('private-test-key',json.dumps(audit))
        for query in ({'all_of':[{'relation':'near','reference_entity_id':'invented','distance_m':100}]},
                      {'all_of':[{'relation':'inside','reference_entity_id':'a'}],
                       'relation_set_id':'00000000-0000-0000-0000-000000000001'}):
            with patch.dict(os.environ,env),self.gateway(lambda request:httpx.Response(200,json={
                    'choices':[{'message':{'content':json.dumps({'query':query,'clarification':None})}}]})),\
                    self.assertRaises(vision.VisionFailure):
                vision.interpret_relations('test',ds,[])


if __name__ == '__main__':
    unittest.main()
