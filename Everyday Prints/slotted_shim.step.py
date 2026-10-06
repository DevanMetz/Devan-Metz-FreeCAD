"""Flat removable spacing shim with an open bolt slot and hanging hole. mm."""
from build123d import Align, Box, Circle, Color, Pos, RectangleRounded, extrude

PARAMETERS = dict(length=40.0,width=24.0,thickness=2.0,bolt_diameter=6.0,
                  clearance=.6,slot_depth=28.0,corner_radius=3.0,hanging_hole=4.5)


def build(*,length=40.0,width=24.0,thickness=2.0,bolt_diameter=6.0,
          clearance=.6,slot_depth=28.0,corner_radius=3.0,hanging_hole=4.5):
    if not (24 <= length <= 100 and 16 <= width <= 60 and .8 <= thickness <= 10
            and 3 <= bolt_diameter <= 16 and .2 <= clearance <= 1.2
            and 12 <= slot_depth <= 80 and 1 <= corner_radius <= 6
            and (hanging_hole == 0 or 3 <= hanging_hole <= 8)):
        raise ValueError("Shim dimensions outside supported ranges.")
    slot = bolt_diameter+clearance
    back = length-slot_depth
    if (slot_depth < slot or back < max(6,hanging_hole+4)
            or width < slot+8 or corner_radius >= min(width,length)/2
            or slot/2+corner_radius > width/2-1):
        raise ValueError("Preserve the closed back, slot arms, and margins around the hanging hole.")
    body = extrude(RectangleRounded(length,width,corner_radius),amount=thickness)
    end = length/2-slot_depth+slot/2
    cut = Pos(end,0,-1)*extrude(Circle(slot/2),amount=thickness+2)
    cut += Pos(end,0,-1)*Box(length/2-end+1,slot,thickness+2,
                           align=(Align.MIN,Align.CENTER,Align.MIN))
    body -= cut
    if hanging_hole:
        body -= Pos(-length/2+back/2,0,-1)*extrude(Circle(hanging_hole/2),amount=thickness+2)
    body.label = "slotted_shim:constant_thickness_rounded_open_bolt_slot_closed_back"
    body.color = Color(.41,.22,.09)
    return body


def gen_step():
    return build(**PARAMETERS)
