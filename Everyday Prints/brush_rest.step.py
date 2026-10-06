"""Three brush cradles over a catch tray with wash-through rail openings. mm."""
from build123d import Align, Box, Circle, Color, Plane, Polygon, Pos, RectangleRounded, extrude

PARAMETERS = dict(width=100.0,length=150.0,wall=2.4,floor=2.4,rim_height=12.0,
                  groove_diameters=(8.0,12.0,16.0),clearance=.6,groove_pitch=30.0,
                  rail_height=20.0,rail_thickness=4.0,rail_spacing=40.0,rear_inset=30.0)


def build(*, width=100.0,length=150.0,wall=2.4,floor=2.4,rim_height=12.0,
          groove_diameters=(8.0,12.0,16.0),clearance=.6,groove_pitch=30.0,
          rail_height=20.0,rail_thickness=4.0,rail_spacing=40.0,rear_inset=30.0):
    if not (70 <= width <= 160 and 110 <= length <= 180 and 2 <= wall <= 3.5
            and 2 <= floor <= 4 and 10 <= rim_height <= 18 and 2 <= len(groove_diameters) <= 4
            and all(5 <= d <= 24 for d in groove_diameters) and .3 <= clearance <= 1
            and 20 <= groove_pitch <= 36 and 16 <= rail_height <= 32
            and 3 <= rail_thickness <= 6 and 25 <= rail_spacing <= 60 and 20 <= rear_inset <= 40):
        raise ValueError("Tray or cradle parameters outside supported ranges.")
    max_radius = (max(groove_diameters)+clearance)/2
    if ((len(groove_diameters)-1)*groove_pitch/2+max_radius+wall+3 > width/2
            or groove_pitch < 2*max_radius+3 or rail_height-max_radius < floor+6+2.4
            or rail_height < rim_height+2 or rim_height < floor+6
            or length-rear_inset-rail_spacing < 35):
        raise ValueError("Preserve cradle webs, portal roofs, rim height, and space for brush ends.")
    body = extrude(RectangleRounded(width,length,6),amount=rim_height)
    body -= Pos(0,0,floor)*extrude(RectangleRounded(width-2*wall,length-2*wall,6-wall),amount=rim_height)
    for y in (-length/2+rear_inset,-length/2+rear_inset+rail_spacing):
        rail = Pos(0,y,floor-.1)*Box(width-2*wall,rail_thickness,rail_height-floor+.1,
                                    align=(Align.CENTER,Align.CENTER,Align.MIN))
        body += rail
        for index,diameter in enumerate(groove_diameters):
            x = (index-(len(groove_diameters)-1)/2)*groove_pitch
            groove = extrude(Plane.XZ*Circle((diameter+clearance)/2),amount=rail_thickness+2)
            body -= Pos(x,y+rail_thickness/2+1,rail_height)*groove
            portal = Plane.XZ*Polygon((-4,floor),(4,floor),(4,floor+2),
                                      (0,floor+6),(-4,floor+2),align=None)
            body -= Pos(x,y+rail_thickness/2+1,0)*extrude(portal,amount=rail_thickness+2)
    body -= Pos(0,length/2,rim_height-3)*Box(12,2*wall+2,4,
                                           align=(Align.CENTER,Align.CENTER,Align.MIN))
    body.label = "brush_rest:paired_cradles_peaked_wash_portals_catch_floor"
    body.color = Color(.09,.35,.49)
    return body


def gen_step():
    return build(**PARAMETERS)
