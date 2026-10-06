"""Refresh a selected shaft configuration without rewriting unchanged print meshes."""
import json
from pathlib import Path
from build_delivery import cli,ROOT,ASSEMBLIES

cli('gen',*[s+'.step.py' for s in ASSEMBLIES],'--write','--json')
path=ROOT/'Review'/'harness_validation.json'
checks=json.loads(path.read_text(encoding='utf-8'))
for item in checks:
    if item['name'] in ASSEMBLIES:
        item['result']=json.loads(cli('inspect','validate',item['name']+'.step.py'))
path.write_text(json.dumps(checks,indent=2),encoding='utf-8')
(ROOT/'Review'/'assembly_facts.json').write_text(cli('inspect','refs','LiftX_LH_Assembly.step.py','--facts','--planes','--positioning'),encoding='utf-8')
for job,out in [('assembly_snapshot.json','assembly_snapshot_results.json'),('parts_snapshot_jobs.json','parts_snapshot_results.json')]:
    shots=cli('snapshot','--job',ROOT/'Review'/job,'--json')
    (ROOT/'Review'/out).write_text(shots,encoding='utf-8')
print('Selected AXIS configuration rebuilt, validated and rendered.',flush=True)
