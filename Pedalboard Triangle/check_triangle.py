"""Measure hole diameters and center distances. Run with FreeCADCmd."""
from math import hypot
from pathlib import Path

import Part

STEP = Path(__file__).resolve().parent / "Pedalboard_Triangle.step"
shape = Part.Shape()
shape.read(str(STEP))
assert shape.isValid() and shape.Volume > 0

holes = []
for face in shape.Faces:
    surf = face.Surface
    if surf.TypeId != "Part::GeomCylinder":
        continue
    if abs(surf.Radius - 4.1) > 0.05:
        continue
    if abs(surf.Axis.z) < 0.9:
        continue
    c = surf.Center
    holes.append((round(c.x, 3), round(c.y, 3), surf.Radius * 2))

unique = []
for hole in holes:
    if not any(hypot(hole[0] - other[0], hole[1] - other[1]) < 1 for other in unique):
        unique.append(hole)

print("holes", unique)
assert len(unique) == 3, unique
for a, b in ((0, 1), (1, 2), (2, 0)):
    pitch = hypot(unique[a][0] - unique[b][0], unique[a][1] - unique[b][1])
    print("pitch", pitch)
    assert abs(pitch - 180) < 0.05, pitch
    assert abs(unique[a][2] - 8.2) < 0.05
print("ok")
