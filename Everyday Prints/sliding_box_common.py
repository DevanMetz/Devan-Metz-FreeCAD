"""Shared mm dimensions for a sliding-lid box and a short rail-fit pair."""
from build123d import Align, Box, Color, Plane, Polygon, Pos, Rectangle, RectangleRounded, extrude, loft

PARAMETERS = dict(length=120.0,width=80.0,height=32.0,wall=2.4,floor=2.4,
                  lid_thickness=2.4,side_clearance=.3,vertical_clearance=.3,
                  roof=1.6,ledge_inset=3.2,end_clearance=.4,pull_extension=6.0,
                  grip_height=3.0,sample_length=30.0,sample_height=16.0)
SLOPE = .8  # Horizontal growth per layer height: 38.7 degrees from vertical.


def settings(overrides):
    if set(overrides)-set(PARAMETERS):
        raise ValueError(f"Unknown box parameters: {sorted(set(overrides)-set(PARAMETERS))}")
    p = PARAMETERS | overrides
    if not (70 <= p['length'] <= 180 and 50 <= p['width'] <= 140 and 22 <= p['height'] <= 60
            and 2 <= p['wall'] <= 4 and 2 <= p['floor'] <= 4 and 1.8 <= p['lid_thickness'] <= 4
            and .15 <= p['side_clearance'] <= 1 and .2 <= p['vertical_clearance'] <= 1
            and 1.2 <= p['roof'] <= 3 and 2.4 <= p['ledge_inset'] <= 5
            and .2 <= p['end_clearance'] <= 1 and 4 <= p['pull_extension'] <= 12
            and 2 <= p['grip_height'] <= 5 and 20 <= p['sample_length'] <= 45
            and 12 <= p['sample_height'] <= 24):
        raise ValueError("Box, lid, clearance, or sample dimensions outside supported ranges.")
    if (rail_inset(p)-p['side_clearance'] < .8 or p['ledge_inset']-p['side_clearance'] < 1.4
            or lid_width(p)-2*SLOPE*p['lid_thickness'] < 32):
        raise ValueError("Preserve retaining overlap, bottom support, and room for the pull grip.")
    for height in (p['height'],p['sample_height']):
        if ledge_z(p,height)-p['ledge_inset']/SLOPE < p['floor']+2:
            raise ValueError("Leave space below the sloped supports and above the floor.")
    return p


def rail_inset(p):
    return SLOPE*(p['lid_thickness']+p['vertical_clearance'])


def ledge_z(p,height):
    return height-p['roof']-p['lid_thickness']-p['vertical_clearance']


def lid_width(p):
    return p['width']-2*p['wall']-2*p['side_clearance']


def add_guides(body,p,length,height):
    inner = p['width']/2-p['wall']
    z = ledge_z(p,height)
    for sign in (-1,1):
        support = Plane.YZ*Polygon((sign*inner,z-p['ledge_inset']/SLOPE),
                                   (sign*inner,z),(sign*(inner-p['ledge_inset']),z),align=None)
        lip = Plane.YZ*Polygon((sign*inner,z),(sign*inner,height),
                               (sign*(inner-rail_inset(p)),height),
                               (sign*(inner-rail_inset(p)),height-p['roof']),align=None)
        # Explicit direction gives both mirrored profiles the same X extrusion.
        body += Pos(-length/2,0,0)*extrude(support,amount=length,dir=(1,0,0))
        body += Pos(-length/2,0,0)*extrude(lip,amount=length,dir=(1,0,0))
    return body


def build_box(**overrides):
    p = settings(overrides)
    l,w,h = p['length'],p['width'],p['height']
    body = extrude(RectangleRounded(l,w,p['wall']),amount=h)
    body -= Pos(0,0,p['floor'])*extrude(Rectangle(l-2*p['wall'],w-2*p['wall']),amount=h+1)
    body = add_guides(body,p,l,h)
    y,z = w/2-p['wall'],ledge_z(p,h)
    inset = rail_inset(p)
    mouth = Plane.YZ*Polygon((-y,z),(y,z),(y-inset,h-p['roof']),
                             (y-inset,h+1),(-y+inset,h+1),(-y+inset,h-p['roof']),align=None)
    body -= Pos(-l/2-.5,0,0)*extrude(mouth,amount=p['wall']+1,dir=(1,0,0))
    body.label = "sliding_box:closed_floor_sloped_guides_front_entry_back_stop"
    body.color = Color(.20,.16,.38)
    return body


def lid_shape(p,length):
    width = lid_width(p)
    body = loft([Rectangle(length,width),
                 Pos(0,0,p['lid_thickness'])*Rectangle(length,width-2*SLOPE*p['lid_thickness'])])
    # Small 45-degree lead at the lower rear edge helps it enter the channel.
    lead = Plane.XZ*Polygon((length/2-.7,-.1),(length/2+1,-.1),(length/2+1,1.6),align=None)
    body -= Pos(0,width/2+1,0)*extrude(lead,amount=width+2)
    grip = Pos(-length/2+p['pull_extension']/2,0,p['lid_thickness'])*Box(
        p['pull_extension']-2,24,p['grip_height'],align=(Align.CENTER,Align.CENTER,Align.MIN))
    body += grip
    body.color = Color(.56,.44,.27)
    return body


def build_lid(**overrides):
    p = settings(overrides)
    length = p['length']-p['wall']-p['end_clearance']+p['pull_extension']
    body = lid_shape(p,length)
    body.label = "sliding_lid:wide_face_down_angled_sides_rear_lead_pull_grip"
    return body


def build_fit_channel(**overrides):
    p = settings(overrides)
    l,w,h = p['sample_length'],p['width'],p['sample_height']
    body = Box(l,w,h,align=(Align.CENTER,Align.CENTER,Align.MIN))
    body -= Pos(0,0,p['floor'])*Box(l+2,w-2*p['wall'],h+1,
                                  align=(Align.CENTER,Align.CENTER,Align.MIN))
    body = add_guides(body,p,l,h)
    body.label = "sliding_fit_channel:short_open_ended_sample_of_full_box_guides"
    body.color = Color(.30,.25,.48)
    return body


def build_fit_slider(**overrides):
    p = settings(overrides)
    body = lid_shape(p,p['sample_length']+p['pull_extension'])
    body.label = "sliding_fit_slider:short_sample_of_full_lid_profile"
    return body
