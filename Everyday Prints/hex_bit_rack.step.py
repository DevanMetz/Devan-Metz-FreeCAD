"""Open-top blind hex sockets for driver bits. mm; measure your own shanks."""
from math import sqrt
from build123d import Color, Pos, RectangleRounded, RegularPolygon, extrude, loft

PARAMETERS = dict(columns=6, rows=3, pitch=12.0, margin=10.0, height=14.0,
                  floor=2.4, shank_af=6.35, clearance=.35, lead_in=.6)


def build(*, columns=6, rows=3, pitch=12.0, margin=10.0, height=14.0,
          floor=2.4, shank_af=6.35, clearance=.35, lead_in=.6):
    if not (isinstance(columns, int) and isinstance(rows, int)
            and 1 <= columns <= 12 and 1 <= rows <= 6):
        raise ValueError("Use 1–12 integer columns and 1–6 integer rows.")
    if not (8 <= pitch <= 25 and 6 <= margin <= 20 and 8 <= height <= 35 and
            1.6 <= floor <= 5 and 3 <= shank_af <= 12 and
            .1 <= clearance <= 1 and .3 <= lead_in <= 1):
        raise ValueError("Rack dimensions, shank, clearance, or entry bevel outside range.")
    hole_af = shank_af+clearance
    radius = hole_af/sqrt(3)
    mouth_radius = (hole_af+2*lead_in)/sqrt(3)
    if (pitch < 2*mouth_radius+2 or margin < mouth_radius+2
            or height-floor <= 2*lead_in+2):
        raise ValueError("Keep 2 mm webs/margins at the entrances and a useful socket depth.")
    length = (columns-1)*pitch+2*margin
    width = (rows-1)*pitch+2*margin
    body = extrude(RectangleRounded(length, width, 3), amount=height)
    socket = RegularPolygon(radius, 6)
    straight = Pos(0, 0, floor)*extrude(socket, amount=height-floor+1)
    # Wide end overshoots the top so the nominal 0.6 entry is present at Z=height.
    wide = RegularPolygon((hole_af+2*(lead_in+.1))/sqrt(3), 6)
    lead = loft([Pos(0, 0, height-lead_in)*socket, Pos(0, 0, height+.1)*wide])
    centers = [((c-(columns-1)/2)*pitch, (r-(rows-1)/2)*pitch)
               for c in range(columns) for r in range(rows)]
    body = body-[Pos(x,y,0)*straight for x,y in centers]
    body = body-[Pos(x,y,0)*lead for x,y in centers]
    body.label = f"hex_bit_rack:{columns}x{rows}_blind_hex_sockets"
    body.color = Color(.07, .21, .11)
    return body


def gen_step():
    return build(**PARAMETERS)
