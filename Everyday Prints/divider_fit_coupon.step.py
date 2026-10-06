"""Four open-ended clearance slots; top ticks 1–4 identify each left rib. mm."""
from build123d import Align, Box, Color, Pos, RectangleRounded, extrude

PARAMETERS = dict(board_thickness=3.0, clearances=(0.2, 0.4, 0.6, 0.8),
                  wall=2.4, length=20.0, height=8.0, floor=1.6)


def build(*, board_thickness=3.0, clearances=(0.2, 0.4, 0.6, 0.8),
          wall=2.4, length=20.0, height=8.0, floor=1.6):
    if not (1 <= board_thickness <= 10 and 2 <= len(clearances) <= 6
            and all(0.1 <= c <= 1.2 for c in clearances)):
        raise ValueError("Use board 1–10 and 2–6 clearances between 0.1 and 1.2.")
    if not (2 <= wall <= 4 and 16 <= length <= 40 and
            6 <= height <= 15 and 1.2 <= floor <= 3 and height > floor + 2):
        raise ValueError("Coupon dimensions outside supported range.")
    slots = [board_thickness + c for c in clearances]
    width = sum(slots) + wall * (len(slots) + 1)
    body = extrude(RectangleRounded(width, length, 1.5), amount=height)
    cuts = []
    cursor = -width / 2 + wall
    for index, slot in enumerate(slots):
        x = cursor + slot / 2
        cuts.append(Pos(x, 0, floor) * Box(slot, length + 2, height,
                      align=(Align.CENTER, Align.CENTER, Align.MIN)))
        # Marks cut downward into each slot's LEFT rib. Open slot ends let a
        # full-length board pass through, and top marks create no overhangs.
        for tick in range(index + 1):
            y = (tick - index / 2) * 2
            cuts.append(Pos(cursor - wall / 2, y, height - .2) * Box(wall * .5, .7, .8))
        cursor += slot + wall
    body = body - cuts
    body.label = "divider_fit_coupon:open_ended_slots_top_ticks_on_left_ribs"
    body.color = Color(0.5, 0.22, 0.055)
    return body


def gen_step():
    return build(**PARAMETERS)
