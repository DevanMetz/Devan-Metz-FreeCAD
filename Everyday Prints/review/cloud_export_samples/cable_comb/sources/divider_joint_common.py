"""Shared drawer-divider joint geometry. Dimensions are mm; bed is Z=0."""
from build123d import Align, Color, Pos, Rectangle, RectangleRounded, Rot, extrude, loft

PARAMETERS = dict(board_thickness=3.0, clearance=.4, wall=2.4,
                  insertion_depth=16.0, height=18.0, floor=2.4, lead_in=.6,
                  ports=(0, 90, 180, 270))


def settings(overrides):
    if set(overrides)-set(PARAMETERS):
        raise ValueError(f"Unknown divider-joint parameters: {sorted(set(overrides)-set(PARAMETERS))}")
    p = PARAMETERS | overrides
    ports = p['ports']
    if (not isinstance(ports, (tuple, list)) or not 2 <= len(ports) <= 4
            or any(angle not in (0, 90, 180, 270) for angle in ports)
            or len(set(ports)) != len(ports)):
        raise ValueError("Choose two to four distinct cardinal ports: 0, 90, 180, 270 degrees.")
    p['ports'] = tuple(sorted(ports))
    if not (1 <= p['board_thickness'] <= 10 and .1 <= p['clearance'] <= 1.2
            and 2 <= p['wall'] <= 4 and 10 <= p['insertion_depth'] <= 30
            and 12 <= p['height'] <= 30 and 1.6 <= p['floor'] <= 4
            and .2 <= p['lead_in'] <= .8):
        raise ValueError("Divider-joint dimensions outside supported ranges.")
    radius = min(.6, p['wall']/4)
    if p['wall']-radius-p['lead_in'] < 1.2-1e-9 or p['height']-p['floor'] < 8:
        raise ValueError("Preserve 1.2 mm at rounded mouth tips and 8 mm of board engagement height.")
    return p


def dimensions(p):
    gap = p['board_thickness']+p['clearance']
    hub = gap+2*p['wall']
    return gap, hub, hub/2+p['insertion_depth']


def build(**overrides):
    p = settings(overrides)
    gap, hub, end = dimensions(p)
    radius = min(.6, p['wall']/4)
    profile = RectangleRounded(hub, hub, radius)
    branch = Pos(end/2, 0)*RectangleRounded(end, hub, radius)
    for angle in p['ports']:
        profile += Rot(0, 0, angle)*branch
    body = extrude(profile, amount=p['height'])
    length = p['insertion_depth']+1
    slot = Pos(hub/2, 0, p['floor'])*extrude(
        Rectangle(length, gap, align=(Align.MIN, Align.CENTER)),
        amount=p['height']-p['floor']+1)
    lead_height = p['lead_in']/.8
    lead = loft([
        Pos(hub/2, 0, p['height']-lead_height)*Rectangle(
            length, gap, align=(Align.MIN, Align.CENTER)),
        Pos(hub/2, 0, p['height'])*Rectangle(
            length, gap+2*p['lead_in'], align=(Align.MIN, Align.CENTER)),
    ])
    for angle in p['ports']:
        body -= Rot(0, 0, angle)*(slot+lead)
    body.label = "divider_joint:separate_board_ends_solid_hub_open_slots"
    body.color = Color(.30, .16, .035)
    return body
