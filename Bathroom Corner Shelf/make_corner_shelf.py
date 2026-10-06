"""Build and export a 3-tier, 185 mm bathroom corner shelf for an 8 mm rod."""

from pathlib import Path
import math

import FreeCAD as App
import Part
import MeshPart


OUT = Path(__file__).resolve().parent

# Main dimensions (mm)
SHELF_RADIUS = 185
PLATE_THICKNESS = 4
GRATE_PITCH = 20
GRATE_BAR_WIDTH = 5
GRATE_BORDER = 5
LIP_HEIGHT = 14
LIP_THICKNESS = 3
ROD_DIAMETER = 8
FIT_CLEARANCE = 0.2
ROD_HOLE = ROD_DIAMETER + FIT_CLEARANCE
ROD_X = ROD_Y = 18
HUB_DIAMETER = 24
HUB_HEIGHT = 16
TIER_PITCH = 140
SPACER_LENGTH = (TIER_PITCH - HUB_HEIGHT) / 2  # two pieces between tiers
SPACER_DIAMETER = 15
ROD_LENGTH = 300
EDGE_FILLET = 1.5
EDGE_CHAMFER = 0.8
OUTER_CORNER_CHAMFER = 5
BACK_CORNER_FILLET = 8


def quarter_disc(radius, height, z=0):
    return Part.makeCylinder(radius, height, App.Vector(0, 0, z)).common(
        Part.makeBox(radius, radius, height, App.Vector(0, 0, z))
    )


def rod_bore(height, z=0):
    return Part.makeCylinder(
        ROD_HOLE / 2, height, App.Vector(ROD_X, ROD_Y, z)
    )


def shelf_shape():
    plate = quarter_disc(SHELF_RADIUS, PLATE_THICKNESS)
    opening = GRATE_PITCH - GRATE_BAR_WIDTH
    cells = [
        Part.makeBox(opening, opening, PLATE_THICKNESS, App.Vector(x, y, 0))
        for x in range(GRATE_BORDER, SHELF_RADIUS, GRATE_PITCH)
        for y in range(GRATE_BORDER, SHELF_RADIUS, GRATE_PITCH)
    ]
    plate = plate.cut(
        Part.makeCompound(cells).common(
            quarter_disc(SHELF_RADIUS - GRATE_BORDER, PLATE_THICKNESS)
        )
    )
    front_bottom = [
        e for e in plate.Edges
        if type(e.Curve).__name__ == "Circle"
        and abs(e.Curve.Radius - SHELF_RADIUS) < 0.01
        and e.BoundBox.ZMax == 0
    ]
    plate = plate.makeFillet(EDGE_FILLET, front_bottom)

    # Low retaining lips keep bottles aboard without making the tray hard to clean.
    x_lip = Part.makeBox(SHELF_RADIUS, LIP_THICKNESS, LIP_HEIGHT)
    x_lip = x_lip.makeChamfer(EDGE_CHAMFER, [
        e for e in x_lip.Edges
        if e.Length > 150 and e.BoundBox.YMin == LIP_THICKNESS and e.BoundBox.ZMin == LIP_HEIGHT
    ])
    y_lip = Part.makeBox(LIP_THICKNESS, SHELF_RADIUS, LIP_HEIGHT)
    y_lip = y_lip.makeChamfer(EDGE_CHAMFER, [
        e for e in y_lip.Edges
        if e.Length > 150 and e.BoundBox.XMin == LIP_THICKNESS and e.BoundBox.ZMin == LIP_HEIGHT
    ])
    straight_lips = x_lip.fuse(y_lip)
    back_center = App.Vector(BACK_CORNER_FILLET, BACK_CORNER_FILLET, 0)
    back_ring = Part.makeCylinder(BACK_CORNER_FILLET, LIP_HEIGHT, back_center).cut(
        Part.makeCylinder(BACK_CORNER_FILLET - LIP_THICKNESS, LIP_HEIGHT, back_center)
    ).common(Part.makeBox(BACK_CORNER_FILLET, BACK_CORNER_FILLET, LIP_HEIGHT))
    back_ring = back_ring.makeChamfer(EDGE_CHAMFER, [
        e for e in back_ring.Edges
        if type(e.Curve).__name__ == "Circle"
        and e.BoundBox.ZMin == LIP_HEIGHT and e.BoundBox.XMin > 0
    ])
    straight_lips = straight_lips.fuse(back_ring)
    arc_lip = quarter_disc(SHELF_RADIUS, LIP_HEIGHT).cut(
        quarter_disc(SHELF_RADIUS - LIP_THICKNESS, LIP_HEIGHT)
    )
    arc_lip = arc_lip.makeChamfer(EDGE_CHAMFER, [
        e for e in arc_lip.Edges
        if type(e.Curve).__name__ == "Circle"
        and e.BoundBox.ZMin == LIP_HEIGHT
        and e.BoundBox.XMax < SHELF_RADIUS
    ])
    hub = Part.makeCylinder(
        HUB_DIAMETER / 2, HUB_HEIGHT, App.Vector(ROD_X, ROD_Y, 0)
    )
    hub = hub.makeFillet(1, [e for e in hub.Edges if e.BoundBox.ZMin == HUB_HEIGHT])
    tray = plate.fuse(straight_lips).fuse(arc_lip).fuse(hub)

    bore = rod_bore(HUB_HEIGHT).fuse(Part.makeCone(
        ROD_HOLE / 2, ROD_HOLE / 2 + 0.6, 0.6,
        App.Vector(ROD_X, ROD_Y, HUB_HEIGHT - 0.6),
    ))
    tray = tray.cut(bore)

    # Bevel the two exposed ends where the curved front meets the wall edges.
    right = [
        App.Vector(SHELF_RADIUS - OUTER_CORNER_CHAMFER, 0, -1),
        App.Vector(SHELF_RADIUS + 2, -2, -1),
        App.Vector(SHELF_RADIUS + 2, OUTER_CORNER_CHAMFER + 2, -1),
    ]
    left = [
        App.Vector(0, SHELF_RADIUS - OUTER_CORNER_CHAMFER, -1),
        App.Vector(-2, SHELF_RADIUS + 2, -1),
        App.Vector(OUTER_CORNER_CHAMFER + 2, SHELF_RADIUS + 2, -1),
    ]
    cutters = Part.Face(Part.makePolygon(right + [right[0]])).extrude(App.Vector(0, 0, LIP_HEIGHT + 2))
    cutters = cutters.fuse(
        Part.Face(Part.makePolygon(left + [left[0]])).extrude(App.Vector(0, 0, LIP_HEIGHT + 2))
    )
    tray = tray.cut(cutters)

    # Restore a constant-thickness retaining wall across each corner bevel.
    diagonal = (2 * SHELF_RADIUS ** 2 - (SHELF_RADIUS - OUTER_CORNER_CHAMFER) ** 2) ** 0.5
    bevel_y = (diagonal - (SHELF_RADIUS - OUTER_CORNER_CHAMFER)) / 2
    offset = LIP_THICKNESS / math.sqrt(2)
    outer_a = App.Vector(SHELF_RADIUS - OUTER_CORNER_CHAMFER, 0, 0)
    outer_b = App.Vector(SHELF_RADIUS - OUTER_CORNER_CHAMFER + bevel_y, bevel_y, 0)
    inner_a = App.Vector(outer_a.x - offset, outer_a.y + offset, 0)
    inner_b = App.Vector(outer_b.x - offset, outer_b.y + offset, 0)
    right_wall = Part.Face(Part.makePolygon(
        [outer_a, outer_b, inner_b, inner_a, outer_a]
    )).extrude(App.Vector(0, 0, LIP_HEIGHT))
    right_wall = right_wall.makeChamfer(EDGE_CHAMFER, [
        e for e in right_wall.Edges
        if e.BoundBox.ZMin == LIP_HEIGHT and e.Length > OUTER_CORNER_CHAMFER
        and e.CenterOfMass.x - e.CenterOfMass.y < SHELF_RADIUS - OUTER_CORNER_CHAMFER - 2
    ])

    outer_a = App.Vector(0, SHELF_RADIUS - OUTER_CORNER_CHAMFER, 0)
    outer_b = App.Vector(bevel_y, SHELF_RADIUS - OUTER_CORNER_CHAMFER + bevel_y, 0)
    inner_a = App.Vector(outer_a.x + offset, outer_a.y - offset, 0)
    inner_b = App.Vector(outer_b.x + offset, outer_b.y - offset, 0)
    left_wall = Part.Face(Part.makePolygon(
        [outer_a, inner_a, inner_b, outer_b, outer_a]
    )).extrude(App.Vector(0, 0, LIP_HEIGHT))
    left_wall = left_wall.makeChamfer(EDGE_CHAMFER, [
        e for e in left_wall.Edges
        if e.BoundBox.ZMin == LIP_HEIGHT and e.Length > OUTER_CORNER_CHAMFER
        and e.CenterOfMass.y - e.CenterOfMass.x < SHELF_RADIUS - OUTER_CORNER_CHAMFER - 2
    ])

    tray = tray.fuse(right_wall).fuse(left_wall)

    # Round the outside rear corner to match the inside radius at full wall thickness.
    rear_box = Part.makeBox(
        BACK_CORNER_FILLET, BACK_CORNER_FILLET, LIP_HEIGHT + 2,
        App.Vector(0, 0, -1),
    )
    rear_round = Part.makeCylinder(
        BACK_CORNER_FILLET, LIP_HEIGHT + 2,
        App.Vector(BACK_CORNER_FILLET, BACK_CORNER_FILLET, -1),
    )
    return tray.cut(rear_box.cut(rear_round))


def tube_shape(length, outer_diameter=SPACER_DIAMETER):
    tube = Part.makeCylinder(outer_diameter / 2, length).cut(
        Part.makeCylinder(ROD_HOLE / 2, length)
    )
    tube = tube.makeFillet(0.8, [e for e in tube.Edges if e.BoundBox.XLength > outer_diameter - 1])
    return tube.makeChamfer(0.5, [
        e for e in tube.Edges if ROD_HOLE - 0.5 < e.BoundBox.XLength < ROD_HOLE + 0.5
    ])


def cap_shape():
    # Four millimetres of rod remain above the top hub; the 2 mm roof hides it.
    cap = Part.makeCylinder(7.5, 6).cut(Part.makeCylinder(ROD_HOLE / 2, 4))
    cap = cap.makeFillet(0.8, [e for e in cap.Edges if e.BoundBox.XLength > 14])
    return cap.makeChamfer(0.5, [
        e for e in cap.Edges
        if ROD_HOLE - 0.5 < e.BoundBox.XLength < ROD_HOLE + 0.5 and e.BoundBox.ZMax == 0
    ])


def add_feature(doc, name, label, shape, color):
    obj = doc.addObject("PartDesign::Feature", name)
    obj.Label = label
    obj.Shape = shape
    if obj.ViewObject:
        obj.ViewObject.ShapeColor = color
    return obj


def build():
    doc = App.newDocument("BathroomCornerShelf")

    params = doc.addObject("App::FeaturePython", "Parameters")
    for name, value in (
        ("ShelfRadius", SHELF_RADIUS),
        ("PlateThickness", PLATE_THICKNESS),
        ("GratePitch", GRATE_PITCH),
        ("GrateBarWidth", GRATE_BAR_WIDTH),
        ("GrateBorder", GRATE_BORDER),
        ("LipHeight", LIP_HEIGHT),
        ("RodDiameter", ROD_DIAMETER),
        ("RodHole", ROD_HOLE),
        ("TierPitch", TIER_PITCH),
        ("RodLength", ROD_LENGTH),
        ("SpacerLength", SPACER_LENGTH),
        ("EdgeFillet", EDGE_FILLET),
        ("EdgeChamfer", EDGE_CHAMFER),
        ("OuterCornerChamfer", OUTER_CORNER_CHAMFER),
        ("BackCornerFillet", BACK_CORNER_FILLET),
    ):
        params.addProperty("App::PropertyLength", name, "Dimensions")
        setattr(params, name, value)

    shelf = shelf_shape()
    spacer = tube_shape(SPACER_LENGTH)
    cap = cap_shape()
    assert shelf.isValid() and spacer.isValid() and cap.isValid()
    assert all(len(shape.Solids) == 1 for shape in (shelf, spacer, cap))
    assert HUB_HEIGHT + 2 * SPACER_LENGTH == TIER_PITCH
    assert 2 * TIER_PITCH + HUB_HEIGHT <= ROD_LENGTH

    for index, z in enumerate((0, TIER_PITCH, TIER_PITCH * 2), 1):
        part = add_feature(doc, f"Shelf{index}", f"Shelf {index}", shelf, (0.30, 0.70, 0.88))
        part.Placement.Base.z = z

    spacer_z = (HUB_HEIGHT, HUB_HEIGHT + SPACER_LENGTH,
                TIER_PITCH + HUB_HEIGHT, TIER_PITCH + HUB_HEIGHT + SPACER_LENGTH)
    for index, z in enumerate(spacer_z, 1):
        part = add_feature(doc, f"Spacer{index}", f"Spacer {index}", spacer, (0.85, 0.85, 0.85))
        part.Placement.Base = App.Vector(ROD_X, ROD_Y, z)

    rod = add_feature(
        doc,
        "CarbonRod",
        "8 x 300 mm carbon rod (reference)",
        Part.makeCylinder(ROD_DIAMETER / 2, ROD_LENGTH, App.Vector(ROD_X, ROD_Y, 0)),
        (0.08, 0.08, 0.08),
    )
    if rod.ViewObject:
        rod.ViewObject.LineColor = (0.3, 0.3, 0.3)

    cap_obj = add_feature(doc, "TopCap", "Top cap", cap, (0.85, 0.85, 0.85))
    cap_obj.Placement.Base = App.Vector(ROD_X, ROD_Y, 296)

    doc.recompute()
    doc.saveAs(str(OUT / "Bathroom Corner Shelf.FCStd"))

    for shape, filename in ((shelf, "shelf.stl"), (spacer, "spacer.stl"), (cap, "top_cap.stl")):
        MeshPart.meshFromShape(
            Shape=shape, LinearDeflection=0.1, AngularDeflection=0.25, Relative=False
        ).write(str(OUT / filename))
    App.closeDocument(doc.Name)
    print("Built valid shelf, spacer, and cap solids; assembly height: 302 mm")


if __name__ == "__main__":
    build()
