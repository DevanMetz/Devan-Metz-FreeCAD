"""Build STEP-first delivery, harness checks, meshes, and snapshot jobs.

Usage: python build_delivery.py
The generated 3MFs contain geometry only, not printer settings or G-code.
"""
import sys
import json
import subprocess
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import trimesh

ROOT=Path(__file__).resolve().parent
CAD=Path(r'C:\Users\metzd\.codex\skills\cad\scripts')
PRINTS=['lower_frame','upper_hood','provisional_dock','axis_sizing_coupon']+[f'gripper_axis_{s}' for s in (600,500,400,340,300,260,200)]
ASSEMBLIES=['LiftX_LH_Assembly','LiftX_LH_Loaded_Clearance_Reference']


def cli(tool,*args):
    proc=subprocess.run([sys.executable,str(CAD/tool),*map(str,args)],cwd=ROOT,capture_output=True,text=True)
    if proc.returncode:
        raise RuntimeError(f'{tool} {args}: {proc.stdout}\n{proc.stderr}')
    return proc.stdout


def main():
    for d in ('STL','3MF','Review'):
        (ROOT/d).mkdir(exist_ok=True)
    print('Generating canonical STEP sources...',flush=True)
    gen=cli('gen',*[n+'.step.py' for n in PRINTS+ASSEMBLIES],'--write','--json')
    (ROOT/'Review'/'generation.jsonl').write_text(gen,encoding='utf-8')
    print('Exporting print-oriented meshes...',flush=True)
    def export(name):
        out=cli('export',name+'.step.py','--stl',ROOT/'STL'/f'{name}.stl','--3mf',ROOT/'3MF'/f'{name}.3mf','--json')
        print('Exported',name,flush=True)
        return json.loads(out)
    with ThreadPoolExecutor(max_workers=2) as pool:
        exports=list(pool.map(export,PRINTS))
    (ROOT/'Review'/'exports.json').write_text(json.dumps(exports,indent=2),encoding='utf-8')
    print('Harness soundness and topology checks...',flush=True)
    def validate(name):
        out=cli('inspect','validate',name+'.step.py')
        print('Validated',name,flush=True)
        return {'name':name,'result':json.loads(out)}
    with ThreadPoolExecutor(max_workers=2) as pool:
        validations=list(pool.map(validate,PRINTS+ASSEMBLIES))
    (ROOT/'Review'/'harness_validation.json').write_text(json.dumps(validations,indent=2),encoding='utf-8')
    facts=cli('inspect','refs','LiftX_LH_Assembly.step.py','--facts','--planes','--positioning')
    (ROOT/'Review'/'assembly_facts.json').write_text(facts,encoding='utf-8')
    meshes={}
    for name in PRINTS:
        path=ROOT/'STL'/f'{name}.stl'
        m=trimesh.load_mesh(path)
        down=(m.face_normals[:,2]<-0.707107) & (m.triangles_center[:,2]>.25)
        mesh3=trimesh.load(ROOT/'3MF'/f'{name}.3mf',force='mesh')
        meshes[name]={'watertight':bool(m.is_watertight),'winding_consistent':bool(m.is_winding_consistent),
                      'bodies':int(m.body_count),'volume_mm3':float(m.volume),'bounds_mm':m.extents.tolist(),
                      'fits_256_with_3mm_margin':bool((m.extents<=250).all()),
                      'downward_area_steeper_than_45deg_excluding_bed_mm2':float(m.area_faces[down].sum()),
                      '3mf_watertight':bool(mesh3.is_watertight),'3mf_bounds_mm':mesh3.extents.tolist(),
                      'stl_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                      'step_sha256':hashlib.sha256((ROOT/f'{name}.step').read_bytes()).hexdigest()}
        if not m.is_watertight or m.volume<=0 or m.body_count!=1 or not mesh3.is_watertight or not (m.extents<=250).all():
            raise ValueError(f'Mesh checks failed: {name}')
    (ROOT/'Review'/'mesh_validation.json').write_text(json.dumps(meshes,indent=2),encoding='utf-8')
    # One concise inspection view of each size variant, plus opposed views for the
    # complex frame, and the loaded clearance reference (NOT real broadhead CAD).
    jobs=[]
    for name in PRINTS+ASSEMBLIES[1:]:
        cameras=['iso']
        if name in ('upper_hood','lower_frame','provisional_dock','LiftX_LH_Loaded_Clearance_Reference'):
            cameras.append({'direction':[-1,1,-.8]})
        jobs.append({'input':str(ROOT/f'{name}.step.py'),'mode':'view',
                     'theme':str(ROOT/'Review'/'review_theme.json'),
                     'outputs':[{'path':str(ROOT/'Review'/f'{name}_{i}.png'),'camera':c} for i,c in enumerate(cameras)],
                     'render':{'sizeProfile':'diagnostic','viewLabels':True,'padding':.12}})
    (ROOT/'Review'/'parts_snapshot_jobs.json').write_text(json.dumps(jobs,indent=2),encoding='utf-8')
    shots=cli('snapshot','--job','Review/parts_snapshot_jobs.json','--json')
    (ROOT/'Review'/'parts_snapshot_results.json').write_text(shots,encoding='utf-8')
    shots=cli('snapshot','--job','Review/assembly_snapshot.json','--json')
    (ROOT/'Review'/'assembly_snapshot_results.json').write_text(shots,encoding='utf-8')
    for job,out in (('detail_snapshot_jobs.json','detail_snapshot_results.json'),):
        shots=cli('snapshot','--job',ROOT/'Review'/job,'--json')
        (ROOT/'Review'/out).write_text(shots,encoding='utf-8')
    print('STEP, STL, 3MF, checks and screenshots built.',flush=True)


if __name__=='__main__':
    main()
