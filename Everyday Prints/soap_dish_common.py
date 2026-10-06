"""Shared dimensions for a removable draining soap dish. Apache-2.0; mm.

Edit PARAMETERS here to resize the tray, insert, and assembly together.
Each print has its bed at Z=0. Turn the printed insert over for use.
"""
from math import floor as integer_floor
from build123d import Align, Box, Color, Cylinder, Pos, RectangleRounded, SlotOverall, extrude

PARAMETERS = dict(length=120.0, width=84.0, height=14.0, wall=2.4, floor=2.4,
                  outer_radius=6.0, side_clearance=1.0, plate=3.0, foot_height=8.0,
                  foot_diameter=8.0, slot_width=5.0, web=3.0, drain_margin=12.0)


def settings(overrides):
    unknown = set(overrides) - set(PARAMETERS)
    if unknown:
        raise ValueError(f"Unknown parameters: {sorted(unknown)}")
    p = PARAMETERS | overrides
    if not (75 <= p['length'] <= 220 and 55 <= p['width'] <= 150 and
            10 <= p['height'] <= 40 and 1.8 <= p['wall'] <= 4 and
            1.8 <= p['floor'] <= 4 and 2.4 <= p['plate'] <= 5):
        raise ValueError("Dish dimensions or wall/floor/plate outside supported ranges.")
    if not (.4 <= p['side_clearance'] <= 2 and 4 <= p['foot_height'] <= 20 and
            6 <= p['foot_diameter'] <= 12 and 3 <= p['slot_width'] <= 8 and
            2.4 <= p['web'] <= 5 and 10 <= p['drain_margin'] <= 20):
        raise ValueError("Clearance, feet, drainage slots, or webs outside supported ranges.")
    r = p['outer_radius'] - p['wall'] - p['side_clearance']
    if not (1 <= r and p['outer_radius'] < min(p['length'], p['width'])/3):
        raise ValueError("Outer radius must leave at least a 1 mm insert corner radius.")
    if p['height'] < p['floor'] + p['foot_height'] + p['plate'] + .4:
        raise ValueError("Tray rim must sit at least 0.4 mm above the assembled insert.")
    if p['drain_margin'] < p['foot_diameter'] + 4:
        raise ValueError("Drain margin must protect the four foot attachment areas.")
    inset = 2*(p['wall'] + p['side_clearance'])
    if min(p['length']-inset, p['width']-inset) <= 2*p['drain_margin'] + 10:
        raise ValueError("Dish is too small for the selected drainage margins.")
    return p


def insert_dimensions(p):
    return (p['length']-2*(p['wall']+p['side_clearance']),
            p['width']-2*(p['wall']+p['side_clearance']))


def foot_centers(p):
    length, width = insert_dimensions(p)
    inset = p['foot_diameter']/2 + 3
    return [(sx*(length/2-inset), sy*(width/2-inset)) for sx in (-1, 1) for sy in (-1, 1)]


def build_tray(**overrides):
    p = settings(overrides)
    body = extrude(RectangleRounded(p['length'], p['width'], p['outer_radius']), amount=p['height'])
    cavity = extrude(RectangleRounded(p['length']-2*p['wall'], p['width']-2*p['wall'],
                                     p['outer_radius']-p['wall']), amount=p['height'])
    body = body - Pos(0, 0, p['floor'])*cavity
    # A lowered front lip forms a small pouring outlet when the tray is tipped.
    spout = Pos(0, p['width']/2, p['height']-4)*Box(12, 2*p['wall']+2, 5,
                                    align=(Align.CENTER, Align.CENTER, Align.MIN))
    body = body - spout
    body.label = "soap_catch_tray:closed_floor_front_pouring_notch"
    body.color = Color(.028, .23, .22)
    return body


def build_insert(**overrides):
    p = settings(overrides)
    length, width = insert_dimensions(p)
    radius = p['outer_radius']-p['wall']-p['side_clearance']
    body = extrude(RectangleRounded(length, width, radius), amount=p['plate'])
    feet = [Pos(x, y, p['plate']-.2)*Cylinder(p['foot_diameter']/2, p['foot_height']+.2,
                     align=(Align.CENTER, Align.CENTER, Align.MIN)) for x, y in foot_centers(p)]
    body = body + feet
    pitch = p['slot_width']+p['web']
    count = integer_floor((length - 2*p['drain_margin'] + p['web'])/pitch)
    slot = extrude(SlotOverall(width-2*p['drain_margin'], p['slot_width'], rotation=90),
                   amount=p['plate']+2)
    cuts = [Pos((i-(count-1)/2)*pitch, 0, -1)*slot for i in range(count)]
    body = body - cuts
    finger_notch = Pos(0, width/2, -1)*Cylinder(7, p['plate']+2,
                            align=(Align.CENTER, Align.CENTER, Align.MIN))
    body = body - finger_notch
    body.label = "soap_draining_insert:slotted_plate_four_feet_lift_notch"
    body.color = Color(.2, .48, .41)
    return body
