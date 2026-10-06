"""Round sieve for dry craft/workshop pieces. Print floor and handle down. mm."""
from math import ceil,hypot,sqrt
from build123d import Circle,Color,Pos,Rectangle,extrude

PARAMETERS = dict(bowl_diameter=90.0,height=18.0,wall=2.4,floor=2.4,hole_diameter=4.0,
                  pitch=7.0,hole_margin=4.0,handle_length=45.0,handle_width=18.0,
                  handle_thickness=4.0,hanging_hole=4.5)


def hole_centers(*,bowl_diameter,wall,hole_diameter,pitch,hole_margin,**unused):
    limit = bowl_diameter/2-wall-hole_margin-hole_diameter/2
    count = ceil(bowl_diameter/pitch)
    points = [(pitch*(q+r/2),pitch*sqrt(3)/2*r)
              for r in range(-count,count+1) for q in range(-count,count+1)
              if hypot(pitch*(q+r/2),pitch*sqrt(3)/2*r) <= limit+1e-9]
    return sorted(points,key=lambda xy:(xy[1],xy[0]))


def build(*,bowl_diameter=90.0,height=18.0,wall=2.4,floor=2.4,hole_diameter=4.0,
          pitch=7.0,hole_margin=4.0,handle_length=45.0,handle_width=18.0,
          handle_thickness=4.0,hanging_hole=4.5):
    if not (55 <= bowl_diameter <= 130 and 12 <= height <= 28 and 2 <= wall <= 3.5
            and 1.6 <= floor <= 4 and 1.6 <= hole_diameter <= 12 and 4 <= pitch <= 18
            and 3 <= hole_margin <= 8 and 30 <= handle_length <= 70
            and 14 <= handle_width <= 26 and 3 <= handle_thickness <= 6
            and 3 <= hanging_hole <= 6):
        raise ValueError("Sieve dimensions outside supported ranges.")
    if (pitch-hole_diameter < 2 or hole_margin < wall+1 or height-floor < 8
            or handle_thickness < floor or handle_width < hanging_hole+8
            or handle_width > bowl_diameter/3):
        raise ValueError("Preserve hole webs, solid edge margin, bowl depth, and handle connection.")
    centers = hole_centers(bowl_diameter=bowl_diameter,wall=wall,hole_diameter=hole_diameter,
                           pitch=pitch,hole_margin=hole_margin)
    if not 7 <= len(centers) <= 250:
        raise ValueError("Choose a hole pitch giving 7 to 250 openings for this bowl.")
    radius = bowl_diameter/2
    body = extrude(Circle(radius),amount=height)
    body -= Pos(0,0,floor)*extrude(Circle(radius-wall),amount=height-floor+1)
    low,high = -radius-handle_length,-radius+2*wall
    cap = low+handle_width/2
    handle = Pos((cap+high)/2,0)*Rectangle(high-cap,handle_width)
    handle += Pos(cap,0)*Circle(handle_width/2)
    body += extrude(handle,amount=handle_thickness)
    openings = [Pos(x,y,-1)*extrude(Circle(hole_diameter/2),amount=floor+2) for x,y in centers]
    body = body-openings
    body -= Pos(low+handle_width/2,0,-1)*extrude(Circle(hanging_hole/2),amount=handle_thickness+2)
    body.label = f"sorting_sieve:{len(centers)}_round_apertures_triangular_pattern_low_handle"
    body.color = Color(.12,.35,.39)
    return body


def gen_step():
    return build(**PARAMETERS)
