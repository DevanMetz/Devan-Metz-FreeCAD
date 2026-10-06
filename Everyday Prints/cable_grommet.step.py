"""Unlatched C-shaped sleeve for a circular desk opening. Print flange down. mm."""
from build123d import Align, Box, Circle, Color, Pos, extrude, loft

PARAMETERS = dict(hole_diameter=60.0, clearance=.4, wall=2.0, flange_width=4.0,
                  flange_thickness=2.4, insertion_depth=16.0, opening=10.0,
                  lead_in=.6)


def build(*, hole_diameter=60.0, clearance=.4, wall=2.0, flange_width=4.0,
          flange_thickness=2.4, insertion_depth=16.0, opening=10.0, lead_in=.6):
    if not (25 <= hole_diameter <= 100 and .2 <= clearance <= 1.2 and 2 <= wall <= 4
            and 3 <= flange_width <= 8 and 2 <= flange_thickness <= 4
            and 6 <= insertion_depth <= 30 and 0 <= opening <= 25 and .3 <= lead_in <= 1):
        raise ValueError("Grommet dimensions outside supported ranges.")
    outside = (hole_diameter-clearance)/2
    inside = outside-wall
    rim = hole_diameter/2+flange_width
    total = flange_thickness+insertion_depth
    if inside < 8 or opening > inside or lead_in > wall-1 or flange_thickness < lead_in/.8+.8:
        raise ValueError("Preserve the bore, flange, sleeve tip, and C-shaped side walls.")
    body = extrude(Circle(rim), amount=flange_thickness)
    body += extrude(Circle(outside), amount=total-lead_in/.8)
    body += loft([Pos(0,0,total-lead_in/.8)*Circle(outside),
                  Pos(0,0,total)*Circle(outside-lead_in)])
    bore = Pos(0,0,-1)*extrude(Circle(inside), amount=total+2)
    # A 38.7-degree entry at the flange reduces the abrupt inside edge.
    entry = loft([Pos(0,0,-.1)*Circle(inside+lead_in+.08),
                  Pos(0,0,lead_in/.8)*Circle(inside)])
    body = body-bore-entry
    if opening:
        body -= Pos(0,0,-1)*Box(rim+1,opening,total+2,
                                align=(Align.MIN,Align.CENTER,Align.MIN))
    body.label = "cable_grommet:flange_down_unlatched_sleeve_side_entry"
    body.color = Color(.18,.18,.21)
    return body


def gen_step():
    return build(**PARAMETERS)
