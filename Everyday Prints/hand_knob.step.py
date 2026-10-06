"""Six-lobed hand knob for a measured hex nut. Print nut pocket upward. mm."""
from math import cos, sin, radians, sqrt
from build123d import Axis, Circle, Color, Pos, RegularPolygon, extrude, fillet, loft

PARAMETERS = dict(grip_diameter=40.0,lobe_radius=6.0,height=14.0,
                  nut_af=10.0,nut_thickness=5.0,nut_clearance=.3,pocket_extra_depth=.4,
                  bolt_diameter=6.0,bolt_clearance=.6,lead_in=.4,valley_radius=.8)


def build(*,grip_diameter=40.0,lobe_radius=6.0,height=14.0,
          nut_af=10.0,nut_thickness=5.0,nut_clearance=.3,pocket_extra_depth=.4,
          bolt_diameter=6.0,bolt_clearance=.6,lead_in=.4,valley_radius=.8):
    if not (30 <= grip_diameter <= 80 and 4 <= lobe_radius <= 10 and 10 <= height <= 28
            and 7 <= nut_af <= 20 and 3 <= nut_thickness <= 10 and .1 <= nut_clearance <= .8
            and .2 <= pocket_extra_depth <= 1 and 3 <= bolt_diameter <= 12
            and .3 <= bolt_clearance <= 1 and .3 <= lead_in <= .8 and .4 <= valley_radius <= 1.4):
        raise ValueError("Knob, nut, or clearance dimensions outside supported ranges.")
    core = grip_diameter/2-lobe_radius
    socket_af = nut_af+nut_clearance
    pocket_floor = height-nut_thickness-pocket_extra_depth
    bore = (bolt_diameter+bolt_clearance)/2
    if (core < 2.3*lobe_radius or valley_radius > .15*lobe_radius
            or core < (socket_af+2*lead_in)/sqrt(3)+3
            or pocket_floor < 3 or bore > nut_af/2-1):
        raise ValueError("Preserve rounded grip valleys, socket walls, bearing floor, and nut support around the bolt.")
    profile = Circle(core)
    for angle in range(0,360,60):
        profile += Pos(core*cos(radians(angle)),core*sin(radians(angle)))*Circle(lobe_radius)
    body = extrude(profile,amount=height)
    body = fillet(body.edges().filter_by(Axis.Z),radius=valley_radius)
    body -= Pos(0,0,-1)*extrude(Circle(bore),amount=height+2)
    socket = RegularPolygon(socket_af/sqrt(3),6)
    body -= Pos(0,0,pocket_floor)*extrude(socket,amount=height-pocket_floor+1)
    wide = RegularPolygon((socket_af+2*(lead_in+.1))/sqrt(3),6)
    body -= loft([Pos(0,0,height-lead_in)*socket,Pos(0,0,height+.1)*wide])
    body.label = "hand_knob:six_rounded_lobes_open_hex_nut_pocket_through_bolt_bore"
    body.color = Color(.15,.25,.42)
    return body


def gen_step():
    return build(**PARAMETERS)
