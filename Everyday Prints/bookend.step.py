"""Bookend with a flat book face and rear braces. Print the broad foot down. mm."""
from build123d import Align, Box, Color, Plane, Polygon, Pos, RectangleRounded, extrude

PARAMETERS = dict(front_depth=100.0,back_depth=30.0,width=80.0,height=130.0,
                  floor=4.0,wall=4.0,brace_height=90.0,brace_width=4.0,corner_radius=3.0)


def build(*,front_depth=100.0,back_depth=30.0,width=80.0,height=130.0,
          floor=4.0,wall=4.0,brace_height=90.0,brace_width=4.0,corner_radius=3.0):
    if not (60 <= front_depth <= 150 and 20 <= back_depth <= 45 and 60 <= width <= 140
            and 80 <= height <= 180 and 3 <= floor <= 5 and 3 <= wall <= 6
            and 45 <= brace_height <= 135 and 3.2 <= brace_width <= 6 and 2 <= corner_radius <= 5):
        raise ValueError("Bookend dimensions outside supported ranges.")
    rise = height-floor
    window_width,window_height = .24*width,.55*rise
    if (brace_height > rise-10 or back_depth-corner_radius-wall < 12
            or .06*width-brace_width/2 < 1.5
            or .1*width-brace_width/2 < corner_radius
            or window_width/window_height > .8):
        raise ValueError("Preserve useful rear braces, window margins, and printable pointed window roofs.")
    body = Pos((front_depth-back_depth)/2,0,0)*extrude(
        RectangleRounded(front_depth+back_depth,width,corner_radius),amount=floor)
    body += Pos(-wall,0,floor)*Box(wall,width,rise,align=(Align.MIN,Align.CENTER,Align.MIN))
    brace = Plane.XZ*Polygon((-back_depth+corner_radius,floor),(-wall,floor),
                             (-wall,floor+brace_height),align=None)
    for sign in (-1,1):
        body += Pos(0,sign*.4*width-brace_width/2,0)*extrude(brace,amount=brace_width,dir=(0,1,0))
    bottom = floor+.2*rise
    for sign in (-1,1):
        center = sign*.22*width
        window = Plane.YZ*Polygon((center,bottom),(center+window_width/2,bottom+window_height/2),
                                   (center,bottom+window_height),(center-window_width/2,bottom+window_height/2),
                                   align=None)
        body -= Pos(-wall-1,0,0)*extrude(window,amount=wall+2,dir=(1,0,0))
    lead_length,tip_height = 2*floor,1.2
    outside_tip = tip_height-(floor-tip_height)/lead_length
    lead = Plane.XZ*Polygon((front_depth-lead_length,floor),(front_depth+1,outside_tip),
                            (front_depth+1,floor+1),(front_depth-lead_length,floor+1),align=None)
    body -= Pos(0,-width/2-1,0)*extrude(lead,amount=width+2,dir=(0,1,0))
    body.label = "bookend:flat_front_rear_braces_pointed_windows_tapered_foot"
    body.color = Color(.24,.22,.37)
    return body


def gen_step():
    return build(**PARAMETERS)
