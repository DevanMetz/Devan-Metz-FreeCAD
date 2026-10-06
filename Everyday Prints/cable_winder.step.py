"""Flat cable bobbin with open parking notches and an optional tie slot. mm."""
from build123d import Align, Box, Color, Cylinder, Pos, RectangleRounded, SlotOverall, extrude

PARAMETERS = dict(length=95.0, width=44.0, neck_width=22.0, end_width=14.0,
                  thickness=4.0, notch_gap=3.6, notch_depth=7.0)


def build(*, length=95.0, width=44.0, neck_width=22.0, end_width=14.0,
          thickness=4.0, notch_gap=3.6, notch_depth=7.0):
    if not (55 <= length <= 160 and 28 <= width <= 70 and
            12 <= neck_width <= width-12 and 10 <= end_width <= 24 and
            2.4 <= thickness <= 8 and 2 <= notch_gap <= end_width-6):
        raise ValueError("Body, waist, end caps, thickness, or notch outside supported ranges.")
    if end_width >= length/3 or not (notch_gap <= notch_depth <= (width-neck_width)/2-1):
        raise ValueError("Keep a useful winding waist and material below each notch.")
    body = extrude(RectangleRounded(length-2*end_width+4, neck_width, 3), amount=thickness)
    cap = extrude(RectangleRounded(end_width, width, 3), amount=thickness)
    center_x = (length-end_width)/2
    body = body + [Pos(-center_x, 0, 0)*cap, Pos(center_x, 0, 0)*cap]
    cuts = []
    for sign in (-1, 1):
        x = sign*center_x
        cy = sign*(width/2-notch_depth+notch_gap/2)
        round_end = Pos(x, cy, -1)*Cylinder(notch_gap/2, thickness+2,
                             align=(Align.CENTER, Align.CENTER, Align.MIN))
        mouth_length = notch_depth-notch_gap/2+1
        mouth = Pos(x, cy+sign*mouth_length/2, thickness/2)*Box(notch_gap, mouth_length, thickness+2)
        cuts.append(round_end+mouth)
    body = body-cuts
    body = body-Pos(0, 0, -1)*extrude(SlotOverall(12, 3), amount=thickness+2)
    body.label = "cable_winder:wide_ends_open_cord_parking_notches_center_tie_slot"
    body.color = Color(.035, .27, .45)
    return body


def gen_step():
    return build(**PARAMETERS)
