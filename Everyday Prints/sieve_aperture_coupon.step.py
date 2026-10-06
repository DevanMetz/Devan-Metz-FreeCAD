"""Aperture sample for the sorting sieve. One to five top ticks identify holes. mm."""
from build123d import Circle,Color,Pos,Rectangle,RectangleRounded,extrude

PARAMETERS = dict(hole_diameter=4.0,floor=2.4,offsets=(-.2,0,.2))


def dimensions(hole_diameter,offsets):
    maximum = hole_diameter+max(offsets)
    pitch = max(12,maximum+4)
    margin = pitch/2+2
    return ((len(offsets)-1)*pitch+2*margin,max(18,maximum+9),pitch)


def build(*,hole_diameter=4.0,floor=2.4,offsets=(-.2,0,.2)):
    if not (2 <= hole_diameter <= 10 and 1.6 <= floor <= 4 and 2 <= len(offsets) <= 5
            and all(-.4 <= offset <= .4 for offset in offsets)
            and all(a < b for a,b in zip(offsets,offsets[1:]))):
        raise ValueError("Use an increasing list of 2 to 5 offsets, with supported aperture and floor dimensions.")
    length,depth,pitch = dimensions(hole_diameter,offsets)
    body = extrude(RectangleRounded(length,depth,3),amount=floor)
    for index,offset in enumerate(offsets):
        x = (index-(len(offsets)-1)/2)*pitch
        body -= Pos(x,0,-1)*extrude(Circle((hole_diameter+offset)/2),amount=floor+2)
        for tick in range(index+1):
            body -= Pos(x+(tick-index/2)*1.6,depth/2-2,floor-.4)*extrude(Rectangle(.7,1.6),amount=.6)
    body.label = "sieve_aperture_coupon:increasing_round_openings_top_tick_labels"
    body.color = Color(.79,.37,.09)
    return body


def gen_step():
    return build(**PARAMETERS)
