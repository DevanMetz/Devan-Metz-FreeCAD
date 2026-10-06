"""Equilateral triangle bulkhead for 8 mm stainless rods. Run with FreeCADCmd."""
from math import atan2, cos, degrees, pi, sin, sqrt
from pathlib import Path

import FreeCAD as App
import Mesh
import Part

OUT = Path(__file__).resolve().parent

ROD_D = 8.0
FIT = 0.2
HOLE_D = ROD_D + FIT
PITCH = 180.0
THICK = 8.0
HUB_D = 24.0
BEAM_W = 14.0
CHAMFER = 0.6
SETSCREW_D = 2.8
OVERSHOOT = 1.0


def hole_centers():
    # Centroid at origin; one side horizontal at -Y so the prism stands apex-up.
    r = PITCH / sqrt(3)
    return [(r * cos(a), r * sin(a)) for a in (pi / 2, pi / 2 + 2 * pi / 3, pi / 2 + 4 * pi / 3)]


def beam(p1, p2):
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    length = sqrt(dx * dx + dy * dy)
    box = Part.makeBox(length, BEAM_W, THICK, App.Vector(0, -BEAM_W / 2, 0))
    box.rotate(App.Vector(0, 0, 0), App.Vector(0, 0, 1), degrees(atan2(dy, dx)))
    box.translate(App.Vector(x1, y1, 0))
    return box


def hub(x, y):
    return Part.makeCylinder(HUB_D / 2, THICK, App.Vector(x, y, 0))


def rod_bore(x, y):
    return Part.makeCylinder(
        HOLE_D / 2, THICK + 2 * OVERSHOOT, App.Vector(x, y, -OVERSHOOT)
    )


def hole_chamfers(x, y):
    r_big = HOLE_D / 2 + CHAMFER
    top = Part.makeCone(HOLE_D / 2, r_big, CHAMFER, App.Vector(x, y, THICK - CHAMFER))
    bottom = Part.makeCone(r_big, HOLE_D / 2, CHAMFER, App.Vector(x, y, 0))
    return top.fuse(bottom)


def setscrew(x, y):
    r = sqrt(x * x + y * y)
    ux, uy = x / r, y / r
    start = App.Vector(x + ux * (HUB_D / 2 + OVERSHOOT), y + uy * (HUB_D / 2 + OVERSHOOT), THICK / 2)
    return Part.makeCylinder(SETSCREW_D / 2, HUB_D / 2 + 4, start, App.Vector(-ux, -uy, 0))


def triangle_shape():
    pts = hole_centers()
    body = hub(*pts[0]).fuse(hub(*pts[1])).fuse(hub(*pts[2]))
    body = body.fuse(beam(pts[0], pts[1])).fuse(beam(pts[1], pts[2])).fuse(beam(pts[2], pts[0]))
    body = body.removeSplitter()
    cut = rod_bore(*pts[0]).fuse(rod_bore(*pts[1])).fuse(rod_bore(*pts[2]))
    cut = cut.fuse(hole_chamfers(*pts[0])).fuse(hole_chamfers(*pts[1])).fuse(hole_chamfers(*pts[2]))
    cut = cut.fuse(setscrew(*pts[0])).fuse(setscrew(*pts[1])).fuse(setscrew(*pts[2]))
    return body.cut(cut).removeSplitter()


def build():
    doc = App.newDocument("PedalboardTriangle")
    shape = triangle_shape()
    body = doc.addObject("PartDesign::Feature", "Triangle")
    body.Label = "8mm rod triangle"
    body.Shape = shape
    body.addProperty("App::PropertyString", "Rod", "Design").Rod = "8 mm stainless, 8.2 mm printed hole"
    body.addProperty("App::PropertyString", "Pitch", "Design").Pitch = "180 mm hole-to-hole, equilateral"
    body.addProperty("App::PropertyString", "Use", "Design").Use = "Print 3; slide onto 3 rods; lock with M3 set screws"
    doc.recompute()
    OUT.mkdir(parents=True, exist_ok=True)
    doc.saveAs(str(OUT / "Pedalboard_Triangle.FCStd"))
    Part.export([body], str(OUT / "Pedalboard_Triangle.step"))
    Mesh.export([body], str(OUT / "Pedalboard_Triangle.stl"))
    assert not body.Shape.isNull() and body.Shape.isValid() and body.Shape.Volume > 0
    bb = body.Shape.BoundBox
    print(
        f"volume={body.Shape.Volume:.0f} mm^3  "
        f"bbox={bb.XLength:.1f} x {bb.YLength:.1f} x {bb.ZLength:.1f} mm"
    )


build()
