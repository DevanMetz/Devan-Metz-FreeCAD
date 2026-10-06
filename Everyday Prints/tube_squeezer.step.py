"""Flat squeeze-through aid for soft tubes; rounded, beveled slot. Units mm."""
from build123d import Color, Pos, RectangleRounded, SlotOverall, extrude, loft

PARAMETERS = dict(length=90.0, width=26.0, thickness=6.0, slot_length=64.0,
                  slot_gap=2.0, lead_in=0.6, corner_radius=8.0)


def build(*, length=90.0, width=26.0, thickness=6.0, slot_length=64.0,
          slot_gap=2.0, lead_in=0.6, corner_radius=8.0):
    if not (45 <= length <= 140 and 18 <= width <= 40 and 4 <= thickness <= 10
            and 25 <= slot_length <= 115 and 0.8 <= slot_gap <= 4):
        raise ValueError("Body or slot dimensions outside supported ranges.")
    if not (2 <= corner_radius < width / 2 and
            .2 <= lead_in <= min(1.2, thickness / 3) and
            slot_length + 2*lead_in <= length - 12 and
            slot_gap + 2*lead_in <= width - 10):
        raise ValueError("Keep 6 mm end webs, 5 mm side webs, and valid lead-ins.")
    body = extrude(RectangleRounded(length, width, corner_radius), amount=thickness)
    slot = SlotOverall(slot_length, slot_gap)
    body = body - Pos(0, 0, -1) * extrude(slot, amount=thickness + 2)
    # 0.8 horizontal / vertical is about 38.7 degrees from vertical, leaving
    # tessellation margin below a 45-degree underside overhang.
    entry_slope = .8
    lead_height = lead_in / entry_slope
    mouth = SlotOverall(slot_length + 2*(lead_in+.1*entry_slope),
                        slot_gap + 2*(lead_in+.1*entry_slope))
    lower = loft([Pos(0, 0, -.1)*mouth, Pos(0, 0, lead_height)*slot])
    upper = loft([Pos(0, 0, thickness-lead_height)*slot, Pos(0, 0, thickness+.1)*mouth])
    body = body - [lower, upper]
    body.label = "tube_squeezer:rounded_through_slot_with_gentle_beveled_entries"
    body.color = Color(.55, .23, .045)
    return body


def gen_step():
    return build(**PARAMETERS)
