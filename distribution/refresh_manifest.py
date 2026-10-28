"""Refresh PACKAGE_MANIFEST.json after editing source files in an extracted package.

build_package.py needs the original build machine; this only re-hashes changed source
files and adds new ones, using the same allowlist. vendor/ entries are never modified.
Run: .runtime/nvidia-intake-venv/Scripts/python.exe -B distribution/refresh_manifest.py
"""
import hashlib
import json
from pathlib import Path
import shutil

from build_package import ROOT, SECRET, walk

SOURCE_SUFFIXES = {'.py', '.ps1', '.txt', '.md', '.html', '.css', '.js', '.mjs', '.sql', '.yaml', '.cmd', '.svg'}
N8N_PARTS = ('intake-integration', 'vision-integration', 'knowledge-integration', 'completion-integration', 'staff-integration')
# Root copies made by build_package.py.
COPIES = {'READ_ME_FIRST.txt': 'distribution/README.txt', 'Start_MunicipaliteAuto.cmd': 'distribution/Start_MunicipaliteAuto.cmd'}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def sources():
    for folder in ('integration', 'distribution'):
        for path in walk(ROOT / folder):
            if not path.name.startswith('test_') and path.suffix in SOURCE_SUFFIXES:
                yield path
    for part in N8N_PARTS:
        for path in walk(ROOT / 'n8n' / part):
            if path.suffix in {'.py', '.js', '.mjs', '.md'}:
                yield path
    for name in ('road-damage.jpg', 'description.txt', 'README.md', 'make_demo_cases.py'):
        yield ROOT / 'demo' / name
    yield from walk(ROOT / 'demo/cases')
    for name in ('AGENTS.md', '.gitignore', *COPIES):
        yield ROOT / name


def main():
    for copy, source in COPIES.items():
        if sha(ROOT / copy) != sha(ROOT / source):
            shutil.copyfile(ROOT / source, ROOT / copy)
    path = ROOT / 'PACKAGE_MANIFEST.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    records = {r['path']: r for r in manifest['files']}
    changed, added = [], []
    for source in sources():
        key = source.relative_to(ROOT).as_posix()
        if key.startswith('vendor/'):
            continue
        digest = sha(source)
        if key in records and records[key]['sha256'] == digest:
            continue
        if SECRET.search(source.read_bytes()):
            raise SystemExit('Secret-like content detected; manifest not written: ' + key)
        (changed if key in records else added).append(key)
        records[key] = {'path': key, 'sha256': digest, 'bytes': source.stat().st_size}
    missing = [k for k in records if not k.startswith('vendor/') and not (ROOT / k).is_file()]
    if missing:
        raise SystemExit('Manifest lists missing files; nothing written: ' + ', '.join(missing))
    manifest['files'] = sorted(records.values(), key=lambda r: r['path'])
    path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Manifest refreshed: {len(changed)} changed, {len(added)} added.')
    for key in changed:
        print('  changed ' + key)
    for key in added:
        print('  added   ' + key)


if __name__ == '__main__':
    main()
