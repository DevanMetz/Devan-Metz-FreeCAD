"""Freestanding foot for a thin drawer divider. mm; flat base at Z=0."""
from build123d import Color, Plane, Polygon, Pos, RectangleRounded, extrude

PARAMETERS = dict(board_thickness=3.0, clearance=0.4, base_width=34.0,
                  length=24.0, height=20.0, floor=2.4, jaw=3.0, lead_in=1.0)


def build(*, board_thickness=3.0, clearance=0.4, base_width=34.0,
          length=24.0, height=20.0, floor=2.4, jaw=3.0, lead_in=1.0):
    slot = board_thickness + clearance
    if not (1 <= board_thickness <= 10 and 0.1 <= clearance <= 1.2):
        raise ValueError("Use board thickness 1–10 and total clearance 0.1–1.2.")
    if not (20 <= base_width <= 70 and 15 <= length <= 60 and
            10 <= height <= 45 and 1.6 <= floor <= 5 and 2 <= jaw <= 6):
        raise ValueError("Base, length, height, floor, or jaw outside supported range.")
    if not (0.4 <= lead_in <= jaw / 2 and slot + 2 * jaw <= base_width - 6
            and height > floor + 2 * lead_in):
        raise ValueError("Leave 3 mm base shoulders and enough jaw for the lead-in.")
    base = extrude(RectangleRounded(base_width, length, 3), amount=floor)
    # XZ profiles are extruded along -Y from the back edge. All polygons are CCW.
    right = [(slot / 2, floor - 0.2), (slot / 2 + jaw, floor - 0.2),
             (slot / 2 + jaw, height), (slot / 2 + lead_in, height),
             (slot / 2, height - lead_in)]
    left = [(-x, z) for x, z in reversed(right)]
    ribs = [Pos(0, length / 2, 0) * extrude(
        Plane.XZ * Polygon(*pts, align=None), amount=length) for pts in (left, right)]
    body = base + ribs
    body.label = "divider_foot:parallel_jaws_with_tapered_entry"
    body.color = Color(0.38, 0.18, 0.035)
    return body


def gen_step():
    return build(**PARAMETERS)
