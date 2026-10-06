"""Reference sliding-lid box, shown partially open. Print parts separately. mm."""
from build123d import Location
from cadgen.assembly import AssemblyHelper
from sliding_box_common import PARAMETERS as SHARED, settings, ledge_z, build_box, build_lid

PARAMETERS = SHARED | dict(open_distance=30.0)


def build(*,open_distance=30.0,**overrides):
    p = settings(overrides)
    if not 0 <= open_distance <= p['length']-p['wall']-p['end_clearance']-20:
        raise ValueError("Keep at least 20 mm of the lid engaged in this reference assembly.")
    assembly = AssemblyHelper("sliding_box_set:lid_riding_on_two_sloped_side_guides")
    box = assembly.add(build_box(**p),"box")
    lid = assembly.add(build_lid(**p),"sliding_lid")
    x = -(p['wall']+p['end_clearance']+p['pull_extension'])/2-open_distance
    fixed = assembly.rigid_frame(box,"supported_lid_origin",Location((x,0,ledge_z(p,p['height']))))
    moving = assembly.rigid_frame(lid,"lid_print_origin",Location())
    assembly.face_to_face(fixed,moving,label="lid_slides_on_support_ledges")
    return assembly.build()


def gen_step():
    return build(**PARAMETERS)
