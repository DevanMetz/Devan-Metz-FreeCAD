"""Edge-referenced knob/pull marking template, not a drill bushing. mm."""
from build123d import Align, Box, Color, Cylinder, Polygon, Pos, extrude

PARAMETERS = dict(hole_pitch=128.0, setback=25.0, end_margin=16.0,
                  front_margin=12.0, plate=4.0, fence=3.0,
                  fence_height=18.0, marking_hole=3.2)


def build(*, hole_pitch=128.0, setback=25.0, end_margin=16.0,
          front_margin=12.0, plate=4.0, fence=3.0,
          fence_height=18.0, marking_hole=3.2):
    if not (16 <= hole_pitch <= 192 and 10 <= setback <= 70 and
            8 <= end_margin <= 24 and 8 <= front_margin <= 20):
        raise ValueError("Pitch, setback, or margins outside supported range.")
    if not (2.4 <= plate <= 8 and 2.4 <= fence <= 6 and
            10 <= fence_height <= 35 and fence_height > plate + 4 and
            2 <= marking_hole <= 5):
        raise ValueError("Plate, fence, height, or marking diameter outside range.")
    length = hole_pitch + 2 * end_margin
    depth = fence + setback + front_margin
    body = Pos(0, depth / 2, plate / 2) * Box(length, depth, plate)
    fence_body = Pos(0, fence / 2, fence_height / 2) * Box(length, fence, fence_height)
    body = body + fence_body
    holes = [Pos(x, fence + setback, -1) * Cylinder(marking_hole / 2, plate + 2,
                      align=(Align.CENTER, Align.CENTER, Align.MIN))
             for x in (-hole_pitch / 2, 0, hole_pitch / 2)]
    body = body - holes
    # Front V notch marks the template centerline without interrupting the fence.
    notch = Polygon((-2, depth + 1), (0, depth - 2), (2, depth + 1), align=None)
    body = body - extrude(notch, amount=plate + 1)
    body.label = "handle_marking_jig:edge_fence_center_and_two_pull_holes"
    body.color = Color(0.03, 0.27, 0.14)
    return body


def gen_step():
    return build(**PARAMETERS)
