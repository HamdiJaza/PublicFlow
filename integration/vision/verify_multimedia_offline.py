"""Run offline regressions and original-delivery integrity checks; no AI/network."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
TARGET=ROOT/'project-docs/integration/multimedia-offline-results.json'


def main():
    report={'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'scope':'Offline tests and original-delivery hashes; no AI accuracy claim','checks':[]}
    commands=[
        ('Intake regressions',68,[str(ROOT/'.runtime/nvidia-intake-venv/Scripts/python.exe'),'-B','-m','unittest','discover','-s','intake-agent/tests','-p','test_*.py','-q']),
        ('Verified-media bridge',6,[str(ROOT/'intake-agent/.venv/Scripts/python.exe'),'-B','-m','unittest','discover','-s','integration/vision','-p','test_media_bridge.py','-q']),
        ('Existing workflow checks',42,['node','n8n/vision-integration/tests/test_workflow.mjs']),
        ('Multimedia graph checks',39,['node','n8n/vision-integration/tests/test_multimedia.mjs'])]
    for name,expected,command in commands:
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=90)
        output=result.stdout+'\n'+result.stderr
        match=re.search(r'Ran (\d+) tests',output) if '-m' in command else re.search(r'All (\d+) ',output)
        count=int(match[1]) if match else None
        passed=result.returncode==0 and count==expected
        report['checks'].append({'name':name,'count':count,'exit_code':result.returncode,'passed':passed})
        print(name+': '+('PASS' if passed else 'FAIL')+' ('+str(count)+')',flush=True)
        if not passed:print(output[-3000:])
    baseline=json.loads((ROOT/'project-docs/integration/phase0-baseline.json').read_text(encoding='utf-8'))
    mismatches=[]
    for record in baseline['files']:
        path=ROOT/record['path']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:mismatches.append(record['path'])
    report['original_delivery']={'files_checked':len(baseline['files']),'hash_mismatches':mismatches,'unchanged':not mismatches}
    report['all_passed']=all(row['passed'] for row in report['checks']) and not mismatches
    TARGET.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':TARGET.relative_to(ROOT).as_posix(),'all_passed':report['all_passed'],'original_files':len(baseline['files'])}))
    return int(not report['all_passed'])


if __name__=='__main__':raise SystemExit(main())
