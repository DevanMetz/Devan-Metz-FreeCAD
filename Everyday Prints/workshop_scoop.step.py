"""Scoop for dry workshop supplies. Print the bowl floor and low handle down. mm."""
from build123d import Circle, Color, Plane, Pos, RectangleRounded, extrude

PARAMETERS = dict(bowl_length=60.0,bowl_width=45.0,height=20.0,wall=2.4,floor=2.4,
                  corner_radius=6.0,handle_length=50.0,handle_width=18.0,handle_thickness=4.0,
                  pour_width=18.0,pour_drop=4.0,hanging_hole=4.5)


def build(*,bowl_length=60.0,bowl_width=45.0,height=20.0,wall=2.4,floor=2.4,
          corner_radius=6.0,handle_length=50.0,handle_width=18.0,handle_thickness=4.0,
          pour_width=18.0,pour_drop=4.0,hanging_hole=4.5):
    if not (40 <= bowl_length <= 90 and 30 <= bowl_width <= 70 and 12 <= height <= 35
            and 1.8 <= wall <= 3.2 and 1.8 <= floor <= 4 and 4 <= corner_radius <= 10
            and 30 <= handle_length <= 75 and 14 <= handle_width <= 26
            and 3 <= handle_thickness <= 6 and 10 <= pour_width <= 30
            and 2 <= pour_drop <= 8 and 3 <= hanging_hole <= 6):
        raise ValueError("Scoop dimensions outside supported ranges.")
    lip = height-pour_drop
    if (corner_radius < wall+1 or corner_radius >= min(bowl_length,bowl_width)/3
            or lip-floor < 6 or handle_thickness < floor or handle_width < hanging_hole+6
            or handle_width > bowl_width-2*corner_radius-2
            or pour_width > bowl_width-2*corner_radius-4):
        raise ValueError("Preserve bowl walls, usable capacity, handle connection, and pour-notch margins.")
    body = extrude(RectangleRounded(bowl_length,bowl_width,corner_radius),amount=height)
    pocket = RectangleRounded(bowl_length-2*wall,bowl_width-2*wall,corner_radius-wall)
    body -= Pos(0,0,floor)*extrude(pocket,amount=height-floor+1)
    handle_min = -bowl_length/2-handle_length
    handle_max = -bowl_length/2+wall/2
    handle = RectangleRounded(handle_max-handle_min,handle_width,4)
    body += Pos((handle_max+handle_min)/2,0,0)*extrude(handle,amount=handle_thickness)
    notch_height = pour_drop+4
    notch = Pos(0,0,lip+notch_height/2)*(Plane.YZ*RectangleRounded(pour_width,notch_height,2))
    body -= Pos(bowl_length/2-wall-1,0,0)*extrude(notch,amount=wall+2,dir=(1,0,0))
    body -= Pos(handle_min+handle_width/2,0,-1)*extrude(Circle(hanging_hole/2),amount=handle_thickness+2)
    body.label = "workshop_scoop:rounded_bowl_lowered_pour_lip_low_handle_hanging_hole"
    body.color = Color(.46,.22,.07)
    return body


def gen_step():
    return build(**PARAMETERS)
