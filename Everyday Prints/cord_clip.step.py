"""Trial flexure clip for a cord; print an end profile down, adhesive foot faces -Y. mm."""
from build123d import Align, Axis, Box, Circle, Color, Pos, RectangleRounded, extrude, fillet

PARAMETERS = dict(cable_diameter=6.0,clearance=.6,capture=.8,arm_thickness=1.0,
                  base_width=20.0,base_thickness=3.0,depth=12.0,tip_radius=.2)


def build(*,cable_diameter=6.0,clearance=.6,capture=.8,arm_thickness=1.0,
          base_width=20.0,base_thickness=3.0,depth=12.0,tip_radius=.2):
    if not (3 <= cable_diameter <= 12 and .3 <= clearance <= 1 and .2 <= capture <= 1.2
            and .8 <= arm_thickness <= 1.6 and 12 <= base_width <= 36
            and 2.4 <= base_thickness <= 5 and 8 <= depth <= 20 and .15 <= tip_radius <= .3):
        raise ValueError("Cord-clip parameters outside supported ranges.")
    inner = (cable_diameter+clearance)/2
    outer = inner+arm_thickness
    entry = cable_diameter-capture
    if (capture > cable_diameter*.2 or base_width < 2*outer+4
            or tip_radius > arm_thickness/4 or outer-tip_radius <= entry/2+tip_radius):
        raise ValueError("Preserve conservative entry capture, foot margins, and enough material to round the tips.")
    center = base_thickness+inner
    body = Pos(0,base_thickness/2,0)*extrude(RectangleRounded(base_width,base_thickness,1),amount=depth)
    body += Pos(0,center,0)*extrude(Circle(outer),amount=depth)
    body -= Pos(0,center,-1)*extrude(Circle(inner),amount=depth+2)
    body -= Pos(0,center,-1)*Box(entry,outer+1,depth+2,align=(Align.CENTER,Align.MIN,Align.MIN))
    tips = [e for e in body.edges().filter_by(Axis.Z)
            if abs(abs(e.center().X)-entry/2) < 1e-5 and e.center().Y > center]
    if len(tips) != 4:
        raise ValueError("Expected four vertical tip edges for entry rounding.")
    body = fillet(tips,radius=tip_radius)
    body.label = "cord_clip:trial_flexure_rounded_C_arms_flat_adhesive_foot"
    body.color = Color(.09,.34,.41)
    return body


def gen_step():
    return build(**PARAMETERS)
