"""Two-pin center finder for parallel-edged stock. Print plate down; invert to use. mm."""
from build123d import Circle, Color, Pos, SlotOverall, extrude, loft

PARAMETERS = dict(pin_spacing=80.0, pin_diameter=8.0, pin_height=12.0,
                  plate_width=24.0, plate_thickness=4.0, end_margin=10.0, mark_hole=3.2)


def build(*, pin_spacing=80.0, pin_diameter=8.0, pin_height=12.0,
          plate_width=24.0, plate_thickness=4.0, end_margin=10.0, mark_hole=3.2):
    if not (40 <= pin_spacing <= 160 and 5 <= pin_diameter <= 14 and 6 <= pin_height <= 24
            and 14 <= plate_width <= 40 and 2.4 <= plate_thickness <= 6
            and 6 <= end_margin <= 20 and 1.5 <= mark_hole <= 6):
        raise ValueError("Center-finder parameters outside supported ranges.")
    if plate_width < pin_diameter+8 or end_margin < pin_diameter/2+3:
        raise ValueError("Leave material around the pins and at both ends of the bridge.")
    body = extrude(SlotOverall(pin_spacing+2*end_margin,plate_width),amount=plate_thickness)
    for x in (-pin_spacing/2,pin_spacing/2):
        stem = Pos(x,0,plate_thickness-.1)*extrude(Circle(pin_diameter/2),amount=pin_height-.75+.1)
        tip = loft([Pos(x,0,plate_thickness+pin_height-.75)*Circle(pin_diameter/2),
                    Pos(x,0,plate_thickness+pin_height)*Circle(pin_diameter/2-.6)])
        body = body+stem+tip
    body -= Pos(0,0,-1)*extrude(Circle(mark_hole/2),amount=plate_thickness+2)
    # In use, the bed face points upward. This entry helps the pencil reach the
    # straight bore while keeping the print's inward slope below 45 degrees.
    entry = loft([Pos(0,0,-.1)*Circle(mark_hole/2+.88),
                  Pos(0,0,1)*Circle(mark_hole/2)])
    body -= entry
    body.label = "center_finder:equal_contact_pins_midpoint_marking_hole"
    body.color = Color(.62,.29,.045)
    return body


def gen_step():
    return build(**PARAMETERS)
