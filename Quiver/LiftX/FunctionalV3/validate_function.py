"""Repeatable sampled rigid-envelope checks; NOT strength or retention certification."""
import json
import math
from pathlib import Path
from build123d import Axis, Location
import quiver_common as q


def overlap_volume(a,b):
    if not hasattr(a,'bounding_box'):
        return sum(overlap_volume(s,b) for s in a)
    if not hasattr(b,'bounding_box'):
        return sum(overlap_volume(a,s) for s in b)
    aa,bb=a.bounding_box(),b.bounding_box()
    if any(getattr(aa.max,c) < getattr(bb.min,c)-1e-7 or
           getattr(bb.max,c) < getattr(aa.min,c)-1e-7 for c in ('X','Y','Z')):
        return 0.0
    s=a.intersect(b)
    if not s:
        return 0.0
    return abs(s.volume) if hasattr(s,'volume') else sum(abs(item.volume) for item in s)


def run():
    report={'scope':'Sampled rigid geometry only. TPU and foam deform intentionally; no structural or bow-fit certification.',
            'selected_axis_spine':q.SELECTED_SPINE, 'selected_shaft_od_mm':q.AXIS_OD[q.SELECTED_SPINE],
            'shaft_od_mm':max(q.AXIS_OD.values()), 'broadhead_envelope_mm':[q.HEAD_D,q.HEAD_L],
            'parts':{}, 'spine_joint':{}, 'removal':[], 'dock':{}}
    rigid={'upper':q.upper_frame(),'lower':q.lower_frame(),'dock':q.dock()}
    for name in ('upper','lower','dock','gripper','coupon'):
        s=q.print_part(name)
        size=list(s.bounding_box().size)
        report['parts'][name]={'valid':s.is_valid,'solids':len(s.solids()),'volume_mm3':s.volume,
                               'print_bbox_mm':size,'fits_256_with_3mm_margin_each_side':all(d<=250 for d in size)}
    report['spine_joint']['rigid_overlap_mm3']=overlap_volume(rigid['upper'],rigid['lower'])
    report['spine_joint']['nominal_socket_side_clearance_mm']=.3
    report['spine_joint']['bolt_axes_mm']=[[0,-29,205],[0,-29,220]]
    report['spine_joint']['hood_neck_one_solid']=len(rigid['upper'].solids())==1
    report['gripper_rigid_overlap_mm3']=overlap_volume(q.gripper(),rigid['lower'])
    jaw_zones=[q.cyl(9.3,9.5,x,y,3.1).intersect(q.box(x-10,y,3.1,20,10,9.5)) for x,y in q.AXES]
    report['tpu_jaw_expansion_zone_hard_overlap_mm3']=[overlap_volume(s,rigid['lower']) for s in jaw_zones]
    arrows=[q.reference_arrow(x,y) for x,y in q.AXES]
    report['parked_hard_interference_mm3']=[sum(overlap_volume(a,s) for s in rigid.values()) for a in arrows]
    report['parked_arrow_pair_overlap_mm3']=[overlap_volume(arrows[i],arrows[j]) for i in range(5) for j in range(i)]
    theta=math.degrees(math.asin(14/(q.TIP_Z-8)))
    for i,(x,y) in enumerate(q.AXES):
        samples=[]
        pivot=Axis((x,y,q.TIP_Z),(1,0,0))
        for k in range(13):
            samples.append(('tip_pivot',k/12,arrows[i].rotate(pivot,theta*k/12)))
        tilted=arrows[i].rotate(pivot,theta)
        for k in range(1,33):
            d=95*k/32
            samples.append(('withdraw_head',d,tilted.moved(Location((0,math.sin(math.radians(theta))*d,-math.cos(math.radians(theta))*d)))))
        clear=tilted.moved(Location((0,math.sin(math.radians(theta))*95,-math.cos(math.radians(theta))*95)))
        for k in range(1,41):
            samples.append(('outboard_exit',k*2.5,clear.moved(Location((0,k*2.5,0)))))
        max_hard=max_neighbor=0.
        failures=[]
        for stage,t,arrow in samples:
            hard={n:overlap_volume(arrow,s) for n,s in rigid.items()}
            neighbors={str(j+1):overlap_volume(arrow,a) for j,a in enumerate(arrows) if j!=i}
            max_hard=max(max_hard,*hard.values())
            max_neighbor=max(max_neighbor,*neighbors.values())
            if max(*hard.values(),*neighbors.values())>1e-5:
                failures.append({'stage':stage,'parameter':t,'hard_mm3':hard,'neighbor_mm3':neighbors})
        item={'arrow':i+1,'axis_mm':[x,y],'samples':len(samples),'pivot_deg':theta,
              'withdrawal_mm':95,'max_hard_overlap_mm3':max_hard,'max_neighbor_overlap_mm3':max_neighbor,
              'pass':not failures,'first_failures':failures[:8]}
        report['removal'].append(item)
        print('Arrow',i+1,'PASS' if not failures else 'FAIL',max_hard,max_neighbor,flush=True)
    # The latch is compliant. Remove exactly its flexing envelope, never the rails/stops.
    flex=q.box(-8.2,-16+q.DY,q.MOUNT_Z+.001,16.4,12,77.999)
    rigid_dock=q.dock().cut(flex)
    slides=[]
    for d in range(0,85,2):
        vol=overlap_volume(q.lower_frame().moved(Location((0,0,d))),rigid_dock)
        if vol>1e-5:
            slides.append({'lift_mm':d,'overlap_mm3':vol})
    report['dock']={'rigid_slide_samples':43,'stroke_mm':84,'excludes_flexible_latch':True,
                    'pass':not slides,'failures':slides,'bow_fit':'UNVERIFIED; generic mounting template only'}
    report['pass']=all(p['valid'] and p['solids']==1 and p['fits_256_with_3mm_margin_each_side'] for p in report['parts'].values()) and all(r['pass'] for r in report['removal']) and not slides and report['spine_joint']['rigid_overlap_mm3']<1e-5 and report['gripper_rigid_overlap_mm3']<1e-5 and max(report['tpu_jaw_expansion_zone_hard_overlap_mm3'])<1e-5
    output=Path(__file__).parent/'Review'/'functional_validation.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('parts','removal')},indent=2),flush=True)
    return report


if __name__=='__main__':
    raise SystemExit(0 if run()['pass'] else 1)
