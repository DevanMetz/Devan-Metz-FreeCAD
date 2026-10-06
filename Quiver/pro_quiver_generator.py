"""Generate a lightweight four-arrow hunting quiver and production STLs.

Run with FreeCADCmd, not regular Python. Dimensions are millimetres.
"""

from pathlib import Path

import FreeCAD as App
import MeshPart
import Part


# Change these three values after measuring the actual equipment.
ROD_DIAMETER = 4.0
ROD_SPACING = 10.0
ARROW_DIAMETER = 6.5
BOW_BOLT_DIAMETER = 5.0

# Printer/material tuning knobs.
ROD_CLEARANCE = 0.20
TPU_ROD_INTERFERENCE = 0.15
TPU_GRIP_INTERFERENCE = 0.25
MESH_LINEAR_DEFLECTION = 0.08
MESH_ANGULAR_DEFLECTION = 0.12

ROOT = Path(__file__).resolve().parent
STL_DIR = ROOT / "STL"


def rounded_box(width, depth, height, radius, z=0):
    """Axis-aligned box with rounded vertical corners, centred on X/Y."""
    x, y = -width / 2, -depth / 2
    shape = Part.makeBox(width - 2 * radius, depth, height, App.Vector(x + radius, y, z))
    shape = shape.fuse(Part.makeBox(width, depth - 2 * radius, height, App.Vector(x, y + radius, z)))
    for cx in (x + radius, x + width - radius):
        for cy in (y + radius, y + depth - radius):
            shape = shape.fuse(Part.makeCylinder(radius, height, App.Vector(cx, cy, z)))
    return shape.removeSplitter()


def rear_rod_base(interface_y, height=26):
    """Minimal rear clamp with the rods centred behind the arrow row."""
    base = Part.makeBox(18, 7, height, App.Vector(-9, interface_y - 7, 0))
    rod_radius = (ROD_DIAMETER + ROD_CLEARANCE) / 2
    for x in (-ROD_SPACING / 2, ROD_SPACING / 2):
        groove = Part.makeCylinder(rod_radius, height + 2, App.Vector(x, interface_y, -1))
        base = base.cut(groove)
    for z in (7, 19):
        insert_pilot = Part.makeCylinder(2.05, 7, App.Vector(0, interface_y - 6, z), App.Vector(0, 1, 0))
        base = base.cut(insert_pilot)
    return base.removeSplitter()


def make_end_cap():
    cap = Part.makeBox(18, 6, 26, App.Vector(-9, 0, 0))
    rod_radius = (ROD_DIAMETER + ROD_CLEARANCE) / 2
    for x in (-ROD_SPACING / 2, ROD_SPACING / 2):
        groove = Part.makeCylinder(rod_radius, 28, App.Vector(x, 0, -1))
        cap = cap.cut(groove)
    for z in (7, 19):
        hole = Part.makeCylinder(1.7, 8, App.Vector(0, -1, z), App.Vector(0, 1, 0))
        cap = cap.cut(hole)
    return cap.removeSplitter()


def make_hood():
    # Open-bottom shell: 2.2 mm walls, 2.5 mm crown, four broadheads in foam.
    outer = rounded_box(102, 46, 48, 7)
    cavity = rounded_box(97.6, 41.6, 45.5, 4.8, z=-0.1)
    hood = outer.cut(cavity)
    return hood.fuse(rear_rod_base(29)).removeSplitter()


def make_gripper():
    # TPU bar; all four shafts load from the side facing -Y.
    gripper = rounded_box(78, 18, 10, 3)
    pocket_radius = (ARROW_DIAMETER - TPU_GRIP_INTERFERENCE) / 2
    throat = ARROW_DIAMETER * 0.67
    for x in (-27, -9, 9, 27):
        pocket = Part.makeCylinder(pocket_radius, 12, App.Vector(x, 0, -1))
        opening = Part.makeBox(throat, 10, 12, App.Vector(x - throat / 2, -10, -1))
        gripper = gripper.cut(pocket.fuse(opening))
    socket = Part.makeBox(18, 22, 8, App.Vector(-9, 8, 0))
    bore_radius = (ROD_DIAMETER - TPU_ROD_INTERFERENCE) / 2
    for x in (-ROD_SPACING / 2, ROD_SPACING / 2):
        socket = socket.fuse(Part.makeCylinder(4.5, 26, App.Vector(x, 29, 0)))
        socket = socket.cut(Part.makeCylinder(bore_radius, 28, App.Vector(x, 29, -1)))
    return gripper.fuse(socket).removeSplitter()


def make_bow_mount():
    # Offset slot leaves the two centred rods directly behind the arrows.
    plate = Part.makeBox(38, 6, 50, App.Vector(-28, -6, 0))
    rod_radius = (ROD_DIAMETER + ROD_CLEARANCE) / 2
    for x in (-ROD_SPACING / 2, ROD_SPACING / 2):
        groove = Part.makeCylinder(rod_radius, 52, App.Vector(x, 0, -1), App.Vector(0, 0, 1))
        plate = plate.cut(groove)
    slot_radius = BOW_BOLT_DIAMETER / 2 + 0.25
    low_z = 25 - 34 / 2
    bow_slot = Part.makeBox(2 * slot_radius, 8, 34, App.Vector(-20 - slot_radius, -7, low_z))
    bow_slot = bow_slot.fuse(
        Part.makeCylinder(slot_radius, 8, App.Vector(-20, -7, low_z), App.Vector(0, 1, 0))
    )
    bow_slot = bow_slot.fuse(
        Part.makeCylinder(slot_radius, 8, App.Vector(-20, -7, low_z + 34), App.Vector(0, 1, 0))
    )
    plate = plate.cut(bow_slot)

    for z in (10, 40):
        hole = Part.makeCylinder(1.7, 8, App.Vector(0, -7, z), App.Vector(0, 1, 0))
        plate = plate.cut(hole)
    return plate.removeSplitter()


def make_mount_cap():
    cap = Part.makeBox(18, 6, 50, App.Vector(-9, 0, 0))
    rod_radius = (ROD_DIAMETER + ROD_CLEARANCE) / 2
    for x in (-ROD_SPACING / 2, ROD_SPACING / 2):
        groove = Part.makeCylinder(rod_radius, 52, App.Vector(x, 0, -1), App.Vector(0, 0, 1))
        cap = cap.cut(groove)
    for z in (10, 40):
        hole = Part.makeCylinder(1.7, 8, App.Vector(0, -1, z), App.Vector(0, 1, 0))
        cap = cap.cut(hole)
    return cap.removeSplitter()


def validate(name, shape):
    if shape.isNull() or not shape.isValid() or len(shape.Solids) != 1 or shape.Volume <= 0:
        raise RuntimeError(f"{name} is not one valid solid")


def export_stl(name, shape):
    mesh = MeshPart.meshFromShape(
        Shape=shape,
        LinearDeflection=MESH_LINEAR_DEFLECTION,
        AngularDeflection=MESH_ANGULAR_DEFLECTION,
        Relative=False,
    )
    if mesh.CountFacets < 100 or mesh.Volume <= 0 or not mesh.isSolid():
        raise RuntimeError(f"{name} produced an invalid mesh")
    mesh.write(str(STL_DIR / f"{name}.stl"))
    box = shape.BoundBox
    print(
        f"{name}: {box.XLength:.1f} x {box.YLength:.1f} x {box.ZLength:.1f} mm, "
        f"{shape.Volume / 1000:.1f} cm^3, {mesh.CountFacets} facets"
    )


def main():
    STL_DIR.mkdir(exist_ok=True)
    parts = {
        "hood_petg": make_hood(),
        "hood_rod_cap_petg": make_end_cap(),
        "shaft_gripper_tpu": make_gripper(),
        "bow_mount_petg": make_bow_mount(),
        "bow_mount_cap_petg": make_mount_cap(),
    }

    doc = App.newDocument("QuiverPro")
    for name, shape in parts.items():
        validate(name, shape)
        obj = doc.addObject("PartDesign::Feature", name)
        obj.Label = name.replace("_", " ").title()
        obj.Shape = shape
        export_stl(name, shape)
    doc.recompute()
    doc.saveAs(str(ROOT / "QuiverPro.FCStd"))


# FreeCADCmd imports script arguments as modules instead of using __main__.
main()
