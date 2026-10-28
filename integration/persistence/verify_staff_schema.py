"""Exercise staff_schema.sql on a throwaway PostgreSQL container; live tickets are never touched.

Uses the cached postgres:17-alpine image (no download) and removes the container afterwards.
Run: .runtime/nvidia-intake-venv/Scripts/python.exe -B integration/persistence/verify_staff_schema.py
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
NAME = 'municipal-staff-schema-check-' + secrets.token_hex(4)
# The package passes its digest-pinned image; development uses the cached tag.
IMAGE = os.environ.get('MUNICIPAL_SCHEMA_CHECK_IMAGE', 'postgres:17-alpine')
CHECKS = []


def psql(sql):
    result = subprocess.run(['docker', 'exec', '-i', NAME, 'psql', '-X', '-q', '-At', '-U', 'municipal_admin',
                             '-d', 'municipal_tickets', '-v', 'ON_ERROR_STOP=1'],
                            input=sql, text=True, encoding='utf-8', capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def call(function, payload):
    return json.loads(psql(f"SELECT municipal.{function}($j${json.dumps(payload)}$j$::jsonb);"))


def check(name, condition):
    CHECKS.append((name, bool(condition)))
    print(('PASS ' if condition else 'FAIL ') + name)


def ticket(report_id, decision, category, organisation, commune=None):
    gates = {g: {'decision': 'PASS' if decision == 'PASS' else 'REVIEW', 'reason_codes': []} for g in ('gate_1', 'gate_2', 'gate_3')}
    location = {'address': 'Rue de Marseille'} | ({'commune': commune} if commune else {})
    return {'report_id': report_id, 'decision': decision, 'input_identity': {'original': report_id}, 'policy': gates, 'trace': [],
            'review_reasons': [] if decision == 'PASS' else ['VISION_UNCERTAINTY_REQUIRES_REVIEW'],
            'summary': 'Signalement de test', 'location': location, 'category': category, 'severity': 'MEDIUM',
            'department': 'X', 'organisation': organisation, 'priority': 'MEDIUM', 'knowledge': {'procedure': None, 'deadline': None}}


def staff(role, actor_org, action, **fields):
    return call('staff_api', {'action': action, 'actor': {'name': 'Agent ' + str(actor_org), 'role': role, 'organisation': actor_org}, **fields})


def main():
    subprocess.run(['docker', 'run', '-d', '--rm', '--pull', 'never', '--name', NAME, '-e', 'POSTGRES_USER=municipal_admin',
                    '-e', 'POSTGRES_PASSWORD=' + secrets.token_urlsafe(24), '-e', 'POSTGRES_DB=municipal_tickets', IMAGE],
                   check=True, capture_output=True)
    try:
        for _ in range(60):
            if subprocess.run(['docker', 'exec', NAME, 'pg_isready', '-U', 'municipal_admin', '-d', 'municipal_tickets'],
                              capture_output=True).returncode == 0:
                break
            time.sleep(1)
        time.sleep(2)  # the entrypoint restarts the server once after initialisation
        for _ in range(30):
            try:
                psql('SELECT 1;'); break
            except RuntimeError:
                time.sleep(1)
        psql((ROOT / 'integration/persistence/schema.sql').read_text(encoding='utf-8'))
        # A ticket saved before the migration must be backfilled, not lost.
        old = json.loads(psql("SELECT municipal.save_report($j$" + json.dumps(ticket('OLD-1', 'REVIEW', 'WATER_LEAK', None)) + "$j$::jsonb);"))
        staff_sql = (ROOT / 'integration/persistence/staff_schema.sql').read_text(encoding='utf-8')
        psql(staff_sql); psql(staff_sql)
        check('migration is idempotent', True)
        check('pre-migration ticket backfilled to SONEDE',
              psql(f"SELECT commune||','||organisation FROM municipal.tickets WHERE tracking_id='{old['tracking_id']}';") == 'COMMUNE_TUNIS,SONEDE')

        translated = {'en': 'Street light out', 'provider': 'nvidia'}
        review = call('save_report', ticket('RPT-review', 'REVIEW', 'STREET_LIGHTING', 'STEG', 'COMMUNE_TUNIS') | {'summary_translation': translated})
        passed = call('save_report', ticket('RPT-pass', 'PASS', 'ROAD_DAMAGE', 'SUPERVISING_COMMUNE'))
        check('review ticket routed: commune supervises, STEG proposed', (review['commune'], review['organisation'], review['status']) == ('COMMUNE_TUNIS', 'STEG', 'NEEDS_REVIEW'))
        check('missing commune falls back to demo commune; commune executes its own work',
              (passed['commune'], passed['organisation'], passed['status']) == ('COMMUNE_TUNIS', 'COMMUNE_TUNIS', 'OPEN'))
        check('unknown organisation is never trusted', call('save_report', ticket('RPT-bad', 'REVIEW', 'WASTE', 'HACKER_ORG'))['organisation'] is None)
        try:
            call('save_report', ticket('RPT-unverified', 'PASS', 'WASTE', 'SUPERVISING_COMMUNE') | {'review_reasons': ['X']})
            check('unverified PASS still refused', False)
        except RuntimeError as error:
            check('unverified PASS still refused', 'UNVERIFIED_TICKET_CANNOT_AUTO_PASS' in str(error))

        r, p = review['tracking_id'], passed['tracking_id']
        steg_list = staff('UTILITY', 'STEG', 'list')['tickets']
        check('STEG does not see tickets under review', all(t['tracking_id'] != r for t in steg_list))
        check('municipality sees all its tickets', {r, p} <= {t['tracking_id'] for t in staff('MUNICIPALITY', 'COMMUNE_TUNIS', 'list')['tickets']})
        check('STEG cannot open a ticket outside its scope', staff('UTILITY', 'STEG', 'detail', tracking_id=r)['error'] == 'TICKET_NOT_FOUND')
        check('STEG cannot approve', staff('UTILITY', 'STEG', 'approve', tracking_id=r, expected_version=1, note='essai', organisation='STEG')['error'] == 'TICKET_NOT_FOUND')
        check('staff detail carries the translation', staff('MUNICIPALITY', 'COMMUNE_TUNIS', 'detail', tracking_id=r)['ticket']['summary_translation'] == translated)
        check('citizen view carries the English summary', json.loads(psql(f"SELECT municipal.ticket_status('{r}');"))['summary_en'] == 'Street light out')
        check('note is mandatory', staff('MUNICIPALITY', 'COMMUNE_TUNIS', 'approve', tracking_id=r, expected_version=1, note='ok',
                                         organisation='STEG')['error'] == 'NOTE_REQUIRED')

        approved = staff('MUNICIPALITY', 'COMMUNE_TUNIS', 'approve', tracking_id=r, expected_version=1, note='Photo vérifiée sur place',
                         organisation='STEG', severity='HIGH', public_note='Transmis à la STEG.')
        t = approved['ticket']
        check('approve: OPEN at STEG, corrected severity and priority', (t['status'], t['organisation'], t['severity'], t['priority'], t['version']) == ('OPEN', 'STEG', 'HIGH', 'HIGH', 2))
        check('AI output kept beside the correction', t['ai_classification']['severity'] == 'MEDIUM' and t['review']['status'] == 'RESOLVED')
        check('stale version refused', staff('MUNICIPALITY', 'COMMUNE_TUNIS', 'reassign', tracking_id=r, expected_version=1,
                                             note='Réaffectation', organisation='SONEDE')['error'] == 'VERSION_CONFLICT')
        check('SONEDE cannot see STEG work', staff('UTILITY', 'SONEDE', 'detail', tracking_id=r)['error'] == 'TICKET_NOT_FOUND')

        check('seeded commune cannot be added twice', staff('ADMIN', None, 'add_commune', code='COMMUNE_ARIANA', name_fr='Doublon', name_en='Duplicate')['error'] == 'COMMUNE_EXISTS')
        # Fictitious commune, only inside this throwaway database.
        check('English name is required for a new municipality', staff('ADMIN', None, 'add_commune', code='COMMUNE_TEST_ONLY', name_fr='Commune de test')['error'] == 'COMMUNE_INVALID')
        staff('ADMIN', None, 'add_commune', code='COMMUNE_TEST_ONLY', name_fr='Commune de test', name_en='Test municipality', region='GRAND_TUNIS')
        check('a commune cannot assign work to another commune', staff('MUNICIPALITY', 'COMMUNE_TUNIS', 'reassign', tracking_id=r, expected_version=2,
                                                                     note='Mauvaise commune', organisation='COMMUNE_ARIANA')['error'] == 'ORGANISATION_INVALID')
        check('Ariana does not see Tunis tickets', staff('MUNICIPALITY', 'COMMUNE_ARIANA', 'list')['tickets'] == [])
        communes = json.loads(psql('SELECT municipal.public_communes();'))
        check('Grand Tunis communes listed for citizens', sorted(c['code'] for c in communes) == ['COMMUNE_ARIANA', 'COMMUNE_BEN_AROUS', 'COMMUNE_TEST_ONLY', 'COMMUNE_TUNIS']
              and all(c['region'] == 'GRAND_TUNIS' for c in communes)
              and {c['code']: c['name_en'] for c in communes}['COMMUNE_BEN_AROUS'] == 'Municipality of Ben Arous')

        check('STEG sees assigned work', any(x['tracking_id'] == r for x in staff('UTILITY', 'STEG', 'list')['tickets']))
        started = staff('UTILITY', 'STEG', 'start', tracking_id=r, expected_version=2, note='Équipe envoyée')['ticket']
        check('STEG starts work', started['status'] == 'IN_PROGRESS')
        check('done requires IN_PROGRESS (no double close)', staff('UTILITY', 'STEG', 'start', tracking_id=r, expected_version=3,
                                                                   note='Encore')['error'] == 'INVALID_STATUS_TRANSITION')
        done = staff('UTILITY', 'STEG', 'done', tracking_id=r, expected_version=3, note='Lampe remplacée', public_note='Le lampadaire est réparé.')['ticket']
        check('STEG resolves', done['status'] == 'RESOLVED')
        public = json.loads(psql(f"SELECT municipal.ticket_status('{r}');"))
        statuses = [s['status'] for s in public['timeline']]
        check('citizen timeline follows the ticket', statuses == ['NEEDS_REVIEW', 'OPEN', 'IN_PROGRESS', 'RESOLVED'])
        check('citizen sees the public message only', public['timeline'][-1]['message'] == 'Le lampadaire est réparé.'
              and 'Lampe remplacée' not in json.dumps(public) and 'Agent' not in json.dumps(public))
        check('citizen sees English names', (public['organisation_name'], public['commune_name']) == ('STEG (electricity and gas)', 'Municipality of Tunis'))

        staff('MUNICIPALITY', 'COMMUNE_TUNIS', 'start', tracking_id=p, expected_version=1, note='Équipe voirie envoyée')
        back = staff('MUNICIPALITY', 'COMMUNE_TUNIS', 'not_done', tracking_id=p, expected_version=2, note='Chantier privé, pas de notre ressort')['ticket']
        check('not done returns to municipal review', back['status'] == 'NEEDS_REVIEW' and back['review']['reason_codes'] == ['EXECUTION_NOT_DONE'])
        comment = staff('UTILITY', 'STEG', 'comment', tracking_id=r, note='Pièce remplacée sous garantie')['ticket']
        check('comments are recorded without version change', comment['events'][-1]['event'] == 'COMMENT' and comment['version'] == 4)

        check('admin never sees ticket content', staff('ADMIN', None, 'detail', tracking_id=r)['error'] == 'STAFF_ACTION_FORBIDDEN'
              and staff('ADMIN', None, 'list')['error'] == 'STAFF_ACTION_FORBIDDEN')
        overview = staff('ADMIN', None, 'overview')
        # OLD-1, RPT-review, RPT-pass, RPT-bad; the unverified PASS was refused.
        check('admin overview counts only', overview['total'] == 4 and 'summary' not in json.dumps(overview))
        check('locked organisations cannot be disabled', staff('ADMIN', None, 'set_active', code='STEG', active=False)['error'] == 'ORGANISATION_LOCKED')
        check('malformed input is a clean error', staff('MUNICIPALITY', 'COMMUNE_TUNIS', 'approve', tracking_id=r,
                                                        expected_version='abc', note='Valeur invalide')['error'] == 'STAFF_REQUEST_INVALID')
        check('forged actor refused', staff('MUNICIPALITY', 'STEG', 'list')['error'] == 'STAFF_ACTOR_INVALID')
    finally:
        subprocess.run(['docker', 'rm', '-f', NAME], capture_output=True)
    failed = [name for name, ok in CHECKS if not ok]
    print(f'{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed on a throwaway database.')
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
