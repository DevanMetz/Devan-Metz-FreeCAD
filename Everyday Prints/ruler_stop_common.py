"""Shared geometry for a wedge-clamped ruler stop. All dimensions are mm."""
from build123d import Align, Box, Color, Plane, Polygon, Pos, Rectangle, RectangleRounded, extrude

PARAMETERS = dict(ruler_width=26.0,ruler_thickness=1.0,side_clearance=.4,body_length=24.0,
                  floor=3.0,roof=4.0,side_wall=4.0,clamp_gap=2.2,wedge_length=35.0,
                  wedge_tip=.8,wedge_back=3.0,wedge_side_clearance=1.2,grip_length=3.0,grip_height=4.0)


def engagement(p):
    return p['wedge_length']*(p['clamp_gap']-p['wedge_tip'])/(p['wedge_back']-p['wedge_tip'])


def settings(overrides):
    if set(overrides)-set(PARAMETERS):
        raise ValueError(f"Unknown ruler-stop parameters: {sorted(set(overrides)-set(PARAMETERS))}")
    p = PARAMETERS | overrides
    if not (10 <= p['ruler_width'] <= 45 and .5 <= p['ruler_thickness'] <= 2.5
            and .2 <= p['side_clearance'] <= .8 and 18 <= p['body_length'] <= 36
            and 2.4 <= p['floor'] <= 5 and 3 <= p['roof'] <= 6 and 3 <= p['side_wall'] <= 6
            and 1.5 <= p['clamp_gap'] <= 4 and 28 <= p['wedge_length'] <= 50
            and .6 <= p['wedge_tip'] <= 1.4 and 2.6 <= p['wedge_back'] <= 5
            and .6 <= p['wedge_side_clearance'] <= 1.6
            and 3 <= p['grip_length'] <= 7 and 3 <= p['grip_height'] <= 6):
        raise ValueError("Ruler-stop dimensions outside supported ranges.")
    if not p['wedge_tip']+.6 <= p['clamp_gap'] <= p['wedge_back']-.4:
        raise ValueError("The wedge must enter freely and grow beyond the clamping gap.")
    depth = engagement(p)
    if (not p['body_length']-5 <= depth <= p['body_length']-1
            or p['wedge_length']-depth < p['grip_length']+4
            or p['ruler_width']+p['side_clearance']-2*p['wedge_side_clearance'] < 8):
        raise ValueError("Keep the wedge tip behind the reference face, its grip exposed, and a useful clamping span.")
    return p


def build_body(**overrides):
    p = settings(overrides)
    slot_width = p['ruler_width']+p['side_clearance']
    slot_height = p['ruler_thickness']+p['clamp_gap']
    height = p['floor']+slot_height+p['roof']
    outer = Pos(0,height/2)*RectangleRounded(slot_width+2*p['side_wall'],height,1.5)
    slot = Pos(0,p['floor']+slot_height/2)*Rectangle(slot_width,slot_height)
    body = extrude(outer-slot,amount=p['body_length'])
    body.label = "ruler_stop:through_passage_end_profile_on_bed_flat_reference_face"
    body.color = Color(.12,.25,.4)
    return body


def build_wedge(**overrides):
    p = settings(overrides)
    span = p['ruler_width']+p['side_clearance']-2*p['wedge_side_clearance']
    length = p['wedge_length']
    profile = Plane.XZ*Polygon((0,0),(length,0),(length,p['wedge_back']),(0,p['wedge_tip']),align=None)
    wedge = Pos(0,-span/2,0)*extrude(profile,amount=span,dir=(0,1,0))
    grip_start = length-p['grip_length']
    grip_bottom = p['wedge_tip']+(p['wedge_back']-p['wedge_tip'])*grip_start/length
    wedge += Pos(grip_start,0,grip_bottom)*Box(p['grip_length'],span,
                 p['wedge_back']+p['grip_height']-grip_bottom,align=(Align.MIN,Align.CENTER,Align.MIN))
    wedge.label = "ruler_wedge:flat_bottom_shallow_taper_exposed_pull_grip"
    wedge.color = Color(.64,.28,.06)
    return wedge
