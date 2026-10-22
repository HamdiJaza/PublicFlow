"""Build an explicit allowlist Windows package; never copy working credentials/data.

Run with the tested project's NVIDIA Python. --archive is optional until validation.
The archive contains only manifest entries, even after testing the staging folder.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'__pycache__', '.git', '.pytest_cache', '.venv', 'site-packages',
        'test', 'tests', 'idlelib', 'tkinter', 'turtledemo', 'ensurepip'}
SECRET = re.compile(rb'(?:nvapi-[A-Za-z0-9_-]{24,}|AIza[0-9A-Za-z_-]{30,}|sk-proj-[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def walk(folder, excluded=SKIP):
    # Prune cache/environment folders instead of traversing them.
    import os
    for base, folders, names in os.walk(folder):
        folders[:] = [name for name in folders if name not in excluded]
        for name in names:
            path = Path(base) / name
            if path.suffix not in {'.pyc', '.pyo'}:
                yield path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--reuse-vendor', action='store_true', help='Reuse previously staged vendor files; prepare.py still verifies all hashes.')
    args = parser.parse_args()
    stage = args.stage.resolve()
    if not stage.is_relative_to(ROOT.parent) or stage == ROOT.parent or stage.is_relative_to(ROOT):
        raise SystemExit('Staging must be a separate subfolder of the deep workspace.')
    if stage.exists() and any(stage.iterdir()) and not (stage / 'PACKAGE_MANIFEST.json').exists() and not (stage / '.package-build-marker').exists():
        raise SystemExit('Refusing a nonempty staging folder without a package manifest.')
    stage.mkdir(parents=True, exist_ok=True)
    (stage / '.package-build-marker').write_text(str(ROOT), encoding='utf-8')
    records = {}
    checked_directories = set()
    previous = {}
    if args.reuse_vendor and (stage / 'PACKAGE_MANIFEST.json').exists():
        previous = {r['path']: r for r in json.loads((stage / 'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))['files']}

    def add(source, relative, scan=True):
        source = Path(source)
        relative = Path(relative)
        if relative.is_absolute() or '..' in relative.parts:
            raise RuntimeError('Invalid package path')
        destination = stage / relative
        if destination.parent not in checked_directories:
            if not destination.parent.resolve().is_relative_to(stage):
                raise RuntimeError('Invalid package path')
            checked_directories.add(destination.parent)
        if destination.is_symlink():
            raise RuntimeError('Linked package file is not allowed')
        key = Path(relative).as_posix()
        if key.startswith('vendor/') and key in previous and destination.is_file():
            records[key] = previous[key]
            return
        if scan and SECRET.search(source.read_bytes()):
            raise RuntimeError('Secret-like content detected; excluded from export: ' + str(relative))
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = sha(source)
        if not destination.exists() or sha(destination) != digest:
            shutil.copyfile(source, destination)
        records[Path(relative).as_posix()] = {'path': Path(relative).as_posix(),
                                             'sha256': digest, 'bytes': source.stat().st_size}

    def tree(folder, target=None, scan=True):
        folder = Path(folder)
        target = Path(target) if target else folder.relative_to(ROOT)
        for source in walk(folder):
            add(source, target / source.relative_to(folder), scan)

    for filename in ('AGENTS.md', '.gitignore'):
        add(ROOT / filename, filename)
    for folder in ('intake-agent/local_intake', 'integration', 'distribution'):
        for source in walk(ROOT / folder):
            if source.name.startswith('test_'):
                continue  # Source-workspace tests can contain intentional fake credentials.
            if source.suffix in {'.py', '.ps1', '.txt', '.md', '.html', '.css', '.js', '.mjs', '.sql', '.yaml', '.cmd', '.svg'}:
                add(source, source.relative_to(ROOT))
    for filename in ('Start_NVIDIA_Intake.ps1', 'assets.lock.json', 'requirements-nvidia.txt'):
        add(ROOT / 'intake-agent' / filename, Path('intake-agent') / filename)
    for part in ('intake-integration', 'vision-integration', 'knowledge-integration', 'completion-integration'):
        for source in walk(ROOT / 'n8n' / part):
            if source.suffix in {'.py', '.js', '.mjs', '.md'}:
                add(source, source.relative_to(ROOT))
    base = Path('n8n/municipal-phase5/n8n/municipal-ticket-phase5.json')
    add(ROOT / base, base)
    vision = Path('vision-agent/Vision_Agent/02_VISION_PROJECT')
    for folder in ('agents', 'prompts', 'tests', 'docs'):
        tree(ROOT / vision / folder)
    for filename in ('README.md', 'requirements-vision.txt'):
        add(ROOT / vision / filename, vision / filename)
    rag = Path('rag-agent/Knowledge_Agent')
    inventory = json.loads((ROOT / rag / 'PACKAGE_CONTENTS.json').read_text(encoding='utf-8'))
    for record in inventory['files']:
        if sha(ROOT / rag / record['path']) != record['sha256']:
            raise RuntimeError('Original RAG delivery changed: ' + record['path'])
        add(ROOT / rag / record['path'], rag / record['path'])
    add(ROOT / rag / 'PACKAGE_CONTENTS.json', rag / 'PACKAGE_CONTENTS.json')
    for name in ('road-damage.jpg', 'description.txt'):
        add(ROOT / 'demo' / name, Path('demo') / name)
    add(ROOT / 'distribution/Start_MunicipaliteAuto.cmd', 'Start_MunicipaliteAuto.cmd')
    add(ROOT / 'distribution/README.txt', 'READ_ME_FIRST.txt')

    # Rehouse the already-tested CPython build as a normal relocatable layout.
    # No registry entries, system installer or pre-existing virtualenv paths.
    base = Path(sys._base_executable).resolve().parent
    stdlib = Path(__import__('os').__file__).resolve().parent
    for source in base.iterdir():
        if source.is_file() and (source.suffix in {'.dll', '.pyd'} or source.name in
                {'python.exe', 'pythonw.exe', 'venvlauncher.exe', 'venvwlauncher.exe', 'LICENSE.txt'}):
            if source.stem.endswith('_d') or source.stem.startswith(('_test', 'xx', '_ctypes_test')):
                continue
            add(source, Path('vendor/python') / source.name, scan=False)
    tree(stdlib, 'vendor/python/Lib', scan=False)
    for name in ('nvidia-intake-venv', 'vision-venv', 'knowledge-venv'):
        tree(ROOT / '.runtime' / name / 'Lib/site-packages', Path('vendor') / name / 'site-packages', scan=False)
    for name in ('yunet.onnx', 'ffmpeg.exe', 'ffprobe.exe'):
        add(ROOT / '.runtime/tools' / name, Path('vendor/media') / name, scan=False)
    with zipfile.ZipFile(ROOT / '.runtime/tools/ffmpeg-portable.zip') as media:
        for name in ('LICENSE', 'README.txt'):
            destination = stage / 'vendor/media' / ('FFmpeg-' + name)
            destination.write_bytes(media.read('ffmpeg-9.0.2-essentials_build/' + name))
            records[destination.relative_to(stage).as_posix()] = {
                'path': destination.relative_to(stage).as_posix(), 'sha256': sha(destination), 'bytes': destination.stat().st_size}
    hub = Path('hub/models--BAAI--bge-m3')
    commit = (ROOT / '.runtime/huggingface' / hub / 'refs/main').read_text().strip()
    for name in ('tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json', 'sentencepiece.bpe.model'):
        relative = hub / 'snapshots' / commit / name
        add(ROOT / '.runtime/huggingface' / relative, Path('vendor/huggingface') / relative, scan=False)
    add(ROOT / '.runtime/huggingface' / hub / 'refs/main', Path('vendor/huggingface') / hub / 'refs/main')
    manifest = {'format': 1, 'platform': 'Windows x64', 'python': sys.version,
                'scope': 'Runtime distribution; original member projects remain in the source workspace.',
                'excludes': ['credentials', 'NVIDIA key', 'DPAPI ciphertext', 'model weights', 'Qdrant index',
                             'live tickets', 'n8n accounts', 'execution history', 'uploaded media', 'runtime receipts'],
                'files': sorted(records.values(), key=lambda record: record['path'])}
    (stage / 'PACKAGE_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Staged {len(records)} allowlisted files, {sum(r["bytes"] for r in records.values()) / 2**20:.1f} MiB.', flush=True)
    if args.archive:
        args.archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for relative in [*records, 'PACKAGE_MANIFEST.json']:
                archive.write(stage / relative, 'MunicipaliteAuto/' + relative)
        digest = sha(args.archive)
        args.archive.with_suffix('.zip.sha256').write_text(digest + '  ' + args.archive.name + '\n', encoding='ascii')
        print(f'ZIP: {args.archive.name}; {args.archive.stat().st_size / 2**20:.1f} MiB; SHA256 {digest}')


if __name__ == '__main__':
    main()
