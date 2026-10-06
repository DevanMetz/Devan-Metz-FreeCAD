"""Spoked roll-core to axle adapter. Print two flange down; measure the roll. mm."""
from math import pi, sin, sqrt
from build123d import Align, Box, Circle, Color, Pos, Rot, extrude, loft

PARAMETERS = dict(roll_bore=52.0,outer_clearance=.4,axle_diameter=8.0,axle_clearance=.6,
                  insertion_depth=15.0,wall=2.4,hub_wall=3.0,flange_extra=4.0,
                  flange_thickness=2.4,spoke_count=6,spoke_thickness=3.0,lead_in=.6)


def build(*,roll_bore=52.0,outer_clearance=.4,axle_diameter=8.0,axle_clearance=.6,
          insertion_depth=15.0,wall=2.4,hub_wall=3.0,flange_extra=4.0,
          flange_thickness=2.4,spoke_count=6,spoke_thickness=3.0,lead_in=.6):
    if not (25 <= roll_bore <= 100 and .2 <= outer_clearance <= 1.2
            and 3 <= axle_diameter <= 20 and .3 <= axle_clearance <= 1.2
            and 8 <= insertion_depth <= 35 and 2 <= wall <= 4 and 2.4 <= hub_wall <= 5
            and 3 <= flange_extra <= 8 and 2 <= flange_thickness <= 5
            and isinstance(spoke_count,int) and 3 <= spoke_count <= 8
            and 2.4 <= spoke_thickness <= 6 and .3 <= lead_in <= 1.2):
        raise ValueError("Adapter dimensions outside supported ranges.")
    outer = (roll_bore-outer_clearance)/2
    inner = outer-wall
    bore = (axle_diameter+axle_clearance)/2
    hub = bore+hub_wall
    height = flange_thickness+insertion_depth
    tip_height = lead_in/.8
    spoke_end = inner+wall/2
    if (min(wall,hub_wall)-lead_in < 1.6 or inner-hub < 5
            or spoke_thickness >= 2*hub*sin(pi/spoke_count)
            or sqrt(spoke_end**2+(spoke_thickness/2)**2) >= outer-lead_in-.1):
        raise ValueError("Preserve the tapered walls, open sectors, and spoke ends inside the insertion envelope.")
    body = extrude(Circle(outer)-Circle(inner),amount=height-tip_height)
    tip = loft([Pos(0,0,height-tip_height)*Circle(outer),Pos(0,0,height)*Circle(outer-lead_in)])
    tip -= Pos(0,0,height-tip_height-.1)*extrude(Circle(inner),amount=tip_height+.2)
    body += tip
    body += extrude(Circle(roll_bore/2+flange_extra)-Circle(inner),amount=flange_thickness)
    body += extrude(Circle(hub),amount=height)
    for index in range(spoke_count):
        body += Rot(0,0,index*360/spoke_count)*Box(spoke_end,spoke_thickness,height,
                                                 align=(Align.MIN,Align.CENTER,Align.MIN))
    body -= Pos(0,0,-1)*extrude(Circle(bore),amount=height+2)
    body -= loft([Pos(0,0,height-tip_height)*Circle(bore),
                  Pos(0,0,height+.1)*Circle(bore+lead_in+.08)])
    body.label = f"roll_adapter:{spoke_count}_spokes_flange_tapered_sleeve_open_axle_bore"
    body.color = Color(.16,.29,.19)
    return body


def gen_step():
    return build(**PARAMETERS)
