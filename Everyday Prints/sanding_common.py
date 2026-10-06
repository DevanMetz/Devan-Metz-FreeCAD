"""Shared parameters for a hand sanding block and its two paper wedges. mm."""
from build123d import Color, Plane, Polygon, Pos, RectangleRounded, extrude

PARAMETERS = dict(length=100.0, width=50.0, height=25.0, end_margin=7.0,
                  slot_width=6.0, slot_span=40.0, slot_depth=14.0,
                  paper_thickness=.3, wedge_tip=3.2, wedge_top=8.0,
                  wedge_height=20.0, wedge_end_clearance=2.0)


def settings(overrides):
    if set(overrides)-set(PARAMETERS):
        raise ValueError(f"Unknown sanding parameters: {sorted(set(overrides)-set(PARAMETERS))}")
    p = PARAMETERS | overrides
    if not (70 <= p['length'] <= 180 and 35 <= p['width'] <= 90 and
            20 <= p['height'] <= 40 and 6 <= p['end_margin'] <= 15 and
            4 <= p['slot_width'] <= 10 and 25 <= p['slot_span'] <= 80 and
            10 <= p['slot_depth'] <= 25 and .15 <= p['paper_thickness'] <= .8 and
            2 <= p['wedge_tip'] <= 5 and 6 <= p['wedge_top'] <= 14 and
            16 <= p['wedge_height'] <= 30 and 1.6 <= p['wedge_end_clearance'] <= 4):
        raise ValueError("Sanding dimensions outside supported ranges.")
    if (p['slot_span'] > p['width']-8 or p['slot_span']-2*p['wedge_end_clearance'] < 20
            or p['slot_depth'] > p['height']-5
            or p['length']-2*(p['end_margin']+p['slot_width']+5) < 25):
        raise ValueError("Preserve the slot floor, side walls, wedge span, and grip recess.")
    if not (p['wedge_tip']+1 < p['slot_width']-p['paper_thickness'] < p['wedge_top']-1):
        raise ValueError("The wedge must enter freely and become wide enough to clamp the paper.")
    depth = engagement(p)
    if not (6 <= depth <= p['slot_depth']-2 and p['wedge_height']-depth >= 5):
        raise ValueError("Leave 2 mm below the engaged wedge and 5 mm above the clamp mouth.")
    return p


def engagement(p):
    return ((p['slot_width']-p['paper_thickness']-p['wedge_tip']) *
            p['wedge_height']/(p['wedge_top']-p['wedge_tip']))


def slot_centers(p):
    x = p['length']/2-p['end_margin']-p['slot_width']/2
    return (-x, x)


def build_block(**overrides):
    p = settings(overrides)
    l, w, h = p['length'], p['width'], p['height']
    # The XZ profile provides 1 mm bottom and 4 mm top wrap-edge chamfers.
    profile = Plane.XZ * Polygon((-l/2,1), (-l/2+1,0), (l/2-1,0), (l/2,1),
                                 (l/2,h-4), (l/2-4,h), (-l/2+4,h), (-l/2,h-4), align=None)
    body = Pos(0,w/2,0)*extrude(profile, amount=w)
    slot = extrude(RectangleRounded(p['slot_width'], p['slot_span'], 1.5),
                   amount=p['slot_depth']+1)
    body = body-[Pos(x,0,h-p['slot_depth'])*slot for x in slot_centers(p)]
    grip_length = l-2*(p['end_margin']+p['slot_width']+5)
    grip = extrude(RectangleRounded(grip_length,w-16,4), amount=h)
    body = body-Pos(0,0,h-8)*grip
    body.label = "sanding_block:flat_sole_two_blind_paper_slots_recessed_grip"
    body.color = Color(.19,.23,.3)
    return body


def build_wedge(**overrides):
    p = settings(overrides)
    width = p['slot_span']-2*p['wedge_end_clearance']
    profile = Plane.XZ * Polygon((-p['wedge_tip']/2,0), (p['wedge_tip']/2,0),
                                 (p['wedge_top']/2,p['wedge_height']),
                                 (-p['wedge_top']/2,p['wedge_height']), align=None)
    body = Pos(0,width/2,0)*extrude(profile,amount=width)
    body.label = "sanding_wedge:print_two_tip_down_tapered_paper_clamp"
    body.color = Color(.65,.26,.04)
    return body
