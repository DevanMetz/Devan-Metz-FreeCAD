"""Angled holder for card labels. mm; slot open at both ends; flat base Z=0."""
from math import cos, radians, tan
from build123d import Color, Plane, Polygon, Pos, RectangleRounded, extrude

PARAMETERS = dict(length=50.0, width=24.0, height=12.0, slot_gap=.8,
                  slot_depth=8.0, lean_angle=12.0, corner_radius=4.0)


def build(*, length=50.0, width=24.0, height=12.0, slot_gap=.8,
          slot_depth=8.0, lean_angle=12.0, corner_radius=4.0):
    if not (25 <= length <= 120 and 16 <= width <= 50 and 6 <= height <= 25
            and .3 <= slot_gap <= 3 and 0 <= lean_angle <= 30):
        raise ValueError("Stand dimensions, card gap, or lean angle outside supported range.")
    if not (3 <= slot_depth <= height-2.4 and 1 <= corner_radius < min(length, width)/2):
        raise ValueError("Keep a 2.4 mm floor and a valid corner radius.")
    slope = tan(radians(lean_angle))
    gap_y = slot_gap / cos(radians(lean_angle))
    if slot_depth*slope/2 + gap_y/2 >= width/2-corner_radius:
        raise ValueError("Widen the base or reduce the lean/depth so the slot clears the curved ends.")
    body = extrude(RectangleRounded(length, width, corner_radius), amount=height)
    z0, z1 = height-slot_depth, height+1
    y0 = -slot_depth*slope/2
    y1 = y0+(z1-z0)*slope
    profile = Plane.YZ * Polygon((y0-gap_y/2, z0), (y0+gap_y/2, z0),
                                 (y1+gap_y/2, z1), (y1-gap_y/2, z1), align=None)
    cutter = Pos(-length/2-1, 0, 0)*extrude(profile, amount=length+2)
    body = body-cutter
    body.label = "label_stand:angled_card_slot_with_open_ends"
    body.color = Color(.34, .12, .075)
    return body


def gen_step():
    return build(**PARAMETERS)
