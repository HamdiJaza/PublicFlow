"""Prepare local secrets; --initialize applies schema to the isolated existing DB.

No model calls, downloads, existing container changes or credential output.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / '.runtime/persistence'
CONTAINER = os.environ.get('MUNICIPAL_POSTGRES_CONTAINER', 'municipal-ticket-postgres-dev')


def psql(sql):
    result = subprocess.run(['docker', 'exec', '-i', CONTAINER, 'psql', '-X', '-q',
        '-U', 'municipal_admin', '-d', 'municipal_tickets', '-v', 'ON_ERROR_STOP=1'],
        input=sql, text=True, encoding='utf-8', capture_output=True)
    if result.returncode:
        # Role SQL contains a secret; never include SQL or raw stderr in errors.
        raise RuntimeError('Database setup failed; no credentials included in this error.')


def prepare():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    passwords = {}
    for kind in ('admin', 'app'):
        path = RUNTIME / (kind + '-password.txt')
        if not path.exists():
            path.write_text(secrets.token_urlsafe(36), encoding='ascii')
        password = path.read_text(encoding='ascii').strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{40,100}', password):
            raise RuntimeError('Unexpected password file format; existing file preserved.')
        passwords[kind] = password
    credential = [{'id': 'municipalTicketsDev', 'name': 'Municipal PostgreSQL tickets (development)',
        'type': 'postgres', 'data': {'host': CONTAINER, 'port': 5432, 'database': 'municipal_tickets',
            'user': 'municipal_app', 'password': passwords['app'], 'ssl': 'disable',
            'maxConnections': 3, 'allowUnauthorizedCerts': False}}]
    (RUNTIME / 'n8n-credential.json').write_text(json.dumps(credential), encoding='utf-8')
    return passwords


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--initialize', action='store_true')
    args = parser.parse_args()
    passwords = prepare()
    if args.initialize:
        psql((ROOT / 'integration/persistence/schema.sql').read_text(encoding='utf-8'))
        psql("""DO $$ BEGIN
          IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='municipal_app') THEN
            CREATE ROLE municipal_app LOGIN;
          END IF;
        END $$;
        ALTER ROLE municipal_app NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '"""
             + passwords['app'] + """';
        GRANT CONNECT ON DATABASE municipal_tickets TO municipal_app;
        GRANT USAGE ON SCHEMA municipal TO municipal_app;
        GRANT EXECUTE ON FUNCTION municipal.save_report(jsonb),municipal.ticket_status(text) TO municipal_app;
        """)
        print('Schema initialized. n8n has function-only access; status changes remain administrator-only.')
    else:
        print('Ignored local credentials prepared; no containers or database were changed.')


if __name__ == '__main__':
    main()
