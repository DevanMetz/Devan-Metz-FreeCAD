"""Parametric corner pad for a hand-tensioned strap clamp. Dimensions in mm."""
from build123d import Circle,Color,Pos,Rectangle,extrude,loft

PARAMETERS = dict(leg_length=30.0,wall=6.0,corner_relief=3.0,strap_width=25.0,
                  strap_thickness=1.2,width_clearance=2.0,lip_projection=2.0,lip_thickness=2.0)


def settings(overrides):
    if set(overrides)-set(PARAMETERS):
        raise ValueError(f"Unknown strap-corner parameters: {sorted(set(overrides)-set(PARAMETERS))}")
    p = PARAMETERS | overrides
    if not (18 <= p['leg_length'] <= 55 and 4 <= p['wall'] <= 10
            and 2 <= p['corner_relief'] <= 5 and 8 <= p['strap_width'] <= 45
            and .6 <= p['strap_thickness'] <= 2.4 and 1 <= p['width_clearance'] <= 3
            and 1.2 <= p['lip_projection'] <= 3.2 and 1.6 <= p['lip_thickness'] <= 3.2):
        raise ValueError("Strap-corner dimensions outside supported ranges.")
    if (p['wall']-p['corner_relief'] < 2.4 or p['leg_length']-p['corner_relief'] < 14
            or p['lip_projection'] < p['strap_thickness']+.4):
        raise ValueError("Preserve the rounded corner bridge, contact faces, and lips beyond the strap.")
    return p


def height(p):
    return 2*p['lip_thickness']+p['strap_width']+p['width_clearance']+p['lip_projection']/.8


def corner_profile(length,thickness,relief):
    # The workpiece occupies X>=0,Y>=0. Both inner faces register at zero;
    # the southwest quarter-circle joins the straight outer strap-bearing faces.
    shape = Pos(length/2,-thickness/2)*Rectangle(length,thickness)
    shape += Pos(-thickness/2,length/2)*Rectangle(thickness,length)
    shape += Circle(thickness) & (Pos(-thickness/2,-thickness/2)*Rectangle(thickness,thickness))
    return shape-Circle(relief)


def build(**overrides):
    p = settings(overrides)
    core = corner_profile(p['leg_length'],p['wall'],p['corner_relief'])
    flange = corner_profile(p['leg_length'],p['wall']+p['lip_projection'],p['corner_relief'])
    upper_start = p['lip_thickness']+p['strap_width']+p['width_clearance']
    ramp_height = p['lip_projection']/.8
    body = extrude(core,amount=height(p))
    body += extrude(flange,amount=p['lip_thickness'])
    body += loft([Pos(0,0,upper_start)*core,Pos(0,0,upper_start+ramp_height)*flange])
    body += Pos(0,0,upper_start+ramp_height)*extrude(flange,amount=p['lip_thickness'])
    body.label = "strap_corner:90_degree_faces_corner_relief_rounded_path_guide_lips"
    body.color = Color(.07,.34,.36)
    return body
