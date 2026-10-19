"""Offline, temporary team demo: registration, blocked roads and multi-hop evidence."""
import hashlib
import argparse
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-question', action='store_true', help='Call the configured question model (may incur fees)')
    args = parser.parse_args()
    source = Path(__file__).parent
    ds = json.loads((source/'spatial_dataset.json').read_text(encoding='utf-8'))
    fixtures = json.loads((source/'spatial_extensions.json').read_text(encoding='utf-8'))
    now = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory() as folder:
        config = Path(folder)/'access.json'
        config.write_text(json.dumps({'users': [
            {'user_id': role, 'workspace': 'demo', 'role': role,
             'token_sha256': hashlib.sha256(f'demo-{role}'.encode()).hexdigest()}
            for role in ('contributor','reviewer','viewer')]}), encoding='utf-8')
        with TestClient(create_app(Path(folder)/'demo.db', mode='team', access_config=config)) as client:
            def post(url, body, role='contributor'):
                response = client.post(url,json=body,headers={'Authorization':f'Bearer demo-{role}'})
                if not response.is_success:
                    raise RuntimeError(f'{response.status_code}: {response.text}')
                response.raise_for_status()
                return response.json()

            identifier = post('/spatial/datasets',ds)['id']
            base = f'/spatial/datasets/{identifier}'
            ids = {}
            for name, endpoint in (('network','networks'),('registration','registrations'),('relations','relations')):
                payload = fixtures[name]
                payload['valid_from'] = (now-timedelta(hours=1)).isoformat()
                payload['valid_until'] = (now+timedelta(hours=24)).isoformat()
                ids[name] = post(base+'/'+endpoint,payload)['id']
                post(f'/spatial/artifacts/{ids[name]}/review',{'action':'approve','note':'合成演练审核'},'reviewer')
            route_query = {'network_id':ids['network'],'start_entity_id':'building-a','end_entity_id':'entrance-far',
                           'as_of':now.isoformat()}
            route = post(base+'/route',route_query,'viewer')
            assert route['distance_m'] == 260
            transformed = post(f'/spatial/registrations/{ids["registration"]}/transform',
                               {'points':[[55,0,6]],'as_of':now.isoformat()},'viewer')
            result = post(base+'/reason',{'kind':'entrance','as_of':now.isoformat(),
                'relation_set_id':ids['relations'],'network_id':ids['network'],'registration_id':ids['registration'],
                'all_of':[{'relation':'near','reference_entity_id':'building-a','distance_m':100},
                          {'relation':'part_of','reference_entity_id':'building-a'},
                          {'relation':'above','reference_entity_id':'building-a'},
                          {'relation':'reachable_from','reference_entity_id':'building-a'}]},'viewer')
            assert [m['entity_id'] for m in result['matches']] == ['entrance-near']
            natural = None
            if args.live_question:
                natural = post(base+'/reason/ask', {'question': 'A楼100米内，属于A楼、位于A楼上方且可以从A楼步行到达的入口有哪些？'}, 'viewer')
                assert natural['status'] == 'answered', natural
                assert {c['relation'] for c in natural['evidence']['query']['all_of']} == {'near','part_of','above','reachable_from'}, natural
                assert [m['entity_id'] for m in natural['evidence']['matches']] == ['entrance-near'], natural
            post(f'/spatial/artifacts/{ids["network"]}/withdraw',{'reviewer':'ignored','note':'演练道路状态变化'},'reviewer')
            invalidated = client.post(base+'/route',json=route_query,headers={'Authorization':'Bearer demo-viewer'})
            assert invalidated.status_code == 409
            print(json.dumps({'mode':'synthetic_offline_team_demo','detour_m':route['distance_m'],
                              'transformed':transformed, 'reasoning':result, 'natural_question': natural,
                              'withdrawn_network_status':409},
                             ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
