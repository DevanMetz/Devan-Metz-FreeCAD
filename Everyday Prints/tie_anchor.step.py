"""Two-direction cable-tie anchor with peaked threading passages. mm."""
from build123d import Circle, Color, Plane, Polygon, Pos, RectangleRounded, extrude

PARAMETERS = dict(side=26.0,tunnel_width=4.8,straight_height=1.6,floor=1.6,
                  roof=2.4,mount_hole=3.5,mount_inset=5.0)


def build(*,side=26.0,tunnel_width=4.8,straight_height=1.6,floor=1.6,
          roof=2.4,mount_hole=3.5,mount_inset=5.0):
    if not (20 <= side <= 40 and 3 <= tunnel_width <= 9 and 1.2 <= straight_height <= 3
            and 1.6 <= floor <= 3.2 and 2 <= roof <= 4 and 3.2 <= mount_hole <= 5
            and 4.5 <= mount_inset <= 8):
        raise ValueError("Anchor or passage dimensions outside supported ranges.")
    offset = side/2-mount_inset
    if mount_inset < mount_hole/2+2 or offset-mount_hole/2-tunnel_width/2 < 2:
        raise ValueError("Leave 2 mm between mounting holes, passages, and outside edges.")
    rise = tunnel_width/2/.8
    peak = floor+straight_height+rise
    height = peak+roof
    body = extrude(RectangleRounded(side,side,3),amount=height)
    points = ((-tunnel_width/2,floor),(tunnel_width/2,floor),
              (tunnel_width/2,floor+straight_height),(0,peak),
              (-tunnel_width/2,floor+straight_height))
    x_passage = Plane.YZ*Polygon(*points,align=None)
    y_passage = Plane.XZ*Polygon(*points,align=None)
    body -= Pos(-side/2-1,0,0)*extrude(x_passage,amount=side+2,dir=(1,0,0))
    body -= Pos(0,side/2+1,0)*extrude(y_passage,amount=side+2)
    for sign in (-1,1):
        body -= Pos(sign*offset,sign*offset,-1)*extrude(Circle(mount_hole/2),amount=height+2)
    body.label = "tie_anchor:crossed_peaked_tunnels_two_diagonal_mounting_holes"
    body.color = Color(.30,.20,.13)
    return body


def gen_step():
    return build(**PARAMETERS)
