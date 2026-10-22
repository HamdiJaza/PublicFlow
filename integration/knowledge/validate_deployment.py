"""Exercise the published full workflow's ingress in n8n without making AI calls."""
from datetime import datetime, timezone
import json
import time
import uuid

import httpx

from common import ROOT

URL = 'http://127.0.0.1:5679/webhook/municipal-full-development'


def main():
    report = {
        'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Actual published full n8n workflow; deliberately invalid text-only submissions. No successful media processing or model inference is claimed.',
        'cases': [], 'errors': [],
    }
    try:
        with httpx.Client(timeout=15, trust_env=False) as http:
            registered = False
            for _ in range(120):
                try:
                    response = http.get(URL, timeout=2)
                    registered = 'Did you mean to make a POST request?' in response.json().get('message', '')
                except (httpx.HTTPError, ValueError):
                    pass
                if registered:
                    break
                time.sleep(.5)
            if not registered:
                raise RuntimeError('FULL_WORKFLOW_WEBHOOK_NOT_REGISTERED')
            for name, extra, expected_error in [
                ('missing_visual_evidence', {}, 'UNSUPPORTED_MEDIA_COMBINATION'),
                ('invalid_report_id', {'report_id': 'INVALID SPACE'}, 'INVALID_REPORT_ID'),
                ('unknown_field', {'unsupported_field': 'test'}, 'UNSUPPORTED_FORM_FIELD'),
            ]:
                body = {'report_id': 'RPT-INGRESS-' + uuid.uuid4().hex[:10],
                        'description': 'Integration test without media; reject before calling an agent.', **extra}
                response = http.post(URL, json=body)
                result = response.json()
                row = {'case': name, 'http_status': response.status_code, 'response': result}
                report['cases'].append(row)
                if response.status_code != 422 or result.get('decision') != 'REJECT' or expected_error not in result.get('errors', []):
                    raise RuntimeError(name.upper() + '_INCORRECT_REJECTION')
                if result.get('report_id') != body['report_id']:
                    raise RuntimeError('REPORT_ID_NOT_PRESERVED')
                if result.get('deployment', {}).get('orchestrator') != 'intake-vision-knowledge-v1':
                    raise RuntimeError('UNEXPECTED_DEPLOYED_WORKFLOW')
                if any(result.get('components', {}).get(stage, {}).get('execution') != 'not_called'
                       for stage in ['intake', 'vision', 'knowledge', 'persistence']):
                    raise RuntimeError('INVALID_INPUT_DID_NOT_STOP_BEFORE_AGENTS')
                if result.get('persisted') is not False or result.get('review_queued') is not False or result.get('ticket') is not None:
                    raise RuntimeError('FALSE_PERSISTENCE_CLAIM')
                row['passed'] = True
                print('PASS real n8n ingress: ' + name, flush=True)
    except Exception as error:
        report['errors'].append(str(error) if isinstance(error, RuntimeError) else type(error).__name__)
    report['passed'] = len(report['cases']) == 3 and not report['errors']
    target = ROOT / ('project-docs/integration/knowledge-deployment-' + uuid.uuid4().hex[:10] + '.json')
    with target.open('x', encoding='utf-8') as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps({'report': target.relative_to(ROOT).as_posix(), 'passed': report['passed'], 'errors': report['errors']}))
    return int(not report['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
