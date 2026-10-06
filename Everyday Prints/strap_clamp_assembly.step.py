"""Four printed pads around a reference frame and strap; assembly is view-only."""
from build123d import Color,Location,Pos,Rectangle,RectangleRounded,extrude
from cadgen.assembly import AssemblyHelper
from strap_corner_common import PARAMETERS as SHARED,settings,build as build_pad

PARAMETERS = SHARED | dict(frame_width=180.0,frame_depth=130.0,frame_height=30.0,rail_width=20.0)


def build(*,frame_width=180.0,frame_depth=130.0,frame_height=30.0,rail_width=20.0,**overrides):
    p = settings(overrides)
    minimum_span = 2*p['leg_length']+12
    strap_z = p['lip_thickness']+p['width_clearance']/2
    if not (minimum_span <= frame_width <= 400 and minimum_span <= frame_depth <= 300
            and strap_z+p['strap_width'] <= frame_height <= 80
            and 10 <= rail_width <= min(50,frame_width/2-10,frame_depth/2-10)):
        raise ValueError("Keep the reference pads separated, the frame opening clear, and the strap within the frame height.")
    assembly = AssemblyHelper("strap_clamp:four_printed_pads_reference_frame_and_webbing")
    root = assembly.add(build_pad(**p),"pad_south_west")
    for name,x,y,angle in (("south_east",frame_width,0,90),
                            ("north_east",frame_width,frame_depth,180),
                            ("north_west",0,frame_depth,270)):
        pad = assembly.add(build_pad(**p),"pad_"+name)
        fixed = assembly.rigid_frame(root,"corner_"+name,Location((x,y,0),(0,0,angle)))
        moving = assembly.rigid_frame(pad,"workpiece_corner",Location())
        assembly.face_to_face(fixed,moving,label="pad_at_"+name)
    frame_profile = Rectangle(frame_width,frame_depth)-Rectangle(frame_width-2*rail_width,frame_depth-2*rail_width)
    frame = assembly.add(extrude(frame_profile,amount=frame_height),
                         "REFERENCE_frame_not_for_printing",color=Color(.63,.67,.69))
    fixed = assembly.rigid_frame(root,"frame_center",Location((frame_width/2,frame_depth/2,0)))
    moving = assembly.rigid_frame(frame,"frame_center_bottom",Location())
    assembly.face_to_face(fixed,moving,label="frame_inside_four_pads")
    inner = p['wall']
    outer = inner+p['strap_thickness']
    band = (RectangleRounded(frame_width+2*outer,frame_depth+2*outer,outer)
            -RectangleRounded(frame_width+2*inner,frame_depth+2*inner,inner))
    strap = assembly.add(extrude(band,amount=p['strap_width']),
                         "REFERENCE_strap_path_not_for_printing",color=Color(.84,.40,.10))
    fixed = assembly.rigid_frame(root,"strap_center",Location((frame_width/2,frame_depth/2,strap_z)))
    moving = assembly.rigid_frame(strap,"strap_center_lower_edge",Location())
    assembly.face_to_face(fixed,moving,label="strap_on_rounded_corner_paths")
    return assembly.build()


def gen_step():
    return build(**PARAMETERS)
