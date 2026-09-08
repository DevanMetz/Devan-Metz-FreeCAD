"""Build a compact two-part FDM quiver for a Mathews LIFT X.

The chassis integrates the hood, truss spine, five shaft clips, and male
quick-connect.  The second printed part is the bow dock with an integral
release latch.  Dimensions are millimetres; run with FreeCADCmd.
"""

from pathlib import Path

import FreeCAD as App
import Import
import MeshPart
import Part


# Product inputs and two process calibration knobs.
HAND = "LH"
SHAFT_DIAMETER = 6.5
BROADHEAD_WIDTH = 32.0
AMO_HOLE_SPACING = 33.325
AMO_SCREW_CLEARANCE = 5.30
DOCK_CLEARANCE = 0.40
CLIP_INTERFERENCE = 0.20

LINEAR_DEFLECTION = 0.08
ANGULAR_DEFLECTION = 0.12

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "MountV2"
STL_DIR = OUTPUT_DIR / "STL"
STEP_DIR = OUTPUT_DIR / "STEP"
MOUNT_HOLE_X = -29.0
MOUNT_SLOT_TRAVEL = 3.0
MOUNT_FLANGE_THICKNESS = 6.0

ARROW_X = (-40.0, -20.0, 0.0, 20.0, 40.0)
ARROW_Y = (16.0, 20.0, 16.0, 20.0, 16.0)
HOOD_Z = 188.0
HOOD_HEIGHT = 60.0
HOOD_FLOOR_THICKNESS = 4.0
BASKET_RIM_HEIGHT = 8.0
BASKET_RIB_HEIGHT = 38.0
MOUNT_Z = 68.0
DOCK_HEIGHT = 76.0
MALE_WIDE = 26.0
MALE_NARROW = 20.0
FEMALE_WIDE = MALE_WIDE + DOCK_CLEARANCE * 2
FEMALE_NARROW = MALE_NARROW + DOCK_CLEARANCE * 2

# Upright-printable planar spine: two thick chords and self-supporting diamonds.
SPINE_X = 16.0
SPINE_Y = -8.0
SPINE_TOP_Y = -21.0
SPINE_TRANSITION_Z = MOUNT_Z + DOCK_HEIGHT + 1
SPINE_DEPTH = 12.0
SPINE_CHORD = 6.0
SPINE_BRACE = 4.0
SPINE_BAYS = ((12, 66), (146, 186))
MOUNT_Y = -13.2
CLIP_OUTER_TAPER = 0.35
CLIP_HEIGHT = 11.0
CLIP_BAR_HEIGHT = 8.0
DOCK_CORNER = 4.0


def wire_xy(width, depth, z, corner, center_y=0.0):
    x0, x1 = -width / 2, width / 2
    y0, y1 = center_y - depth / 2, center_y + depth / 2
    return Part.makePolygon(
        [
            App.Vector(x0 + corner, y0, z),
            App.Vector(x1 - corner, y0, z),
            App.Vector(x1, y0 + corner, z),
            App.Vector(x1, y1 - corner, z),
            App.Vector(x1 - corner, y1, z),
            App.Vector(x0 + corner, y1, z),
            App.Vector(x0, y1 - corner, z),
            App.Vector(x0, y0 + corner, z),
            App.Vector(x0 + corner, y0, z),
        ]
    )


def chamfered_prism_xy(width, depth, height, corner, center_y=0.0, z=0.0):
    return Part.Face(wire_xy(width, depth, z, corner, center_y)).extrude(
        App.Vector(0, 0, height)
    )


def rectangular_wire_xy(x0, x1, y0, y1, z):
    return Part.makePolygon(
        [
            App.Vector(x0, y0, z),
            App.Vector(x1, y0, z),
            App.Vector(x1, y1, z),
            App.Vector(x0, y1, z),
            App.Vector(x0, y0, z),
        ]
    )


def chamfered_prism_xz(width, height, depth, y, z=0.0, corner=3.0):
    x0, x1 = -width / 2, width / 2
    z0, z1 = z, z + height
    wire = Part.makePolygon(
        [
            App.Vector(x0 + corner, y, z0),
            App.Vector(x1 - corner, y, z0),
            App.Vector(x1, y, z0 + corner),
            App.Vector(x1, y, z1 - corner),
            App.Vector(x1 - corner, y, z1),
            App.Vector(x0 + corner, y, z1),
            App.Vector(x0, y, z1 - corner),
            App.Vector(x0, y, z0 + corner),
            App.Vector(x0 + corner, y, z0),
        ]
    )
    return Part.Face(wire).extrude(App.Vector(0, depth, 0))


def pointed_window_xz(width, height, depth, center_x, center_z, y):
    roof = width / 2
    wire = Part.makePolygon(
        [
            App.Vector(center_x, y, center_z - height / 2),
            App.Vector(center_x + width / 2, y, center_z - height / 2 + roof),
            App.Vector(center_x + width / 2, y, center_z + height / 2 - roof),
            App.Vector(center_x, y, center_z + height / 2),
            App.Vector(center_x - width / 2, y, center_z + height / 2 - roof),
            App.Vector(center_x - width / 2, y, center_z - height / 2 + roof),
            App.Vector(center_x, y, center_z - height / 2),
        ]
    )
    return Part.Face(wire).extrude(App.Vector(0, depth, 0))


def pointed_window_yz(width, height, depth, center_y, center_z, x):
    roof = width / 2
    wire = Part.makePolygon(
        [
            App.Vector(x, center_y, center_z - height / 2),
            App.Vector(x, center_y + width / 2, center_z - height / 2 + roof),
            App.Vector(x, center_y + width / 2, center_z + height / 2 - roof),
            App.Vector(x, center_y, center_z + height / 2),
            App.Vector(x, center_y - width / 2, center_z + height / 2 - roof),
            App.Vector(x, center_y - width / 2, center_z - height / 2 + roof),
            App.Vector(x, center_y, center_z - height / 2),
        ]
    )
    return Part.Face(wire).extrude(App.Vector(depth, 0, 0))


def beam_xy(x1, y1, x2, y2, width, height, z=0.0):
    dx, dy = x2 - x1, y2 - y1
    length = (dx * dx + dy * dy) ** 0.5
    px, py = -dy * width / (2 * length), dx * width / (2 * length)
    wire = Part.makePolygon(
        [
            App.Vector(x1 + px, y1 + py, z),
            App.Vector(x2 + px, y2 + py, z),
            App.Vector(x2 - px, y2 - py, z),
            App.Vector(x1 - px, y1 - py, z),
            App.Vector(x1 + px, y1 + py, z),
        ]
    )
    return Part.Face(wire).extrude(App.Vector(0, 0, height))


def beam_xz(x1, z1, x2, z2, width, y, depth):
    dx, dz = x2 - x1, z2 - z1
    length = (dx * dx + dz * dz) ** 0.5
    px, pz = -dz * width / (2 * length), dx * width / (2 * length)
    wire = Part.makePolygon(
        [
            App.Vector(x1 + px, y, z1 + pz),
            App.Vector(x2 + px, y, z2 + pz),
            App.Vector(x2 - px, y, z2 - pz),
            App.Vector(x1 - px, y, z1 - pz),
            App.Vector(x1 + px, y, z1 + pz),
        ]
    )
    return Part.Face(wire).extrude(App.Vector(0, depth, 0))


def spine_y_at_z(z):
    blend = max(0.0, min(1.0, (z - SPINE_TRANSITION_Z) / (HOOD_Z - SPINE_TRANSITION_Z)))
    return SPINE_Y + (SPINE_TOP_Y - SPINE_Y) * blend


def beam_xz_on_spine(x1, z1, x2, z2, width):
    dx, dz = x2 - x1, z2 - z1
    length = (dx * dx + dz * dz) ** 0.5
    px, pz = -dz * width / (2 * length), dx * width / (2 * length)
    points = (
        (x1 + px, z1 + pz),
        (x2 + px, z2 + pz),
        (x2 - px, z2 - pz),
        (x1 - px, z1 - pz),
    )

    def wire(offset):
        def rail_y(z):
            blend = (z - SPINE_TRANSITION_Z) / (HOOD_Z - SPINE_TRANSITION_Z)
            return SPINE_Y + (SPINE_TOP_Y - SPINE_Y) * blend

        vertices = [
            App.Vector(x, rail_y(z) + offset, z) for x, z in points
        ]
        vertices.append(vertices[0])
        return Part.makePolygon(vertices)

    return Part.makeLoft([wire(0), wire(SPINE_DEPTH)], True, False)


def sloped_spine_chord(x):
    lower = rectangular_wire_xy(
        x - SPINE_CHORD / 2,
        x + SPINE_CHORD / 2,
        SPINE_Y,
        SPINE_Y + SPINE_DEPTH,
        SPINE_TRANSITION_Z,
    )
    upper = rectangular_wire_xy(
        x - SPINE_CHORD / 2,
        x + SPINE_CHORD / 2,
        SPINE_TOP_Y,
        SPINE_TOP_Y + SPINE_DEPTH,
        HOOD_Z + 1,
    )
    return Part.makeLoft([lower, upper], True, False)


def wedge_xz(x_wall, x_tip, z, y, depth):
    height = abs(x_tip - x_wall)
    wire = Part.makePolygon(
        [
            App.Vector(x_wall, y, z),
            App.Vector(x_wall, y, z + height),
            App.Vector(x_tip, y, z + height),
            App.Vector(x_wall, y, z),
        ]
    )
    return Part.Face(wire).extrude(App.Vector(0, depth, 0))


def wedge_yz(y_wall, y_tip, z, x, width):
    height = abs(y_tip - y_wall)
    wire = Part.makePolygon(
        [
            App.Vector(x, y_wall, z),
            App.Vector(x, y_wall, z + height),
            App.Vector(x, y_tip, z + height),
            App.Vector(x, y_wall, z),
        ]
    )
    return Part.Face(wire).extrude(App.Vector(width, 0, 0))


def dovetail_prism(wide, narrow, y_wide, y_narrow, z, length):
    wire = Part.makePolygon(
        [
            App.Vector(-wide / 2, y_wide, z),
            App.Vector(wide / 2, y_wide, z),
            App.Vector(narrow / 2, y_narrow, z),
            App.Vector(-narrow / 2, y_narrow, z),
            App.Vector(-wide / 2, y_wide, z),
        ]
    )
    return Part.Face(wire).extrude(App.Vector(0, 0, length))


def translated(shape, vector):
    moved = shape.copy()
    moved.translate(vector)
    return moved


def handed(shape):
    if HAND == "RH":
        return shape
    # FreeCAD mirror RETURNS a shape; unlike translate it does not mutate it.
    return shape.mirror(App.Vector(), App.Vector(0, 1, 0))


def production_solid(shape, name):
    """Strip Boolean wrapper compounds so neutral CAD contains one true solid."""
    refined = shape.removeSplitter()
    if len(refined.Solids) != 1:
        raise RuntimeError(f"{name} did not resolve to exactly one production solid")
    return refined.Solids[0]


def make_hood():
    # Match stations at the taper changes. Previously the inner maximum was
    # above the outer maximum; it crossed the shrinking outside and severed
    # most of the rim. The 4.2 mm horizontal inset is finite through every bay.
    # The broad 24 mm corner chamfers also keep the diagonal faces above 45 deg;
    # checking just the flat front and side faces would miss the worst overhang.
    outer = Part.makeLoft(
        [
            wire_xy(38, 12, 0, 2, -15),
            wire_xy(126, 62, 54, 24, 12),
            wire_xy(126, 62, 59, 24, 12),
            wire_xy(124, 60, HOOD_HEIGHT, 23.4, 12),
        ],
        True,
        True,
    )
    inner = Part.makeLoft(
        [
            wire_xy(36.1185185, 7.3037037, 4, 1.0, -13),
            wire_xy(117.6, 53.6, 54, 21.54, 12),
            wire_xy(117.6, 53.6, 59, 21.54, 12),
            wire_xy(115.6, 51.6, HOOD_HEIGHT, 20.94, 12),
            wire_xy(115.6, 51.6, HOOD_HEIGHT + 1, 20.94, 12),
        ],
        True,
        True,
    )
    hood = outer.cut(inner)

    # Five tapered ports are the only floor openings.  The slightly flared
    # upper diameter avoids a sharp edge where the shaft passes through the
    # sloped inner tray and prints cleanly along the upright axis.
    for x, y in zip(ARROW_X, ARROW_Y):
        hood = hood.cut(
            Part.makeCone(4.0, 4.9, HOOD_HEIGHT + 4, App.Vector(x, y, -2))
        )

    # These are continuations of the two spine chords, not connector tabs.
    # Each starts with the exact chord section and fades into a short internal
    # wall rib below the opening, spreading load without interrupting the rim.
    for x in (-SPINE_X, SPINE_X):
        hood = hood.fuse(
            Part.makeLoft(
                [
                    rectangular_wire_xy(
                        x - SPINE_CHORD / 2,
                        x + SPINE_CHORD / 2,
                        SPINE_TOP_Y,
                        SPINE_TOP_Y + SPINE_DEPTH,
                        0,
                    ),
                    rectangular_wire_xy(
                        x - SPINE_CHORD / 2,
                        x + SPINE_CHORD / 2,
                        -20.65,
                        -10.5,
                        10,
                    ),
                    rectangular_wire_xy(
                        x - SPINE_CHORD / 2,
                        x + SPINE_CHORD / 2,
                        -19.65,
                        -12,
                        BASKET_RIB_HEIGHT,
                    ),
                ],
                True,
                True,
            )
        )
    return hood.removeSplitter()


def make_shaft_clip(x, y):
    pocket = (SHAFT_DIAMETER - CLIP_INTERFERENCE) / 2
    outer = Part.makeCone(
        pocket + 2.4,
        pocket + 2.4 - CLIP_OUTER_TAPER,
        CLIP_HEIGHT,
        App.Vector(x, y, 0),
    )
    bore = Part.makeCylinder(pocket, CLIP_HEIGHT + 2, App.Vector(x, y, -1))
    throat = SHAFT_DIAMETER * 0.67
    opening = Part.makeBox(
        throat,
        9,
        CLIP_HEIGHT + 2,
        App.Vector(x - throat / 2, y, -1),
    )
    return outer.cut(bore.fuse(opening))


def make_male_rail():
    bottom = Part.makePolygon(
        [
            App.Vector(-MALE_NARROW / 2, -14.0, 0),
            App.Vector(MALE_NARROW / 2, -14.0, 0),
            App.Vector(MALE_NARROW / 2, -12.8, 0),
            App.Vector(-MALE_NARROW / 2, -12.8, 0),
            App.Vector(-MALE_NARROW / 2, -14.0, 0),
        ]
    )
    full = Part.makePolygon(
        [
            App.Vector(-MALE_WIDE / 2, -23.7, 10),
            App.Vector(MALE_WIDE / 2, -23.7, 10),
            App.Vector(MALE_NARROW / 2, -13.8, 10),
            App.Vector(-MALE_NARROW / 2, -13.8, 10),
            App.Vector(-MALE_WIDE / 2, -23.7, 10),
        ]
    )
    lead = Part.makeLoft([bottom, full], True, False)
    rail = lead.fuse(dovetail_prism(MALE_WIDE, MALE_NARROW, -23.7, -13.8, 10, 62))
    rail = rail.fuse(Part.makeBox(MALE_NARROW, 1, 72, App.Vector(-10, -13.8, 0)))
    return rail.cut(Part.makeBox(12, 4, 7, App.Vector(-6, -16, 63))).removeSplitter()


def make_chassis():
    pieces = [translated(make_hood(), App.Vector(0, 0, HOOD_Z))]
    for x in (-SPINE_X, SPINE_X):
        pieces.append(
            Part.makeBox(
                SPINE_CHORD,
                SPINE_DEPTH,
                SPINE_TRANSITION_Z - 6,
                App.Vector(x - SPINE_CHORD / 2, SPINE_Y, 8),
            )
        )
        pieces.append(sloped_spine_chord(x))

    # These square/steep bays are printable upright without internal support.
    # The full-depth web avoids the thin enclosed struts used by the SLS version.
    for z1, z2 in SPINE_BAYS:
        if z1 >= SPINE_TRANSITION_Z:
            pieces.append(beam_xz_on_spine(-SPINE_X, z1, SPINE_X, z2, SPINE_BRACE))
            pieces.append(beam_xz_on_spine(SPINE_X, z1, -SPINE_X, z2, SPINE_BRACE))
        else:
            pieces.append(beam_xz(-SPINE_X, z1, SPINE_X, z2, SPINE_BRACE, SPINE_Y, SPINE_DEPTH))
            pieces.append(beam_xz(SPINE_X, z1, -SPINE_X, z2, SPINE_BRACE, SPINE_Y, SPINE_DEPTH))

    # A restrained clip bridge replaces the former four crossing wishbones.
    # Two straight roots sit directly over the spine chords; the shallow
    # chamfered bar carries the five clips without ornamental intersections.
    crossbar = chamfered_prism_xy(
        116,
        7,
        CLIP_BAR_HEIGHT,
        3,
        center_y=7,
    )
    pieces.append(crossbar)
    for x in (-SPINE_X, SPINE_X):
        pieces.append(
            beam_xy(
                x,
                SPINE_Y + SPINE_DEPTH / 2,
                x,
                7,
                8,
                CLIP_BAR_HEIGHT,
            )
        )
    for x, y in zip(ARROW_X, ARROW_Y):
        pieces.append(make_shaft_clip(x, y))
        if y > 16:
            pieces.append(
                beam_xy(
                    x,
                    10.3,
                    x,
                    y - (SHAFT_DIAMETER - CLIP_INTERFERENCE) / 2 - 2.1,
                    4,
                    CLIP_BAR_HEIGHT,
                )
            )

    mount = chamfered_prism_xz(42, DOCK_HEIGHT, 6.5, MOUNT_Y, MOUNT_Z, 5)
    for x in (-13.2, 13.2):
        mount = mount.cut(
            pointed_window_xz(9.5, 44, 7.1, x, MOUNT_Z + 38, MOUNT_Y - 0.3)
        )
    mount = mount.cut(
        Part.makeBox(
            16.4,
            7.7,
            DOCK_HEIGHT,
            App.Vector(-8.2, MOUNT_Y - 0.2, MOUNT_Z),
        )
    )
    pieces.append(mount.fuse(translated(make_male_rail(), App.Vector(0, 0, MOUNT_Z))))

    chassis = pieces[0]
    for piece in pieces[1:]:
        chassis = chassis.fuse(piece)
    return chassis.removeSplitter()


def female_track():
    track = chamfered_prism_xz(38, DOCK_HEIGHT, 10.5, -24, 0, DOCK_CORNER)
    cavity = dovetail_prism(
        FEMALE_WIDE,
        FEMALE_NARROW,
        -24.2,
        -13.35,
        -0.5,
        DOCK_HEIGHT + 1,
    )
    return track.cut(cavity)


def latch_tooth():
    wire = Part.makePolygon(
        [
            App.Vector(-5, -12.4, 63.5),
            App.Vector(-5, -15.2, 63.5),
            App.Vector(-5, -15.2, 64.5),
            App.Vector(-5, -12.4, 69),
            App.Vector(-5, -12.4, 63.5),
        ]
    )
    return Part.Face(wire).extrude(App.Vector(10, 0, 0))


def make_bow_dock():
    lower = (DOCK_HEIGHT - AMO_HOLE_SPACING) / 2
    upper = lower + AMO_HOLE_SPACING
    # One coherent rear plate replaces the stack of circles, bars and diagonal
    # beams.  Side windows leave a central screw land and a continuous rim,
    # matching the chassis mount without creating thin isolated struts.
    back = chamfered_prism_xz(38, DOCK_HEIGHT, 6.3, -30, 0, DOCK_CORNER)
    for x in (-12, 12):
        back = back.cut(
            pointed_window_xz(9.5, 42, 7.0, x, DOCK_HEIGHT / 2, -30.35)
        )

    stop = chamfered_prism_xy(38, 10.5, 4, 3, center_y=-18.75, z=-4)
    stop = stop.fuse(
        chamfered_prism_xy(14, 6.5, 4, 2, center_y=-12.25, z=-4)
    )
    tongue = Part.makeBox(10, 3, 73, App.Vector(-5, -12.4, -4))
    release = chamfered_prism_xz(16, 8, 7, -12.4, 68, 2)
    dock = back.fuse(female_track()).fuse(stop).fuse(tongue).fuse(latch_tooth()).fuse(release)

    # Exposed screw land outside the slide/latch: both screws can be installed
    # and reached without bending the latch or removing the quiver chassis.
    flange = chamfered_prism_xz(32, 60, MOUNT_FLANGE_THICKNESS, -30, 8, 6)
    flange.translate(App.Vector(-22, 0, 0))
    dock = dock.fuse(flange)
    for z, travel in ((lower, MOUNT_SLOT_TRAVEL), (upper, 0.0)):
        cut = Part.makeCylinder(AMO_SCREW_CLEARANCE / 2, 9,
                               App.Vector(MOUNT_HOLE_X, -31, z-travel/2), App.Vector(0, 1, 0))
        if travel:
            cut = cut.fuse(Part.makeCylinder(AMO_SCREW_CLEARANCE / 2, 9,
                                App.Vector(MOUNT_HOLE_X, -31, z+travel/2), App.Vector(0, 1, 0)))
            cut = cut.fuse(Part.makeBox(AMO_SCREW_CLEARANCE, 9, travel,
                                App.Vector(MOUNT_HOLE_X-AMO_SCREW_CLEARANCE/2, -31, z-travel/2)))
        dock = dock.cut(cut)
    return dock.removeSplitter()


def make_foam_reference():
    return Part.makeLoft(
        [
            wire_xy(78, 16, 37, 3, 8),
            wire_xy(90, 24, 44, 6, 10),
            wire_xy(106, 36, 54, 8, 12),
        ],
        True,
        True,
    )


def make_fit_gauge():
    """Optional flat 2 mm mounting-pattern coupon; not a production part."""
    gauge = translated(chamfered_prism_xz(32, 60, 2, -30, 8, 6), App.Vector(-22, 0, 0))
    for z, travel in (((DOCK_HEIGHT-AMO_HOLE_SPACING)/2, MOUNT_SLOT_TRAVEL),
                      ((DOCK_HEIGHT+AMO_HOLE_SPACING)/2, 0)):
        cut = Part.makeCylinder(AMO_SCREW_CLEARANCE/2, 4,
                App.Vector(MOUNT_HOLE_X, -31, z-travel/2), App.Vector(0, 1, 0))
        if travel:
            cut = cut.fuse(translated(cut, App.Vector(0, 0, travel)))
            cut = cut.fuse(Part.makeBox(AMO_SCREW_CLEARANCE, 4, travel,
                App.Vector(MOUNT_HOLE_X-AMO_SCREW_CLEARANCE/2, -31, z-travel/2)))
        gauge = gauge.cut(cut)
    gauge = handed(gauge)
    gauge.rotate(App.Vector(), App.Vector(1, 0, 0), 90)
    return production_solid(gauge, "mount_pattern_gauge")


def validate(name, shape):
    if shape.isNull() or not shape.isValid() or len(shape.Solids) != 1 or shape.Volume <= 0:
        raise RuntimeError(f"{name} is not one valid solid")


def validate_functional_geometry(chassis, dock_placed, foam):
    """Deterministic gates for the interfaces most likely to regress visually."""
    if chassis.common(dock_placed).Volume > 0.05:
        raise RuntimeError("latched dock/chassis hard interference exceeds 0.05 mm3")
    printed_hood = translated(handed(make_hood()), App.Vector(0, 0, HOOD_Z))
    if printed_hood.common(foam).Volume > 0.05:
        raise RuntimeError("foam cartridge hard-interferes with the printed basket")

    clip_bore = (SHAFT_DIAMETER - CLIP_INTERFERENCE) / 2
    for index, (x, y) in enumerate(zip(ARROW_X, ARROW_Y), start=1):
        bore_probe = Part.makeCylinder(
            clip_bore,
            CLIP_HEIGHT + 2,
            App.Vector(x, y, -1),
        )
        if chassis.common(handed(bore_probe)).Volume > 0.05:
            raise RuntimeError(f"shaft clip {index} bore is obstructed")

        port_probe = Part.makeCylinder(
            3.85,
            HOOD_HEIGHT + 4,
            App.Vector(x, y, HOOD_Z - 2),
        )
        if chassis.common(handed(port_probe)).Volume > 0.05:
            raise RuntimeError(f"basket shaft port {index} is obstructed")

    hood = printed_hood
    for x in (-SPINE_X, SPINE_X):
        root_probe = Part.makeBox(
            SPINE_CHORD - 0.5,
            SPINE_DEPTH - 0.5,
            4,
            App.Vector(
                x - (SPINE_CHORD - 0.5) / 2,
                SPINE_TOP_Y + 0.25,
                HOOD_Z,
            ),
        )
        if hood.common(handed(root_probe)).Volume < 150:
            raise RuntimeError(f"basket/spine root at x={x:.1f} lacks direct material")


def manufacturing_shape(name, shape):
    """Place each part for printing while keeping the assembly datums unchanged."""
    ready = shape.copy()
    if name == "bow_dock_petg":
        # Back face on the bed, long flexure axis within XY rather than across
        # layers. Removable local support under the tongue is still required.
        ready.rotate(App.Vector(), App.Vector(1, 0, 0), -90 if HAND == "LH" else 90)
    ready.translate(App.Vector(0, 0, -ready.BoundBox.ZMin))
    return ready


def export_stl(name, shape):
    ready = manufacturing_shape(name, shape)
    box = ready.BoundBox
    ready.translate(App.Vector(-box.XMin, -box.YMin, -box.ZMin))
    mesh = MeshPart.meshFromShape(
        Shape=ready,
        LinearDeflection=LINEAR_DEFLECTION,
        AngularDeflection=ANGULAR_DEFLECTION,
        Relative=False,
    )
    if mesh.CountFacets < 10 or not mesh.isSolid() or abs(mesh.Volume) <= 0:
        raise RuntimeError(f"{name} produced an invalid mesh")
    mesh.write(str(STL_DIR / f"{name}.stl"))
    box = ready.BoundBox
    print(
        f"{name}: {box.XLength:.1f} x {box.YLength:.1f} x {box.ZLength:.1f} mm, "
        f"{shape.Volume / 1000:.1f} cm^3, {mesh.CountFacets} facets"
    )


def export_step(name, label, shape):
    """Write one labeled production solid in its local manufacturing frame."""
    document_name = f"StepExport_{name}"
    if document_name in App.listDocuments():
        App.closeDocument(document_name)
    export_doc = App.newDocument(document_name)
    obj = export_doc.addObject("PartDesign::Feature", name)
    obj.Label = label
    ready = manufacturing_shape(name, shape)
    obj.Shape = ready
    export_doc.recompute()
    path = STEP_DIR / f"{name}.step"
    Part.export([obj], str(path))
    App.closeDocument(document_name)
    print(f"Saved {path}")


def add_shape(doc, group, name, label, shape, color, material, transparency=0):
    obj = doc.addObject("PartDesign::Feature", name)
    obj.Label = label
    obj.Shape = shape
    obj.addProperty("App::PropertyString", "Material", "Build")
    obj.addProperty("App::PropertyString", "RenderColor", "Build")
    obj.addProperty("App::PropertyInteger", "RenderTransparency", "Build")
    obj.addProperty("App::PropertyBool", "RenderVisible", "Build")
    obj.Material = material
    obj.RenderColor = ",".join(f"{channel:.3f}" for channel in color)
    obj.RenderTransparency = transparency
    obj.RenderVisible = True
    if obj.ViewObject is not None:
        obj.ViewObject.ShapeColor = color
        obj.ViewObject.LineColor = (0.04, 0.04, 0.04)
        obj.ViewObject.DisplayMode = "Flat Lines"
        obj.ViewObject.Transparency = transparency
    group.addObject(obj)
    return obj


def main():
    if HAND not in ("RH", "LH"):
        raise ValueError("HAND must be RH or LH")
    if not (0 < CLIP_INTERFERENCE < SHAFT_DIAMETER * 0.15):
        raise ValueError("clip interference is outside the calibration range")
    if BROADHEAD_WIDTH > 34:
        print("WARNING: verify the foam and hood with the production broadhead")
    if SPINE_CHORD < 5 or SPINE_BRACE < 4 or SPINE_DEPTH < 10:
        raise RuntimeError("compact FDM spine is below its design minimum features")

    STL_DIR.mkdir(parents=True, exist_ok=True)
    STEP_DIR.mkdir(parents=True, exist_ok=True)

    chassis = production_solid(handed(make_chassis()), "quiver_chassis_petg")
    dock = production_solid(handed(make_bow_dock()), "bow_dock_petg")
    validate("quiver_chassis_petg", chassis)
    validate("bow_dock_petg", dock)
    if max(chassis.BoundBox.XLength, chassis.BoundBox.YLength, chassis.BoundBox.ZLength) > 252:
        raise RuntimeError("chassis exceeds the 252 mm guarded Bambu Lab A1 envelope")
    dock_placed = translated(dock, App.Vector(0, 0, MOUNT_Z))
    foam = translated(handed(make_foam_reference()), App.Vector(0, 0, HOOD_Z))
    validate_functional_geometry(chassis, dock_placed, foam)

    production = {
        "quiver_chassis_petg": chassis,
        "bow_dock_petg": dock,
    }
    if len(production) != 2:
        raise RuntimeError("production architecture must remain two printed parts")
    for name, shape in production.items():
        export_stl(name, shape)
    export_step(
        "quiver_chassis_petg",
        "LIFT X Compact Quiver Chassis - PETG-HF",
        chassis,
    )
    export_step(
        "bow_dock_petg",
        "LIFT X Integral-Latch Bow Dock - PETG-HF",
        dock,
    )
    gauge = make_fit_gauge()
    export_stl("mount_pattern_gauge", gauge)
    export_step("mount_pattern_gauge", "Optional mounting pattern fit gauge - not load bearing", gauge)

    doc = App.newDocument("LiftX_Quiver")
    parameters = doc.addObject("App::FeaturePython", "Parameters")
    parameters.Label = "Production Parameters (edit generator to rebuild)"
    printed_volume = (chassis.Volume + dock.Volume) / 1000
    for prop, value in (
        ("Hand", HAND),
        ("Architecture", "2 PETG-HF printed parts + foam + 2 bow screws"),
        ("Process", "Bambu Lab A1 FDM; upright chassis; 0.4 mm nozzle"),
        ("Material", "Bambu PETG-HF; dry before printing"),
        ("MountInterface", "PROVISIONAL: exposed 10-24 UNC / 33.325 mm c-c flange; not OEM LowPro"),
        ("BowSetup", "Left-hand LIFT X; Spot-Hogg Eddie variant pending; QAD MX2"),
        ("ShaftDiameter", f"{SHAFT_DIAMETER:.2f} mm"),
        ("BroadheadEnvelope", f"{BROADHEAD_WIDTH:.1f} mm TARGET ONLY; actual heads and containment unverified"),
        ("DockClearance", f"{DOCK_CLEARANCE:.2f} mm per side nominal width clearance"),
        ("PrinterEnvelope", f"{chassis.BoundBox.XLength:.1f} x {chassis.BoundBox.YLength:.1f} x {chassis.BoundBox.ZLength:.1f} mm"),
        ("SpineOptimization", "Continuous swept web; 6 mm chords / 4 mm braces / 12 mm depth"),
        ("SolidVolume", f"{printed_volume:.1f} cm3"),
        ("NominalSolidMass", f"{printed_volume * 1.28:.0f} g upper estimate at 1.28 g/cm3"),
        ("DesignStatus", "FDM prototype: fit, latch, fatigue, heat and bow-clearance validation required"),
    ):
        parameters.addProperty("App::PropertyString", prop, "Inputs")
        setattr(parameters, prop, value)

    printed = doc.addObject("App::DocumentObjectGroup", "PrintedParts")
    refs = doc.addObject("App::DocumentObjectGroup", "ReferenceItems")
    graphite = (0.13, 0.14, 0.15)
    green = (0.38, 0.46, 0.25)
    production_assembly = [
        add_shape(doc, printed, "quiver_chassis_petg", "Compact One-Piece Quiver Chassis / PETG-HF", chassis, graphite, "FDM PETG-HF"),
        add_shape(doc, printed, "bow_dock_petg", "Integral-Latch Bow Dock / PETG-HF", dock_placed, graphite, "FDM PETG-HF"),
    ]

    foam_obj = add_shape(doc, refs, "broadhead_foam", "Press-In Broadhead Foam", foam, green, "Cross-linked PE foam", 25)
    arrows = handed(
        Part.makeCompound(
            [
                Part.makeCylinder(SHAFT_DIAMETER / 2, HOOD_Z + 94, App.Vector(x, y, -42))
                for x, y in zip(ARROW_X, ARROW_Y)
            ]
        )
    )
    add_shape(doc, refs, "arrow_references", "Five Arrow References", arrows, (0.42, 0.29, 0.15), "Measured arrows", 12)

    doc.recompute()
    # XCAF export preserves separate labeled occurrences at the seated contact;
    # Part.export instead collapses both touching parts into a single compound.
    Import.export(production_assembly, str(STEP_DIR / "LiftX_Quiver_Assembly.step"))
    print(f"Saved {STEP_DIR / 'LiftX_Quiver_Assembly.step'}")
    try:
        doc.saveAs(str(OUTPUT_DIR / "LiftX_Quiver_LH.FCStd"))
    except OSError as error:
        print(f"Native document save failed; STEP/STL exports remain available: {error}")
        raise
    else:
        print(f"Saved {OUTPUT_DIR / 'LiftX_Quiver_LH.FCStd'}")


if __name__ in {"__main__", "builtins"}:
    main()
