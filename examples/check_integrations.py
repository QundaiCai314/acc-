"""Explicit live provider probe; may incur provider charges. Uses synthetic input only."""
import argparse
import json
from datetime import datetime, timezone

from fastapi import HTTPException

from app.integrations import ProbeInput, probe


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('provider',choices=['vision','question','anysearch','all'])
    args=parser.parse_args()
    providers=['vision','question','anysearch'] if args.provider=='all' else [args.provider]
    failed=False
    for provider in providers:
        try:
            result=probe(ProbeInput(provider=provider))
            failed |= result['status'] != 'verified'
        except HTTPException as exc:
            failed=True
            result={'provider':provider,'status':'failed','http_status':exc.status_code,'detail':exc.detail}
        print(json.dumps({'checked_at':datetime.now(timezone.utc).isoformat(),**result},ensure_ascii=False),flush=True)
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
