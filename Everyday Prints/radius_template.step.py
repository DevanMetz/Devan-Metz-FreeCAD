"""Four outside corner radii with recessed tick identifiers; mm, font-free."""
from build123d import Align, Box, CenterArc, Circle, Color, Face, Line, Pos, Wire, extrude

PARAMETERS = dict(side=80.0, thickness=3.0, radii=(5.0,10.0,15.0,20.0), finger_hole=20.0)


def build(*, side=80.0, thickness=3.0, radii=(5.0,10.0,15.0,20.0), finger_hole=20.0):
    if not (50 <= side <= 140 and 2 <= thickness <= 6 and len(radii) == 4
            and all(2 <= r < side/2 for r in radii) and 10 <= finger_hole <= side/3):
        raise ValueError("Template dimensions or corner radii outside supported ranges.")
    half = side/2
    a,b,c,d = radii  # Bottom-left, bottom-right, top-right, top-left as viewed from above.
    outline = Wire([
        Line((-half+a,-half),(half-b,-half)),
        CenterArc((half-b,-half+b),b,-90,90),
        Line((half,-half+b),(half,half-c)),
        CenterArc((half-c,half-c),c,0,90),
        Line((half-c,half),(-half+d,half)),
        CenterArc((-half+d,half-d),d,90,90),
        Line((-half,half-d),(-half,-half+a)),
        CenterArc((-half+a,-half+a),a,180,90)])
    body = extrude(Face(outline),amount=thickness)
    body -= Pos(0,0,-1)*extrude(Circle(finger_hole/2),amount=thickness+2)
    for index,(sx,sy) in enumerate(((-1,-1),(1,-1),(1,1),(-1,1))):
        for tick in range(index+1):
            body -= Pos(sx*side*.28+(tick-index/2)*1.8,sy*side*.28,thickness-.6)*Box(
                .8,3,1,align=(Align.CENTER,Align.CENTER,Align.MIN))
    body.label = "radius_template:four_marking_corners_one_to_four_tick_ids"
    body.color = Color(.32,.12,.48)
    return body


def gen_step():
    return build(**PARAMETERS)
