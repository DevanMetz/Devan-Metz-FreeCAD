"""Reference fit at the clamp mouths; flexible sandpaper is omitted. mm."""
from build123d import Location
from cadgen.assembly import AssemblyHelper
from sanding_common import PARAMETERS, settings, engagement, slot_centers, build_block, build_wedge


def build(**overrides):
    p = settings(overrides)
    assembly = AssemblyHelper("sanding_set:block_and_two_paper_wedges")
    block = assembly.add(build_block(**p), "sanding_block")
    for index, x in enumerate(slot_centers(p)):
        sign = -1 if x < 0 else 1
        # One paper layer lies between the wedge and the outside slot wall.
        # Shifting inward by half its thickness places the other face at the
        # inside mouth edge. The taper stays clear below that edge.
        origin = (x-sign*p['paper_thickness']/2, 0, p['height'])
        fixed = assembly.rigid_frame(block, f"clamp_mouth_{index}", Location(origin))
        wedge = assembly.add(build_wedge(**p), f"paper_wedge_{index}")
        moving = assembly.rigid_frame(wedge, "engaged_section", Location((0,0,engagement(p))))
        assembly.face_to_face(fixed, moving, label=f"paper_clamp_{index}")
    return assembly.build()


def gen_step():
    return build(**PARAMETERS)
