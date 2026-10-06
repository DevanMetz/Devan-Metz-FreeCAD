"""Measured smooth-tube reducer. Print large mouth down. Dimensions in mm."""
from math import sqrt
from build123d import Axis, Color, Plane, Polygon, revolve

PARAMETERS = dict(large_diameter=50.0,small_diameter=32.0,large_clearance=.4,
                  small_clearance=.4,wall=2.4,large_depth=22.0,small_depth=20.0,
                  transition_length=30.0,stop_inset=2.0,lead_in=.6)


def build(*,large_diameter=50.0,small_diameter=32.0,large_clearance=.4,
          small_clearance=.4,wall=2.4,large_depth=22.0,small_depth=20.0,
          transition_length=30.0,stop_inset=2.0,lead_in=.6):
    if not (20 <= large_diameter <= 120 and 12 <= small_diameter <= 90
            and .1 <= large_clearance <= 1.2 and .1 <= small_clearance <= 1.2
            and 2 <= wall <= 5 and 10 <= large_depth <= 45 and 10 <= small_depth <= 45
            and 12 <= transition_length <= 90 and 1.2 <= stop_inset <= 4
            and .3 <= lead_in <= 1.2):
        raise ValueError("Reducer dimensions outside supported ranges.")
    large = (large_diameter+large_clearance)/2
    small = (small_diameter+small_clearance)/2
    throat = small-stop_inset
    slope = (large-throat)/transition_length
    if (large_diameter-small_diameter < 8 or throat < 4
            or not 0 < slope <= .8 or wall/sqrt(1+slope*slope) < 1.6
            or wall-lead_in < 1.4 or stop_inset-small_clearance/2 < 1):
        raise ValueError("Preserve the flow passage, stop land, entry walls, and supported print slopes.")
    shoulder = large_depth+transition_length
    height = shoulder+small_depth
    entry_height = lead_in/.8
    # Radial/height section. The lower opening faces the bed; its inward
    # entry lead and the inner transition stay below 45 degrees from vertical.
    section = Plane.XZ*Polygon(
        (large+lead_in,0),(large+wall,0),(large+wall,large_depth),
        (small+wall,shoulder),(small+wall,height),(small+lead_in,height),
        (small,height-entry_height),(small,shoulder),(throat,shoulder),
        (large,large_depth),(large,entry_height),align=None)
    body = revolve(section,axis=Axis.Z)
    body.label = "tube_reducer:large_mouth_down_small_socket_stop_open_bore"
    body.color = Color(.065,.33,.34)
    return body


def gen_step():
    return build(**PARAMETERS)
