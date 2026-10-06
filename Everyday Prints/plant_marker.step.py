"""Blank pot label with a tapered stake and rounded neck. Print either flat face down. mm."""
from build123d import Axis, Circle, Color, Polygon, Pos, RectangleRounded, extrude, fillet

PARAMETERS = dict(label_width=26.0,label_height=45.0,stake_length=70.0,stake_width=8.0,
                  thickness=2.4,tip_length=15.0,tip_width=1.2,corner_radius=3.0,
                  neck_radius=2.0,hanging_hole=3.5)


def build(*,label_width=26.0,label_height=45.0,stake_length=70.0,stake_width=8.0,
          thickness=2.4,tip_length=15.0,tip_width=1.2,corner_radius=3.0,
          neck_radius=2.0,hanging_hole=3.5):
    if not (20 <= label_width <= 50 and 30 <= label_height <= 70 and 35 <= stake_length <= 120
            and 6 <= stake_width <= 14 and 1.6 <= thickness <= 4 and 8 <= tip_length <= 25
            and .8 <= tip_width <= 2 and 2 <= corner_radius <= 5 and 1 <= neck_radius <= 3
            and (hanging_hole == 0 or 3 <= hanging_hole <= 6)):
        raise ValueError("Marker dimensions outside supported ranges.")
    if (stake_length-tip_length < 20 or label_width < stake_width+2*neck_radius+2*corner_radius
            or tip_width >= stake_width/2 or label_width < hanging_hole+2*corner_radius+4):
        raise ValueError("Preserve useful stake length, a narrow flat tip, and space for the rounded neck and hole.")
    body = Pos(0,label_height/2,0)*extrude(RectangleRounded(label_width,label_height,corner_radius),amount=thickness)
    outline = Polygon((-stake_width/2,corner_radius),(stake_width/2,corner_radius),
                      (stake_width/2,-stake_length+tip_length),(tip_width/2,-stake_length),
                      (-tip_width/2,-stake_length),(-stake_width/2,-stake_length+tip_length),align=None)
    body += extrude(outline,amount=thickness,dir=(0,0,1))
    neck = [e for e in body.edges().filter_by(Axis.Z)
            if abs(e.center().Y) < 1e-6 and abs(abs(e.center().X)-stake_width/2) < 1e-6]
    if len(neck) != 2:
        raise ValueError("Expected two neck corners for rounding.")
    body = fillet(neck,radius=neck_radius)
    if hanging_hole:
        hole_y = label_height-corner_radius-hanging_hole/2-1.5
        body -= Pos(0,hole_y,-1)*extrude(Circle(hanging_hole/2),amount=thickness+2)
    body.label = "plant_marker:blank_rounded_label_blended_neck_tapered_flat_tip"
    body.color = Color(.22,.34,.11)
    return body


def gen_step():
    return build(**PARAMETERS)
