"""Staff console workflow: one header-authenticated webhook calling municipal.staff_api.

Passwords never reach n8n: the staff console authenticates people and sends only
the agent name, role and organisation. The database enforces scope and transitions.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PG = {'postgres': {'id': 'municipalTicketsDev', 'name': 'Municipal PostgreSQL tickets (development)'}}


def build():
    nodes = [
        {'id': 'staff-webhook', 'name': 'Staff Webhook', 'type': 'n8n-nodes-base.webhook', 'typeVersion': 2.1,
         'position': [0, 0], 'webhookId': 'municipal-staff',
         'credentials': {'httpHeaderAuth': {'id': 'municipalStaffWebhook', 'name': 'Municipal staff console webhook (development)'}},
         'parameters': {'httpMethod': 'POST', 'path': 'municipal-staff', 'authentication': 'headerAuth',
                        'responseMode': 'responseNode', 'options': {}}},
        {'id': 'staff-request', 'name': 'Staff Request Check', 'type': 'n8n-nodes-base.code', 'typeVersion': 2,
         'position': [300, 0], 'parameters': {'mode': 'runOnceForAllItems',
                                              'jsCode': (HERE / 'nodes/request.js').read_text(encoding='utf-8')}},
        {'id': 'staff-valid', 'name': 'Request Valid?', 'type': 'n8n-nodes-base.if', 'typeVersion': 2, 'position': [600, 0],
         'parameters': {'conditions': {'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'strict', 'version': 2},
                        'combinator': 'and', 'conditions': [{'id': 'staff-valid', 'leftValue': '={{ $json.valid }}',
                        'rightValue': True, 'operator': {'type': 'boolean', 'operation': 'true', 'singleValue': True}}]}, 'options': {}}},
        {'id': 'staff-api', 'name': 'Staff API', 'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6, 'position': [900, -100],
         'retryOnFail': False, 'onError': 'continueRegularOutput', 'credentials': PG,
         'parameters': {'operation': 'executeQuery', 'query': 'SELECT municipal.staff_api($1::jsonb) AS result;',
                        'options': {'queryReplacement': '={{ [JSON.stringify($json.request)] }}',
                                    'connectionTimeout': 5, 'queryBatching': 'single'}}},
        {'id': 'staff-response', 'name': 'Staff Response', 'type': 'n8n-nodes-base.respondToWebhook', 'typeVersion': 1.4,
         'position': [1200, -100], 'parameters': {'respondWith': 'json',
            'responseBody': "={{ $json.result || {ok:false,error:'DATABASE_UNAVAILABLE'} }}",
            'options': {'responseCode': '={{ $json.result ? 200 : 503 }}'}}},
        {'id': 'staff-invalid', 'name': 'Invalid Staff Request', 'type': 'n8n-nodes-base.respondToWebhook', 'typeVersion': 1.4,
         'position': [900, 100], 'parameters': {'respondWith': 'json',
            'responseBody': "={{ {ok:false,error:'STAFF_REQUEST_INVALID'} }}", 'options': {'responseCode': 400}}},
        # Read-only, unauthenticated: the citizen form's commune list (names only).
        {'id': 'communes-webhook', 'name': 'Communes Webhook', 'type': 'n8n-nodes-base.webhook', 'typeVersion': 2.1,
         'position': [0, 400], 'webhookId': 'municipal-communes',
         'parameters': {'httpMethod': 'GET', 'path': 'municipal-communes', 'responseMode': 'responseNode', 'options': {}}},
        {'id': 'communes-list', 'name': 'List Communes', 'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6, 'position': [300, 400],
         'retryOnFail': False, 'onError': 'continueRegularOutput', 'credentials': PG,
         'parameters': {'operation': 'executeQuery', 'query': 'SELECT municipal.public_communes() AS communes;',
                        'options': {'connectionTimeout': 5}}},
        {'id': 'communes-response', 'name': 'Communes Response', 'type': 'n8n-nodes-base.respondToWebhook', 'typeVersion': 1.4,
         'position': [600, 400], 'parameters': {'respondWith': 'json',
            'responseBody': '={{ {communes: $json.communes || null} }}',
            'options': {'responseCode': '={{ $json.communes ? 200 : 503 }}'}}},
    ]
    edge = lambda name: {'node': name, 'type': 'main', 'index': 0}
    connections = {
        'Staff Webhook': {'main': [[edge('Staff Request Check')]]},
        'Staff Request Check': {'main': [[edge('Request Valid?')]]},
        'Request Valid?': {'main': [[edge('Staff API')], [edge('Invalid Staff Request')]]},
        'Staff API': {'main': [[edge('Staff Response')]]},
        'Communes Webhook': {'main': [[edge('List Communes')]]},
        'List Communes': {'main': [[edge('Communes Response')]]},
    }
    return {'name': 'Municipalité Automatisée - Console des responsables', 'nodes': nodes, 'connections': connections,
            'active': False, 'pinData': {}, 'tags': [], 'id': 'municipalStaffDev',
            # The audit trail is municipal.ticket_events; successful calls are not duplicated
            # into n8n history, which would copy citizen data on every list refresh.
            'settings': {'executionOrder': 'v1', 'timezone': 'Africa/Tunis', 'saveDataSuccessExecution': 'none',
                         'saveDataErrorExecution': 'all', 'saveManualExecutions': False},
            'meta': {'staff_contract': 'POST municipal-staff {action, actor{name,role,organisation}, ...}; header X-Staff-Secret',
                     'scope_policy': 'Enforced in municipal.staff_api: commune sees its tickets, STEG/SONEDE see assigned work, ADMIN sees no ticket content'}}


if __name__ == '__main__':
    (HERE / 'municipal-staff-development.json').write_text(json.dumps(build(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Built staff console workflow.')
