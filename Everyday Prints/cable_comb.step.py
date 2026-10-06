"""Desk-edge cable guide; slots are open, not snap-fit. mm; bottom Z=0."""
from build123d import Align, Box, Color, Cylinder, Pos, RectangleRounded, extrude

PARAMETERS = dict(cable_diameters=(3.0, 4.0, 5.0, 6.0, 8.0), clearance=0.6,
                  web=5.0, depth=32.0, thickness=4.0, slot_depth=18.0,
                  mounting_hole=4.5)


def build(*, cable_diameters=(3.0, 4.0, 5.0, 6.0, 8.0), clearance=0.6,
          web=5.0, depth=32.0, thickness=4.0, slot_depth=18.0,
          mounting_hole=4.5):
    if not (2 <= len(cable_diameters) <= 10 and
            all(1.5 <= d <= 14 for d in cable_diameters)):
        raise ValueError("Use 2–10 cable diameters between 1.5 and 14 mm.")
    if not (0.2 <= clearance <= 1.5 and 3 <= web <= 10 and
            2.4 <= thickness <= 8 and 24 <= depth <= 60):
        raise ValueError("Clearance/web/thickness/depth outside supported range.")
    widths = [d + clearance for d in cable_diameters]
    rear_strip = depth - slot_depth
    if not (max(widths) <= slot_depth <= depth - 10 and
            2 <= mounting_hole <= min(web, rear_strip - 6)):
        raise ValueError("Keep 10 mm of rear strip and enough material by holes.")
    length = sum(widths) + web * (len(widths) + 1)
    body = extrude(RectangleRounded(length, depth, 2), amount=thickness)
    cuts = []
    cursor = -length / 2 + web
    for width in widths:
        x = cursor + width / 2
        cy = depth / 2 - slot_depth + width / 2
        round_end = Pos(x, cy, -1) * Cylinder(width / 2, thickness + 2,
                               align=(Align.CENTER, Align.CENTER, Align.MIN))
        mouth_length = depth / 2 - cy + 1
        mouth = Pos(x, cy + mouth_length / 2, thickness / 2) * Box(
            width, mouth_length, thickness + 2)
        cuts.append(round_end + mouth)
        cursor += width + web
    body = body - cuts
    hole_y = -depth / 2 + rear_strip / 2
    holes = [Pos(x, hole_y, -1) * Cylinder(mounting_hole / 2, thickness + 2,
                      align=(Align.CENTER, Align.CENTER, Align.MIN))
             for x in (-length / 2 + web, length / 2 - web)]
    body = body - holes
    body.label = f"cable_comb:{len(widths)}_open_slots_rear_mounting_strip"
    body.color = Color(0.04, 0.19, 0.39)
    return body


def gen_step():
    return build(**PARAMETERS)
