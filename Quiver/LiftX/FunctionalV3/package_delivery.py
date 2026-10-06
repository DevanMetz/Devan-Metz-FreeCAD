"""Package only V3 sources, checked outputs and current review screenshots."""
import json
import hashlib
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root=Path(__file__).resolve().parent
files=set(root.glob('*.py'))|set(root.glob('*.step'))|set(root.glob('*.md'))
for folder in ('STL','3MF'):
    files.update((root/folder).iterdir())
files.update((root/'Review').glob('*.json'))
files.update((root/'Review').glob('*.jsonl'))
files.update((root/'Review').glob('*.md'))
for name in ('assembly_snapshot_results.json','parts_snapshot_results.json','detail_snapshot_results.json','section_snapshot_results.json'):
    result=json.loads((root/'Review'/name).read_text(encoding='utf-8'))
    for job in result.get('jobs',[result]):
        for out in job.get('outputs',[]):
            files.add(Path(out['path']))
validation=json.loads((root/'Review'/'functional_validation.json').read_text(encoding='utf-8'))
assert validation['pass']
mesh=json.loads((root/'Review'/'mesh_validation.json').read_text(encoding='utf-8'))
for name,check in mesh.items():
    assert check['watertight'] and check['3mf_watertight']
    assert hashlib.sha256((root/f'{name}.step').read_bytes()).hexdigest()==check['step_sha256']
    assert hashlib.sha256((root/'STL'/f'{name}.stl').read_bytes()).hexdigest()==check['stl_sha256']
out=root/'LiftX_LH_AXIS_V3_Fit_Test_Pack.zip'
with ZipFile(out,'w',ZIP_DEFLATED) as pack:
    for file in sorted(files):
        if file.is_file():
            pack.write(file,file.relative_to(root).as_posix())
with ZipFile(out,'r') as pack:
    assert pack.testzip() is None
print(f'{out}: {len(files)} files, {out.stat().st_size:,} bytes; validated hashes and ZIP integrity.')
