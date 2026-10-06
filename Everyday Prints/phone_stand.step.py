"""One-piece phone stand printed on its side. mm; width extrudes along +Z."""
from math import radians, tan
from build123d import Color, Polygon, extrude, offset

PARAMETERS = dict(depth=85.0, height=96.0, width=65.0, angle=68.0,
                  seat_depth=15.0, seat_height=14.0, lip=4.0,
                  lip_height=10.0, base=6.0, frame=6.0)


def build(*, depth=85.0, height=96.0, width=65.0, angle=68.0,
          seat_depth=15.0, seat_height=14.0, lip=4.0,
          lip_height=10.0, base=6.0, frame=6.0):
    if not (60 <= depth <= 130 and 60 <= height <= 140 and 40 <= width <= 100
            and 60 <= angle <= 78):
        raise ValueError("Depth/height/width/angle outside supported range.")
    if not (9 <= seat_depth <= 22 and 10 <= seat_height <= 24 and
            3 <= lip <= 6 and 6 <= lip_height <= 16 and
            4 <= base <= 10 and 4 <= frame <= 10):
        raise ValueError("Seat, lip, base, or frame outside supported range.")
    seat_x = lip + seat_depth
    top_x = seat_x + (height - seat_height) / tan(radians(angle))
    if not (top_x + frame < depth - frame and seat_height > base + 2
            and seat_height + lip_height < height / 2):
        raise ValueError("Increase depth/height or reduce seat and frame sizes.")
    outline = Polygon((0, 0), (depth, 0), (depth, base),
                      (top_x + frame, height), (top_x, height),
                      (seat_x, seat_height), (lip, seat_height),
                      (lip, seat_height + lip_height),
                      (0, seat_height + lip_height), align=None)
    # Inward offset of the triangle creates a robust open frame with a real wall.
    frame_triangle = Polygon((seat_x, base), (depth, base),
                             (top_x + frame / 2, height), align=None)
    opening = offset(frame_triangle, amount=-frame)
    if not opening.faces():
        raise ValueError("Frame is too thick to leave an opening.")
    body = extrude(outline, amount=width) - extrude(opening, amount=width)
    body.label = "phone_stand:side_printed_open_frame"
    body.color = Color(0.12, 0.09, 0.26)
    return body


def gen_step():
    return build(**PARAMETERS)
