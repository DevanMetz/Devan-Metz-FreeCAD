"""Short slip-fit socket sample. Clearance is total added diameter. mm."""
from build123d import Axis, Color, Plane, Polygon, revolve

PARAMETERS = dict(tube_diameter=50.0,clearance=.4,wall=2.4,height=8.0,lead_in=.6)


def build(*,tube_diameter=50.0,clearance=.4,wall=2.4,height=8.0,lead_in=.6):
    if not (12 <= tube_diameter <= 120 and .1 <= clearance <= 1.2
            and 2 <= wall <= 5 and 5 <= height <= 15 and .3 <= lead_in <= 1.2):
        raise ValueError("Socket sample dimensions outside supported ranges.")
    entry_height = lead_in/.8
    if wall-lead_in < 1.4 or height-2*entry_height < 3:
        raise ValueError("Preserve the entry wall and at least 3 mm of working bore.")
    radius = (tube_diameter+clearance)/2
    section = Plane.XZ*Polygon(
        (radius+lead_in,0),(radius+wall,0),(radius+wall,height),
        (radius+lead_in,height),(radius,height-entry_height),
        (radius,entry_height),align=None)
    body = revolve(section,axis=Axis.Z)
    body.label = "socket_fit_ring:open_bore_two_entry_leads"
    body.color = Color(.88,.42,.13)
    return body


def gen_step():
    return build(**PARAMETERS)
