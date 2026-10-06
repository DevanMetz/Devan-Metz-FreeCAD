"""Small 90-degree glue-up / marking reference; not a calibrated instrument."""
from build123d import Align, Color, Cylinder, Polygon, Pos, extrude

PARAMETERS = dict(leg=80.0, leg_width=18.0, thickness=8.0,
                  corner_relief=3.0, hanging_hole=5.0, tip_chamfer=2.0)


def build(*, leg=80.0, leg_width=18.0, thickness=8.0,
          corner_relief=3.0, hanging_hole=5.0, tip_chamfer=2.0):
    if not (40 <= leg <= 160 and 12 <= leg_width <= 30 and
            4 <= thickness <= 15 and 0.5 <= tip_chamfer <= 4):
        raise ValueError("Leg, width, thickness, or tip chamfer outside range.")
    if not (leg >= 2.5 * leg_width and 1 <= corner_relief <= leg_width / 3
            and 3 <= hanging_hole <= leg_width - 6):
        raise ValueError("Keep sufficient straight datum length and hole margins.")
    c, w = tip_chamfer, leg_width
    outline = Polygon((0, 0), (leg-c, 0), (leg, c), (leg, w-c),
                      (leg-c, w), (w, w), (w, leg-c), (w-c, leg),
                      (c, leg), (0, leg-c), align=None)
    body = extrude(outline, amount=thickness)
    cut = lambda x, y, r: Pos(x, y, -1) * Cylinder(r, thickness + 2,
                              align=(Align.CENTER, Align.CENTER, Align.MIN))
    body = body - [cut(w, w, corner_relief), cut(w / 2, leg - w / 2, hanging_hole / 2)]
    body.label = "corner_square:perpendicular_inside_datums_with_glue_relief"
    body.color = Color(0.47, 0.085, 0.035)
    return body


def gen_step():
    return build(**PARAMETERS)
