"""Run with FreeCADCmd to create the topology-inspired printable bracket."""
from pathlib import Path
from math import sqrt
import FreeCAD as App
import Mesh
import Part

OUT = Path(__file__).parent
doc = App.newDocument("LongboardWallHolder")


def prism(points, width=18, z=6):
    wire = Part.makePolygon([App.Vector(x, y, z) for x, y in points] + [App.Vector(*points[0], z)])
    return Part.Face(wire).extrude(App.Vector(0, 0, width))


def diamond_wire(x, y, radius):
    a = radius * sqrt(2)
    points = [App.Vector(x, y + a, 16), App.Vector(x, y, 16 + a),
              App.Vector(x, y - a, 16), App.Vector(x, y, 16 - a)]
    return Part.makePolygon(points + points[:1])


# Shallow cradle: the deck stands on edge, grip tape toward the wall and artwork outward.
wall = Part.makeBox(8, 90, 32)
floor = Part.makeBox(30, 10, 32, App.Vector(6, 20, 0))
lip = Part.makeBox(8, 28, 32, App.Vector(30, 20, 0))
retaining_bead = Part.makeBox(11, 4, 32, App.Vector(27, 44, 0))
gusset = prism([(6, 5), (6, 20), (36, 20), (28, 5)], width=32, z=0)
shape = wall.fuse(floor).fuse(lip).fuse(retaining_bead).fuse(gusset).removeSplitter()

# Round every side-profile corner; these edges extrude straight from the flat print face.
rounded = ((0, 0), (0, 90), (8, 90), (28, 5), (38, 20), (38, 48), (27, 48))
profile_edges = [edge for edge in shape.Edges if len(edge.Vertexes) == 2 and
                 abs(edge.Vertexes[0].Point.x - edge.Vertexes[1].Point.x) < 1e-6 and
                 abs(edge.Vertexes[0].Point.y - edge.Vertexes[1].Point.y) < 1e-6 and
                 any(abs(edge.Vertexes[0].Point.x - x) < 1e-6 and
                     abs(edge.Vertexes[0].Point.y - y) < 1e-6 for x, y in rounded)]
shape = shape.makeFillet(1.5, profile_edges)

# Support-free M5 countersinks: diamond profiles keep every printed ceiling at 45 degrees.
for y in (22, 72):
    clearance = Part.Face(diamond_wire(0, y, 2.75)).extrude(App.Vector(4, 0, 0))
    countersink = Part.makeLoft([diamond_wire(4, y, 2.75), diamond_wire(8, y, 5.0)], True)
    shape = shape.cut(clearance.fuse(countersink))

# A small perimeter chamfer removes sharp side-face edges without sacrificing the flat bed contact.
side_edges = [edge for edge in shape.Edges if edge.Vertexes and
              (all(abs(vertex.Point.z) < 1e-6 for vertex in edge.Vertexes) or
               all(abs(vertex.Point.z - 32) < 1e-6 for vertex in edge.Vertexes))]
shape = shape.makeChamfer(0.6, side_edges)
shape = shape.removeSplitter()

body = doc.addObject("PartDesign::Feature", "Bracket")
body.Label = "Topology-optimized longboard bracket"
body.Shape = shape
body.addProperty("App::PropertyString", "Material", "Design").Material = "PETG, 6+ walls, 40% gyroid (prototype assumption)"
body.addProperty("App::PropertyForce", "DesignLoad", "Design").DesignLoad = 176.58
body.addProperty("App::PropertyString", "DeckOpening", "Design").DeckOpening = "22 mm cradle; 19 mm at retaining bead before padding"
body.addProperty("App::PropertyString", "Use", "Design").Use = "Print two; space along deck length; artwork faces outward"
body.addProperty("App::PropertyString", "EdgeTreatment", "Design").EdgeTreatment = "1.5 mm profile fillets; 0.6 mm side chamfers; 45 degree countersinks"
doc.recompute()
doc.saveAs(str(OUT / "Longboard_Wall_Holder.FCStd"))
Part.export([body], str(OUT / "Longboard_Wall_Holder.step"))
Mesh.export([body], str(OUT / "Longboard_Wall_Holder.stl"))

assert not body.Shape.isNull() and body.Shape.isValid() and body.Shape.Volume > 0
print(f"volume={body.Shape.Volume:.0f} mm^3 mass~={body.Shape.Volume * 1.27e-3:.0f} g")
