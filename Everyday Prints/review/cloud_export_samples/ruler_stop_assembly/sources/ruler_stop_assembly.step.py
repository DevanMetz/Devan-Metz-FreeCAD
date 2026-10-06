"""Reference ruler stop. Gray ruler is illustrative hardware, not a print. mm."""
from build123d import Align, Box, Color, Location, Rot
from cadgen.assembly import AssemblyHelper
from ruler_stop_common import PARAMETERS as SHARED, settings, engagement, build_body, build_wedge

PARAMETERS = SHARED | dict(reference_length=180.0)


def build(*,reference_length=180.0,**overrides):
    p = settings(overrides)
    if not max(90,p['body_length']+60) <= reference_length <= 400:
        raise ValueError("Use a reference ruler long enough to extend past both ends of the stop.")
    assembly = AssemblyHelper("ruler_stop_set:body_wedge_and_nonprintable_ruler_reference")
    # Map the printed profile (width, height, length) to in-use (length, width, height).
    body = assembly.add(Rot(0,0,90)*Rot(90,0,0)*build_body(**p),"stop_body")
    ruler = assembly.add(Box(reference_length,p['ruler_width'],p['ruler_thickness'],
                             align=(Align.MIN,Align.CENTER,Align.MIN)),
                         "REFERENCE_ruler_not_for_printing",color=Color(.6,.62,.66))
    fixed = assembly.rigid_frame(body,"ruler_on_floor",Location((-reference_length/4,0,p['floor'])))
    moving = assembly.rigid_frame(ruler,"ruler_lower_end",Location())
    assembly.face_to_face(fixed,moving,label="ruler_resting_on_stop_floor")
    wedge = assembly.add(build_wedge(**p),"ruler_wedge")
    fixed = assembly.rigid_frame(body,"engaged_tip",Location((engagement(p),0,p['floor']+p['ruler_thickness']),
                                                            (0,0,180)))
    moving = assembly.rigid_frame(wedge,"wedge_tip_lower_edge",Location())
    assembly.face_to_face(fixed,moving,label="wedge_contact_at_passage_mouth")
    return assembly.build()


def gen_step():
    return build(**PARAMETERS)
