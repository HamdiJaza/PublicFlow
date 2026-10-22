"""Final offline regressions and delivered-file integrity; never calls a model."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import unittest

from common import ROOT,RUNTIME,GENERATION_MODEL


def python_suite():
    """Use inherited workspace ACLs for synthetic fixtures in restricted Windows sessions."""
    scratch=(ROOT/'.runtime/offline-test-temp').resolve()
    scratch.mkdir(parents=True,exist_ok=True)
    if os.name=='nt':
        def fixture_directory(suffix=None,prefix=None,dir=None):
            base=Path(dir or scratch).resolve()
            if not base.is_relative_to(scratch):raise ValueError('Test fixture directory escapes project scratch storage')
            name=(prefix or 'tmp')+secrets.token_hex(16)+(suffix or '')
            target=(base/name).resolve()
            if target.parent!=base:raise ValueError('Invalid test fixture name')
            # Python's private 0700 ACL omits the restricted session capability.
            # This affects only synthetic unit fixtures, never product storage.
            target.mkdir()
            return str(target)
        tempfile.mkdtemp=fixture_directory
    sys.path.insert(0,str(Path.cwd()))
    suite=unittest.defaultTestLoader.discover(sys.argv[2],pattern=sys.argv[3])
    return int(not unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful())


def main():
    # Keep generated fixtures and their cleanup within the writable project.
    scratch=(ROOT/'.runtime/offline-test-temp').resolve()
    if not scratch.is_relative_to(ROOT.resolve()):raise RuntimeError('Test temporary path escapes the project')
    scratch.mkdir(parents=True,exist_ok=True)
    environment={**os.environ,'TMP':str(scratch),'TEMP':str(scratch)}
    commands=[
        ('Intake offline regressions',68,[str(ROOT/'.runtime/nvidia-intake-venv/Scripts/python.exe'),'-B',__file__,'--python-suite','intake-agent/tests','test_*.py'],ROOT),
        ('Media bridge regressions',6,[str(ROOT/'intake-agent/.venv/Scripts/python.exe'),'-B',__file__,'--python-suite','integration/vision','test_media_bridge.py'],ROOT),
        ('Existing Intake/Vision workflow',42,['node','n8n/vision-integration/tests/test_workflow.mjs'],ROOT),
        ('Multimedia workflow regressions',39,['node','n8n/vision-integration/tests/test_multimedia.mjs'],ROOT),
        ('Delivered RAG contract tests',5,[str(ROOT/'.runtime/knowledge-venv/Scripts/python.exe'),'-B',__file__,'--python-suite','tests','test_*.py'],RUNTIME),
        ('Knowledge evidence, download and live-validation tests',32,[str(ROOT/'.runtime/knowledge-venv/Scripts/python.exe'),'-B',__file__,'--python-suite','integration/knowledge','test_*.py'],ROOT),
        ('Knowledge workflow checks',45,['node','n8n/knowledge-integration/tests/test_workflow.mjs'],ROOT)]
    live_path=ROOT/'project-docs/integration/knowledge-live-qwen-3b-results.json'
    live=json.loads(live_path.read_text(encoding='utf-8')) if live_path.is_file() else None
    inference_verified=bool(live and not live.get('errors') and live.get('generation_calls',0)>0 and live.get('native_cases'))
    blockers=[]
    if not (RUNTIME/'data/index_structure.json').is_file():blockers.append('Fresh audited Qdrant index not built')
    if not inference_verified:blockers.append('Real retrieval/generation validation pending')
    blockers+=['Persistent tickets/review queue and web integration pending']
    report={'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'scope':'Offline checks and source hashes; not live retrieval or generation evidence',
        'municipality_scope':'Commune de Tunis (user confirmed); incident location not inferred','checks':[],
        'live_rag_inference_verified':inference_verified,'model_download_authorized':'BGE-M3 only; reuse delivered qwen2.5:3b already installed',
        'generation_model':GENERATION_MODEL,'remaining_blockers':blockers}
    for name,expected,command,directory in commands:
        result=subprocess.run(command,cwd=directory,env=environment,capture_output=True,text=True,timeout=180)
        output=result.stdout+'\n'+result.stderr
        found=re.search(r'Ran (\d+) tests',output) if '--python-suite' in command else re.search(r'All (\d+) ',output)
        count=int(found[1]) if found else None;passed=count==expected and result.returncode==0
        report['checks'].append({'name':name,'count':count,'exit_code':result.returncode,'passed':passed})
        print(name+': '+('PASS' if passed else 'FAIL')+' ('+str(count)+')',flush=True)
        if not passed:print(output[-3000:])
    baseline=json.loads((ROOT/'project-docs/integration/phase0-baseline.json').read_text(encoding='utf-8'))
    delivered=json.loads((ROOT/'project-docs/integration/knowledge-delivery-baseline.json').read_text(encoding='utf-8'))
    records=[(ROOT/r['path'],r['sha256']) for r in baseline['files']]+[(ROOT/'rag-agent/Knowledge_Agent'/r['path'],r['sha256']) for r in delivered['files']]
    bad=[str(path.relative_to(ROOT)) for path,expected in records if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected]
    report['original_delivery']={'earlier_files':len(baseline['files']),'rag_files':len(delivered['files']),'hash_mismatches':bad,'unchanged':not bad}
    report['offline_checks_passed']=all(r['passed'] for r in report['checks']) and not bad
    engine=ROOT/'project-docs/integration/knowledge-engine-results.json'
    if engine.is_file():
        actual=json.loads(engine.read_text(encoding='utf-8'))
        report['n8n_engine']={'cases':len(actual['cases']),'errors':actual['errors'],'scope':actual['scope'],'real_generation_calls':actual['real_generation_calls']}
    report['original_models_and_prompts']='Delivered files/prompts and runtime source copy unchanged; user-approved generation model overridden through environment only'
    (ROOT/'project-docs/integration/knowledge-verification-recovered-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'offline_checks_passed':report['offline_checks_passed'],'total_checks':sum(r['count'] or 0 for r in report['checks']),'originals_checked':len(records)}))
    return int(not report['offline_checks_passed'])


if __name__=='__main__':raise SystemExit(python_suite() if sys.argv[1:2]==['--python-suite'] else main())
