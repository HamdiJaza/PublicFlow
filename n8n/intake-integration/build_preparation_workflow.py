"""New development workflow; preserve both delivered and validated legacy exports."""

import hashlib
import json

from build_workflow import HERE, ROOT, build


def build_preparation():
    workflow = build()
    workflow['id'] = 'municipalPreparedIntakeDev'
    workflow['name'] = 'Municipal - Preparation Intake - DEVELOPMENT ONLY'
    nodes = {node['name']: node for node in workflow['nodes']}
    webhook = nodes['Citizen Webhook']
    webhook['parameters']['path'] = 'municipal-prepared-intake'
    webhook['webhookId'] = 'municipal-prepared-intake-development'
    nodes['HTTP Intake']['parameters']['url'] = 'http://host.docker.internal:8012/analyser'
    lock = json.loads((ROOT/'intake-agent/assets.lock.json').read_text(encoding='utf-8'))
    config = {
        'trusted_safe_root': (ROOT/'.runtime/intake/safe').as_posix(),
        'privacy_invariant': 'checked_yunet_output_v1',
        'yunet_model_sha256': lock['yunet']['sha256'],
        'local_source_sha256': hashlib.sha256(b''.join(p.read_bytes() for p in sorted((ROOT/'intake-agent/local_intake').glob('*.py')))).hexdigest(),
    }
    nodes['Input Check']['parameters']['jsCode'] = (HERE/'nodes/input.js').read_text(encoding='utf-8').replace('__INTEGRATION_CONFIG__', json.dumps(config))
    nodes['Gate 1 - Intake']['parameters']['jsCode'] = (HERE/'nodes/gate1-preparation.js').read_text(encoding='utf-8')
    nodes['Format API Response']['parameters']['jsCode'] = nodes['Format API Response']['parameters']['jsCode'].replace("orchestrator:'intake-integration-v1'", "orchestrator:'intake-preparation-v1'")
    workflow['meta']['intake_contract'] = 'intake-preparation-v1'
    return workflow


if __name__ == '__main__':
    target = HERE/'municipal-prepared-intake-development.json'
    target.write_text(json.dumps(build_preparation(), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Built preparation-only workflow:', target.name)
