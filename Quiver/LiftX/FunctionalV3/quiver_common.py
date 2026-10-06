"""Functional quiver prototype. Millimetres; +Z tips; RH construction, LH delivery.

No generated STEP is imported here. All delivered parts derive from these functions.
"""
from functools import lru_cache
from math import sqrt, sin, cos, radians
from build123d import Solid, Wire, Face, Plane, Kind, Axis, Location, Compound, RigidJoint, Color

PITCH = 44.0
ROW = PITCH * sqrt(3) / 2
AXES = ((-44., 0.), (0., 0.), (44., 0.), (-22., ROW), (22., ROW))
AXIS_OD = {600: 6.4262, 500: 6.5532, 400: 6.7056, 340: 6.7818, 300: 6.9850, 260: 7.1120, 200: 7.2644}
SELECTED_SPINE = 340
HEAD_D = 35.0
HEAD_L = 70.0
HEAD_BASE = 282.0
TIP_Z = HEAD_BASE + HEAD_L
DY = -22.8
MOUNT_Z = 92.0


def box(x, y, z, w, d, h):
    return Solid.make_box(w, d, h, Plane(origin=(x, y, z)))


def cyl(r, h, x, y, z, axis=(0, 0, 1)):
    return Solid.make_cylinder(r, h, Plane(origin=(x, y, z), z_dir=axis))


def poly(points):
    return Wire.make_polygon(points, close=True)


def prism(points, vec):
    return Solid.extrude(Face(poly(points)), vec)


def rect(x0, x1, y0, y1, z):
    return poly([(x0,y0,z), (x1,y0,z), (x1,y1,z), (x0,y1,z)])


def joined(shapes):
    shapes = list(shapes)
    return shapes[0].fuse(*shapes[1:]).clean() if len(shapes) > 1 else shapes[0]


def require_one(shape, name):
    shape = shape.clean()
    if not shape.is_valid or len(shape.solids()) != 1 or shape.volume <= 0:
        raise ValueError(f"{name}: valid={shape.is_valid}, solids={len(shape.solids())}, volume={shape.volume}")
    return shape


def capsule(a, b, width, z, h):
    dx, dy = b[0]-a[0], b[1]-a[1]
    length = sqrt(dx*dx + dy*dy)
    nx, ny = -dy/length*width/2, dx/length*width/2
    bar = prism([(a[0]+nx,a[1]+ny,z), (b[0]+nx,b[1]+ny,z),
                 (b[0]-nx,b[1]-ny,z), (a[0]-nx,a[1]-ny,z)], (0,0,h))
    return joined([bar, cyl(width/2,h,*a,z), cyl(width/2,h,*b,z)])


def skeleton(radius, link_width, z, height):
    # All backing links are behind the local release mouth.
    links = (((-44,-5),(44,-5)), ((-22,ROW-5),(22,ROW-5)),
             ((-22,-5),(-22,ROW-5)), ((22,-5),(22,ROW-5)))
    return joined([cyl(radius,height,x,y,z) for x,y in AXES] +
                  [capsule(a,b,link_width,z,height) for a,b in links])


def release_cuts(width, z, h, near_only=False):
    return [box(x-width/2,y,z,width,8.2 if near_only else ROW+35-y,h) for x,y in AXES]


def shaft_clearances(width, z, h):
    return [cyl(width/2,h,x,y,z) for x,y in AXES] + release_cuts(width,z,h)


def hood_wire(radius, z):
    base = poly([(-44,0,z),(44,0,z),(22,ROW,z),(-22,ROW,z)])
    return base.offset_2d(radius, kind=Kind.ARC)


def joint_holes():
    return [cyl(2.25,30,0,-45,z,(0,1,0)) for z in (205.,220.)]


@lru_cache(None)
def upper_frame():
    outside = Solid.make_loft([hood_wire(28,278),hood_wire(23,357),hood_wire(22,360)], ruled=True)
    cavity = Solid.make_loft([hood_wire(25,277),hood_wire(20,356)], ruled=True)
    hood = outside.cut(cavity)
    # The spine continues up the back wall to the cap: a direct union, not a
    # cantilever beginning in mid-air when this component is printed cap-down.
    neck = Solid.make_loft([rect(-16,16,-36,-22,194),rect(-16,16,-36,-22,252),
                           rect(-22,22,-36,-22,278),rect(-22,22,-36,-22,346),
                           rect(-22,22,-22,-20,360)], ruled=True)
    part = joined([hood,neck])
    socket = box(-10.3,-33.3,193,20.6,8.6,38)
    # Nut pockets are captive in XY, accessible from the bow-facing rear.
    nut_pockets=[]
    for z in (205.,220.):
        pts=[(4.22*cos(radians(30+i*60)),-36.1,z+4.22*sin(radians(30+i*60))) for i in range(6)]
        nut_pockets.append(prism(pts,(0,3.6,0)))
    part=part.cut(socket,*joint_holes(),*nut_pockets)
    return require_one(part,"upper hood and neck")


def male_rail():
    bottom=rect(-10,10,-14,-12.8,0)
    full=poly([(-13,-23.7,10),(13,-23.7,10),(10,-13.8,10),(-10,-13.8,10)])
    wedge=Solid.make_loft([bottom,full],ruled=True)
    rail=prism([(-13,-23.7,10),(13,-23.7,10),(10,-13.8,10),(-10,-13.8,10)],(0,0,62))
    part=joined([wedge,rail,box(-10,-13.8,0,20,1,72)])
    part=part.cut(box(-6,-16,63,12,4,7))
    return part.moved(Location((0,DY,MOUNT_Z)))


@lru_cache(None)
def lower_frame():
    carrier=skeleton(10,10,0,12)
    pocket=skeleton(8.3,6.6,3,10)
    # Open the whole front of each rigid saddle, leaving the TPU jaws room to
    # flex. A narrow hard cup would make the nominal soft clip effectively rigid.
    carrier=carrier.cut(pocket,*[cyl(4.75,15,x,y,-1) for x,y in AXES],*release_cuts(21,-1,15))
    anchors=[]
    for x in (-22.,22.):
        anchors.extend([cyl(2,4,x,-5,-.5),cyl(2.7,1.1,x,-5,-.1)])
    carrier=carrier.cut(*anchors)
    beam=box(-16,-36,9,32,14,185)
    # 45 degree ends avoid unsupported flat roofs in the upright build.
    windows=[]
    for z0,z1 in ((30,78),(176,191)):
        if z1-z0>20:
            windows.append(prism([(-7,-37,z0+7),(0,-37,z0),(7,-37,z0+7),
                                  (7,-37,z1-7),(0,-37,z1),(-7,-37,z1-7)],(0,16,0)))
    # The latch occupies this channel; rail edges remain tied to both beam chords.
    windows.append(box(-8.2,-37,MOUNT_Z-4,16.4,16,82))
    beam=beam.cut(*windows)
    root=box(-14,-36,0,28,27.7,12)
    plug=Solid.make_loft([rect(-10,10,-33,-25,193),rect(-10,10,-33,-25,226),
                          rect(-9.2,9.2,-32.2,-25.8,228)],ruled=True)
    part=joined([carrier,root,beam,plug,male_rail()]).cut(*joint_holes())
    # A continuous shallow rear relief lets the FIXED latch root pass every
    # crossbar during the full release stroke, including the carrier root.
    # Only the flexible tongue is excluded from rigid-motion validation.
    part=part.cut(box(-8.2,-37,-.1,16.4,5.5,194.1))
    return require_one(part,"lower spine and carrier")


def chamfer_plate_xz(width,height,depth,y,z,c=3,cx=0):
    a,b=cx-width/2,cx+width/2
    return prism([(a+c,y,z),(b-c,y,z),(b,y,z+c),(b,y,z+height-c),
                  (b-c,y,z+height),(a+c,y,z+height),(a,y,z+height-c),(a,y,z+c)],(0,depth,0))


@lru_cache(None)
def dock():
    back=chamfer_plate_xz(38,76,6.3,-30,0,4)
    track=box(-19,-24,0,38,10.5,76)
    cavity=prism([(-13.4,-24.2,-.5),(13.4,-24.2,-.5),(10.4,-13.35,-.5),(-10.4,-13.35,-.5)],(0,0,77))
    track=track.cut(cavity)
    stops=[box(-19,-24,-4,38,10.5,4),box(-7,-15.5,-4,14,6.5,4)]
    tongue=box(-5,-12.4,-4,10,3,73)
    release=chamfer_plate_xz(16,8,7,-12.4,68,2)
    tooth=prism([(-5,-12.4,63.5),(-5,-15.2,63.5),(-5,-15.2,64.5),(-5,-12.4,69)],(10,0,0))
    flange=chamfer_plate_xz(32,60,6,-30,8,4,-22)
    part=joined([back,track,*stops,tongue,release,tooth,flange])
    holes=[cyl(2.65,9,-29,-31,54.6625,(0,1,0)),
           cyl(2.65,9,-29,-31,19.8375,(0,1,0)),cyl(2.65,9,-29,-31,22.8375,(0,1,0)),
           box(-31.65,-31,19.8375,5.3,9,3)]
    part=part.cut(*holes)
    return require_one(part.moved(Location((0,DY,MOUNT_Z))),"provisional dock")


@lru_cache(None)
def gripper(spine=SELECTED_SPINE):
    od=AXIS_OD[spine]
    part=skeleton(8,6,3.3,9)
    holes=[cyl((od-.25)/2,11,x,y,2.8) for x,y in AXES]
    near=release_cuts(od*.65,2.8,11,near_only=True)
    # A rear-row arrow must also clear the backing bridge ahead of it.
    far=[box(x-4.75,y+8,2.8,9.5,ROW+25-y,11) for x,y in AXES]
    part=part.cut(*holes,*near,*far)
    pegs=[]
    for x in (-22.,22.):
        pegs.extend([cyl(1.7,3.2,x,-5,.3),
                     Solid.make_cone(1.7,2.4,.7,Plane(origin=(x,-5,-.4))),
                     Solid.make_cone(2.4,1.7,.7,Plane(origin=(x,-5,.3)))])
    return require_one(joined([part,*pegs]),f"AXIS {spine} TPU gripper")


@lru_cache(None)
def foam():
    # Template only; not a rigid printed blade barrier. Bond inside the cap.
    return Solid.extrude(Face(hood_wire(19.5,344)),(0,0,12))


def sizing_coupon():
    # Separate one-bore samples joined by a numbered backing rail.
    samples=[]
    for i,(spine,od) in enumerate(AXIS_OD.items()):
        x=i*17.
        sample=joined([cyl(7,9,x,0,0),box(x-8.5,-10,0,17,6,9)])
        sample=sample.cut(cyl((od-.25)/2,11,x,0,-1),box(x-od*.65/2,0,-1,od*.65,9,11))
        # 1..7 recessed dots are printable labels; map supplied in README.
        dots=[cyl(.55,.8,x-3+j,-7.5,8.3) for j in range(i+1)]
        samples.append(sample.cut(*dots))
    return require_one(joined(samples),"AXIS sizing coupon")


def lh(shape):
    return shape.mirror(Plane.XZ)


def to_bed(shape, rotation=None):
    if rotation:
        shape=shape.rotate(rotation[0],rotation[1])
    bb=shape.bounding_box()
    return shape.moved(Location((-bb.min.X,-bb.min.Y,-bb.min.Z)))


def print_part(name, spine=SELECTED_SPINE):
    shape={"upper":upper_frame,"lower":lower_frame,"dock":dock,
           "gripper":lambda:gripper(spine),"coupon":sizing_coupon}[name]()
    shape=lh(shape)
    if name in ("upper","gripper"):
        shape=to_bed(shape,(Axis.X,180))
    elif name=="dock":
        shape=to_bed(shape,(Axis.X,-90))
    else:
        shape=to_bed(shape)
    shape.label=f"LH_{name}"+(f"_AXIS_{spine}" if name=="gripper" else "")
    RigidJoint("print_bed",shape,Location((0,0,0)))
    return shape


def tint(shape, label, color):
    import cadgen
    shape.label=label
    shape.color=cadgen.srgb(color)
    return shape


def reference_arrow(x,y,od=7.2644,short=False):
    shaft=cyl(od/2,290 if short else 682,x,y,-8 if short else -400)
    head=cyl(HEAD_D/2,HEAD_L,x,y,HEAD_BASE)
    return joined([shaft,head])


def assembly(loaded=False):
    parts=[tint(lh(lower_frame()),"01_LH_lower_frame","#819379"),
           tint(lh(upper_frame()),"02_LH_hood_upper_frame","#819379"),
           tint(lh(dock()),"03_PROVISIONAL_dock_UNVERIFIED_BOW_FIT","#6E7C87"),
           tint(lh(gripper(SELECTED_SPINE)),f"04_TPU_AXIS_{SELECTED_SPINE}_USER_CONFIRMED","#C2743D"),
           tint(lh(foam()),"05_CUT_FOAM_TEMPLATE_NOT_PRINTED","#343437")]
    for part in parts:
        RigidJoint("quiver_origin",part,Location((0,0,0)))
    for i,z in enumerate((205.,220.)):
        bolt=joined([cyl(1.95,16,0,-38,z,(0,1,0)),cyl(3.5,3,0,-22,z,(0,1,0))])
        pts=[(4.04*cos(radians(30+j*60)),-35.7,z+4.04*sin(radians(30+j*60))) for j in range(6)]
        nut=prism(pts,(0,3.2,0)).cut(cyl(2,4,0,-36,z,(0,1,0)))
        parts.extend([tint(lh(bolt),f"HARDWARE_M4x16_{i+1}_REFERENCE","#C6C9CC"),
                      tint(lh(nut),f"HARDWARE_M4_nut_{i+1}_REFERENCE","#C6C9CC")])
    if loaded:
        for i,(x,y) in enumerate(AXES):
            parts.append(tint(lh(reference_arrow(x,y,od=AXIS_OD[SELECTED_SPINE],short=True)),
                              f"REF_{i+1}_35x70_head_AXIS_{SELECTED_SPINE}_shaft","#829EA9"))
    return Compound(label="LH_LIFT_X_FUNCTIONAL_V3_PROTOTYPE",children=parts)
