"""Relocatable Windows setup: packaged libraries, fresh secrets and native n8n CLI.

--local-only performs offline preparation without Docker, models or network.
--containers-only validates a fresh isolated backend without calling AI providers.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import venv

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
ENVS = ('nvidia-intake-venv', 'vision-venv', 'knowledge-venv')
COMPOSE = ['docker', 'compose', '-f', str(ROOT / 'distribution/compose.yaml')]
# Bump when staff_schema.sql or the staff/citizen workflows change: the upgrade then reruns once.
STAFF_VERSION = 4


def run(args, *, capture=False, **kwargs):
    result = subprocess.run([str(a) for a in args], cwd=ROOT, text=True,
                            encoding='utf-8', errors='replace', capture_output=capture, **kwargs)
    if result.returncode:
        raise RuntimeError('Command failed: ' + str(args[0]) + ' (exit ' + str(result.returncode) + ')')
    return result.stdout if capture else None


def python(name):
    return RUNTIME / name / 'Scripts/python.exe'


def verify_manifest():
    print('Checking package integrity...', flush=True)
    manifest = json.loads((ROOT / 'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
    checked_directories = set()
    for record in manifest['files']:
        relative = Path(record['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise RuntimeError('Invalid package manifest path')
        path = ROOT / relative
        if path.parent not in checked_directories:
            if not path.parent.resolve().is_relative_to(ROOT):
                raise RuntimeError('Linked package directory outside root')
            checked_directories.add(path.parent)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('Missing package file: ' + record['path'])
        if hashlib.file_digest(path.open('rb'), 'sha256').hexdigest() != record['sha256']:
            raise RuntimeError('Package file changed: ' + record['path'])


def local():
    RUNTIME.mkdir(exist_ok=True)
    (ROOT / 'project-docs/integration').mkdir(parents=True, exist_ok=True)
    verify_manifest()
    for name in ENVS:
        destination = RUNTIME / name
        # Only regenerate launchers/config; never clear the environment or data.
        cfg = destination / 'pyvenv.cfg'
        expected_home = 'home = ' + str(Path(sys.executable).parent)
        if not cfg.exists() or expected_home not in cfg.read_text(encoding='utf-8') or not python(name).exists():
            venv.EnvBuilder(with_pip=False, clear=False).create(destination)
        vendor = ROOT / 'vendor' / name / 'site-packages'
        pth = destination / 'Lib/site-packages/municipal-vendor.pth'
        pth.write_text('import site; site.addsitedir(' + repr(str(vendor)) + ')\n', encoding='utf-8')
    for filename in ('ffmpeg.exe', 'ffprobe.exe', 'yunet.onnx'):
        destination = RUNTIME / 'tools' / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copyfile(ROOT / 'vendor/media' / filename, destination)
    lock = json.loads((ROOT / 'intake-agent/assets.lock.json').read_text())
    for filename, expected in dict(lock['binary_sha256'], **{'yunet.onnx': lock['yunet']['sha256']}).items():
        if hashlib.file_digest((RUNTIME / 'tools' / filename).open('rb'), 'sha256').hexdigest() != expected:
            raise RuntimeError('Media asset checksum mismatch: ' + filename)
    # Only the four public tokenizer files and its cache reference, never weights or tokens.
    shutil.copytree(ROOT / 'vendor/huggingface', RUNTIME / 'huggingface', dirs_exist_ok=True)
    run([python(ENVS[0]), '-B', ROOT / 'distribution/smoke.py', 'intake'])
    run([python(ENVS[1]), '-B', ROOT / 'distribution/smoke.py', 'vision'])
    run([python(ENVS[2]), '-B', ROOT / 'distribution/smoke.py', 'knowledge'])
    for script in ('integration/persistence/setup.py', 'integration/vision/media_bridge.py',
                   'n8n/vision-integration/build_workflow.py', 'n8n/completion-integration/build_workflow.py',
                   'n8n/staff-integration/build_workflow.py', 'integration/translation/translation_bridge.py'):
        run([python(ENVS[0]), '-B', ROOT / script])
    run([python(ENVS[2]), '-B', ROOT / 'integration/knowledge/common.py'])
    run([python(ENVS[2]), '-B', ROOT / 'integration/knowledge/evidence_bridge.py'])
    print('Offline setup passed: three native agent environments and relocated workflow.', flush=True)


def fetch(url, data=None, *, allow_notfound=False):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=4) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if allow_notfound and error.code == 404:
            return json.load(error)
        raise


def occupied(port):
    with socket.socket() as sock:
        sock.settimeout(.3)
        return sock.connect_ex(('127.0.0.1', port)) == 0


def container_name(service):
    return os.environ['MUNICIPAL_N8N_CONTAINER' if service == 'n8n' else 'MUNICIPAL_POSTGRES_CONTAINER']


def check_ownership():
    run(['docker', 'info', '--format', '{{.ServerVersion}}'])
    for service, port in (('n8n', int(os.getenv('MUNICIPAL_N8N_PORT', '5679'))),
                          ('postgres', int(os.getenv('MUNICIPAL_POSTGRES_PORT', '5434')))):
        result = subprocess.run(['docker', 'inspect', container_name(service)], capture_output=True, text=True)
        if not result.returncode:
            item = json.loads(result.stdout)[0]
            if item['Config'].get('Labels', {}).get('municipal.package.root') != str(ROOT):
                raise RuntimeError('Container belongs to another installation: ' + container_name(service))
        elif occupied(port):
            raise RuntimeError(f'Port {port} is already occupied. Close the other municipal installation first.')
    project = os.getenv('COMPOSE_PROJECT_NAME', 'municipalite-auto')
    for suffix in ('n8n_data', 'ticket_data'):
        result = subprocess.run(['docker', 'volume', 'inspect', project + '_' + suffix], capture_output=True, text=True)
        if not result.returncode:
            labels = json.loads(result.stdout)[0].get('Labels') or {}
            if labels.get('municipal.package.root') != str(ROOT):
                raise RuntimeError('Existing data belongs to another folder. Use its original launcher; data was preserved.')


def preflight_models():
    if not shutil.which('ollama'):
        raise RuntimeError('Ollama is not on PATH. Install/start Ollama, then reopen the launcher.')
    try:
        names = {m['name'] for m in fetch('http://127.0.0.1:11434/api/tags')['models']}
    except Exception:
        raise RuntimeError('Start the existing Ollama application on port 11434, then retry.') from None
    missing = {'qwen2.5vl:3b', 'qwen2.5:3b', 'bge-m3:latest'} - names
    if missing:
        raise RuntimeError('Required local models missing: ' + ', '.join(sorted(missing)) + '. No models were downloaded.')
    if not (RUNTIME / 'distribution/ready.json').exists():
        for port in (8010, 8012, 8013, 8014, 8020, 8021, 8090, 8091):
            if occupied(port):
                raise RuntimeError(f'Port {port} is occupied by an earlier service. Stop it before first launch.')


def import_n8n(command, path=None, workflow_id='municipalCompletionDev'):
    args = COMPOSE + ['run', '--rm', '--no-deps']
    if path:
        args += ['-v', str(path.resolve()).replace('\\', '/') + ':/package-input.json:ro']
    args += ['n8n', command]
    args += ['--input=/package-input.json'] if path else ['--id=' + workflow_id]
    output = run(args, capture=True)
    # n8n's import handler can report an error with a zero exit code.
    if command.startswith('import:') and 'Successfully imported' not in output:
        raise RuntimeError('n8n ' + command + ' did not confirm success. No ready marker was written.')
    if command.startswith('publish:') and ('error' in output.lower() or 'publish' not in output.lower()):
        raise RuntimeError('n8n publication was not confirmed.')
    print('n8n: ' + command + ' completed.', flush=True)


def staff_console():
    """Staff console upgrade; also runs once on installations prepared before it existed.

    Every step is idempotent (additive migration, credential and workflow imports by id).
    The marker is written only after the published communes webhook answers from PostgreSQL.
    """
    marker = RUNTIME / 'distribution/staff-ready.json'
    if marker.exists() and json.loads(marker.read_text(encoding='utf-8')).get('version') == STAFF_VERSION:
        return
    print('Installing the staff console: additive database migration and staff workflow.', flush=True)
    # Rehearse the migration on a throwaway container from the same pinned image before the live database.
    image = re.search(r'image:\s*(postgres@sha256:[a-f0-9]{64})', (ROOT / 'distribution/compose.yaml').read_text(encoding='utf-8')).group(1)
    run([python(ENVS[0]), '-B', ROOT / 'integration/persistence/verify_staff_schema.py'], env=os.environ | {'MUNICIPAL_SCHEMA_CHECK_IMAGE': image})
    run([python(ENVS[0]), '-B', ROOT / 'integration/persistence/setup.py', '--initialize'])
    run(COMPOSE + ['stop', 'n8n'])
    try:
        import_n8n('import:credentials', RUNTIME / 'persistence/n8n-credential.json')
        import_n8n('import:credentials', RUNTIME / 'translation-bridge/n8n-credential.json')
        # The citizen workflow changed too (commune field, executing organisation).
        import_n8n('import:workflow', ROOT / 'n8n/completion-integration/municipal-completion-development.json')
        import_n8n('import:workflow', ROOT / 'n8n/staff-integration/municipal-staff-development.json')
        import_n8n('publish:workflow')
        import_n8n('publish:workflow', workflow_id='municipalStaffDev')
    finally:
        run(COMPOSE + ['up', '-d', 'n8n'])
    base = 'http://127.0.0.1:' + os.getenv('MUNICIPAL_N8N_PORT', '5679')
    for _ in range(90):
        try:
            if isinstance(fetch(base + '/webhook/municipal-communes').get('communes'), list):
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        raise RuntimeError('The staff workflow did not answer from the database. Inspect Docker logs; setup can be retried.')
    marker.write_text(json.dumps({'root': str(ROOT), 'version': STAFF_VERSION, 'workflow_id': 'municipalStaffDev',
                                  'communes_lookup_verified': True}), encoding='utf-8')
    print('Staff console workflow published and verified.', flush=True)


def containers():
    check_ownership()
    marker = RUNTIME / 'distribution/ready.json'
    if marker.exists():
        run(COMPOSE + ['up', '-d', '--wait', '--wait-timeout', '120'])
        staff_console()
        return
    print('Starting isolated database; Docker downloads pinned images only if missing.', flush=True)
    run(COMPOSE + ['up', '-d', '--wait', '--wait-timeout', '120', 'postgres'])
    run([python(ENVS[0]), '-B', ROOT / 'integration/persistence/setup.py', '--initialize'])
    # First CLI run initializes n8n's own empty database and owner placeholder.
    # No existing account, encryption key, tickets or execution history is copied.
    run(COMPOSE + ['stop', 'n8n'])
    for path in ('media-bridge', 'knowledge-bridge', 'persistence'):
        import_n8n('import:credentials', RUNTIME / path / 'n8n-credential.json')
    try:
        import_n8n('import:workflow', ROOT / 'n8n/completion-integration/municipal-completion-development.json')
    except RuntimeError:
        # A re-run after a partial setup: the workflow is already imported and active; keep it.
        print('n8n: workflow already imported and active; kept as is.', flush=True)
    import_n8n('publish:workflow')
    run(COMPOSE + ['up', '-d', 'n8n'])
    base = 'http://127.0.0.1:' + os.getenv('MUNICIPAL_N8N_PORT', '5679')
    for _ in range(90):
        try:
            response = fetch(base + '/webhook/municipal-ticket-status?tracking_id=00000000-0000-0000-0000-000000000000', allow_notfound=True)
            if response == {'ticket': None, 'error': None}:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        raise RuntimeError('Published ticket lookup did not verify the database. Inspect Docker logs; setup can be retried.')
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({'root': str(ROOT), 'workflow_id': 'municipalCompletionDev',
                                 'database_lookup_verified': True}), encoding='utf-8')
    print('n8n workflow published and PostgreSQL lookup verified.', flush=True)
    staff_console()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-only', action='store_true')
    parser.add_argument('--containers-only', action='store_true')
    args = parser.parse_args()
    os.environ.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1',
                      MUNICIPAL_PACKAGE_ROOT=str(ROOT))
    os.environ.setdefault('MUNICIPAL_N8N_CONTAINER', 'municipalite-auto-n8n')
    os.environ.setdefault('MUNICIPAL_POSTGRES_CONTAINER', 'municipalite-auto-postgres')
    if not args.local_only:
        check_ownership()
        if not args.containers_only:
            preflight_models()
    local()
    if args.local_only:
        return
    if not args.containers_only:
        run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
             ROOT / 'integration/knowledge/Start_Knowledge_Ollama.ps1'])
        index = RUNTIME / 'knowledge-agent/Knowledge_Agent/data/index_structure.json'
        catalog = index.with_name('catalog_structure.json')
        fixed = index.with_name('catalog_fixed.json')
        if not all(path.exists() for path in (index, catalog, fixed)):
            print('Building native RAG indexes with the installed BGE-M3. This can take several minutes.', flush=True)
            run([python(ENVS[2]), '-B', ROOT / 'integration/knowledge/setup_resources.py'])
    containers()


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError) as error:
        print('SETUP STOPPED: ' + str(error), file=sys.stderr)
        sys.exit(1)
