"""Fit sample for the hex-bit rack; top marks 1–3 identify clearances. mm."""
from math import sqrt
from build123d import Box, Color, Pos, RectangleRounded, RegularPolygon, extrude, loft

PARAMETERS = dict(shank_af=6.35, clearances=(.15, .35, .55), pitch=12.0,
                  margin=8.0, depth=20.0, height=14.0, floor=2.4, lead_in=.6)


def build(*, shank_af=6.35, clearances=(.15, .35, .55), pitch=12.0,
          margin=8.0, depth=20.0, height=14.0, floor=2.4, lead_in=.6):
    if not (3 <= shank_af <= 12 and 2 <= len(clearances) <= 5
            and all(.1 <= c <= 1 for c in clearances) and
            8 <= pitch <= 25 and 6 <= margin <= 20 and 16 <= depth <= 40 and
            8 <= height <= 30 and 1.6 <= floor <= 5 and .3 <= lead_in <= 1):
        raise ValueError("Coupon, shank, or clearance values outside supported ranges.")
    max_af = shank_af+max(clearances)+2*lead_in
    radius = max_af/sqrt(3)
    if (pitch < 2*radius+2 or margin < radius+3 or
            depth/2-2.7 < max_af/2+.8 or height-floor <= 2*lead_in+2):
        raise ValueError("Leave adequate socket webs, end margins, label space, and depth.")
    length = (len(clearances)-1)*pitch+2*margin
    body = extrude(RectangleRounded(length, depth, 3), amount=height)
    holes, leads, marks = [], [], []
    for index, clearance in enumerate(clearances):
        x = (index-(len(clearances)-1)/2)*pitch
        af = shank_af+clearance
        socket = RegularPolygon(af/sqrt(3), 6)
        holes.append(Pos(x,0,floor)*extrude(socket, amount=height-floor+1))
        wide = RegularPolygon((af+2*(lead_in+.1))/sqrt(3), 6)
        leads.append(Pos(x,0,0)*loft([Pos(0,0,height-lead_in)*socket,
                                      Pos(0,0,height+.1)*wide]))
        for tick in range(index+1):
            marks.append(Pos(x+(tick-index/2)*1.8, depth/2-2, height-.2)*Box(.7, 1.4, .8))
    body = body-holes
    body = body-leads
    body = body-marks
    body.label = "hex_bit_fit_coupon:increasing_across_flat_clearance_top_tick_labels"
    body.color = Color(.13, .35, .17)
    return body


def gen_step():
    return build(**PARAMETERS)
