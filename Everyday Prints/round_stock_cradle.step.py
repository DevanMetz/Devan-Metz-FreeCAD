"""V cradle for round stock during hand layout; print the broad base down. mm."""
from build123d import Circle, Color, Plane, Polygon, Pos, RectangleRounded, extrude

PARAMETERS = dict(length=80.0,width=60.0,height=30.0,apex_height=8.0,
                  mount_hole=4.0,end_margin=10.0)


def build(*,length=80.0,width=60.0,height=30.0,apex_height=8.0,mount_hole=4.0,end_margin=10.0):
    if not (45 <= length <= 150 and 40 <= width <= 100 and 18 <= height <= 55
            and 6 <= apex_height <= 20 and 3 <= mount_hole <= 6 and 8 <= end_margin <= 20):
        raise ValueError("Cradle dimensions outside supported ranges.")
    depth = height-apex_height
    if depth < 8 or width/2-depth < mount_hole+4 or length-2*end_margin < mount_hole+4:
        raise ValueError("Preserve V depth and at least 2 mm around the mounting holes.")
    body = extrude(RectangleRounded(length,width,3),amount=height)
    groove = Plane.YZ*Polygon((-depth-1,height+1),(0,apex_height),(depth+1,height+1),align=None)
    body -= Pos(-length/2-1,0,0)*extrude(groove,amount=length+2,dir=(1,0,0))
    y = (width/2+depth)/2
    for x in (-length/2+end_margin,length/2-end_margin):
        for sign in (-1,1):
            body -= Pos(x,sign*y,-1)*extrude(Circle(mount_hole/2),amount=height+2)
    body.label = "round_stock_cradle:90_degree_V_open_ends_four_mounting_holes"
    body.color = Color(.26,.32,.19)
    return body


def gen_step():
    return build(**PARAMETERS)
