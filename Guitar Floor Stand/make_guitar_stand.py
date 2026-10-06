"""Build a smooth implicit topology guitar floor stand."""

from pathlib import Path

import FreeCAD as App
import Mesh
import numpy as np
import Part
from scipy.ndimage import gaussian_filter
from scipy.spatial import Delaunay
import vtk
from vtk.util.numpy_support import numpy_to_vtk


OUT = Path(__file__).resolve().parent
BODY_THICKNESS = 45
PAD_THICKNESS = 3
CRADLE_GAP = BODY_THICKNESS + 2 * PAD_THICKNESS
FOOTPRINT = 234
SIDE_CENTERS = (37, 193)


def load_optimized_radii(points, edges):
    loads = []
    for force in ((0, 25, -75), (35, 0, -50), (-35, 0, -50)):
        load = np.zeros(3 * len(points))
        load[3 * 12:3 * 12 + 3] = force
        loads.append(load)
    fixed = [dof for node in (0, 2, 4) for dof in range(3 * node, 3 * node + 3)]
    free = np.setdiff1d(np.arange(3 * len(points)), fixed)
    area = {edge: np.pi * 5 ** 2 for edge in edges}

    for _ in range(12):
        stiffness = np.zeros((3 * len(points), 3 * len(points)))
        for a, b in edges:
            delta = points[b] - points[a]
            length = np.linalg.norm(delta)
            direction = delta / length
            spring = 2000 * area[a, b] / length * np.outer(direction, direction)
            ia, ib = np.arange(3 * a, 3 * a + 3), np.arange(3 * b, 3 * b + 3)
            stiffness[np.ix_(ia, ia)] += spring
            stiffness[np.ix_(ib, ib)] += spring
            stiffness[np.ix_(ia, ib)] -= spring
            stiffness[np.ix_(ib, ia)] -= spring

        axial = {edge: 0.0 for edge in edges}
        for load in loads:
            displacement = np.zeros_like(load)
            displacement[free] = np.linalg.solve(stiffness[np.ix_(free, free)], load[free])
            for a, b in edges:
                delta = points[b] - points[a]
                length = np.linalg.norm(delta)
                direction = delta / length
                value = abs(2000 * area[a, b] / length * np.dot(
                    displacement[3 * b:3 * b + 3] - displacement[3 * a:3 * a + 3], direction
                ))
                axial[a, b] = max(axial[a, b], value)
        peak = max(axial.values())
        target = {edge: np.pi * (3.2 + 6.3 * (axial[edge] / peak) ** 0.4) ** 2 for edge in edges}
        area = {edge: 0.35 * area[edge] + 0.65 * target[edge] for edge in edges}

    radii = {edge: np.sqrt(value / np.pi) for edge, value in area.items()}
    assert peak > 0 and len(radii) >= 40 and all(3.2 <= radius <= 9.5 for radius in radii.values())
    return radii


def side_segments(x, mirror):
    points = np.array([
        (0, 72, 28), (-8, 95, 42), (9, 128, 20), (-6, 175, 25),
        (3, 224, 10), (10, 93, 82), (-10, 120, 72), (4, 155, 65),
        (-8, 192, 55), (-11, 103, 125), (7, 130, 115), (-4, 160, 105),
        (5, 114, 174), (-7, 145, 155), (10, 175, 135),
    ], dtype=float)
    points[:, 0] = x + mirror * points[:, 0]
    candidates = {
        tuple(sorted((int(a), int(b))))
        for cell in Delaunay(points).simplices
        for a in cell for b in cell
        if a < b and np.linalg.norm(points[a] - points[b]) < 75
    }
    radii = load_optimized_radii(points, candidates)
    segments = [(points[a], points[b], radius, radius) for (a, b), radius in radii.items()]
    toe = np.array((x, 10, 9.0))
    lip = np.array((x - 4 * mirror, 10, 59.0))
    seat = np.array((x + 3 * mirror, 34, 17.0))
    segments.extend(((toe, seat, 9.5, 12), (lip, seat, 9, 11), (seat, points[0], 11, 10)))
    return segments


def stand_segments():
    segments = side_segments(SIDE_CENTERS[0], 1) + side_segments(SIDE_CENTERS[1], -1)
    rails = [
        ([(9, 12, 7), (62, 9, 6), (117, 16, 8), (173, 9, 6), (225, 12, 7)], [9, 7, 9, 7, 9]),
        ([(7, 128, 6), (43, 128, 7), (92, 124, 8), (142, 133, 7), (188, 128, 7), (227, 128, 6)], [7, 8, 8, 7, 8, 7]),
        ([(7, 216, 5), (61, 220, 6), (117, 213, 7), (174, 219, 6), (227, 216, 5)], [7, 6, 8, 6, 7]),
    ]
    for points, radii in rails:
        segments.extend((np.array(a), np.array(b), ra, rb) for a, b, ra, rb in zip(points, points[1:], radii, radii[1:]))
    segments.extend([
        (np.array((43, 128, 16)), np.array((188, 193, 43)), 6.5, 6.5),
        (np.array((187, 128, 16)), np.array((42, 193, 43)), 6.5, 6.5),
    ])
    return segments


def box_sdf(x, y, z, center, half_size):
    qx, qy, qz = abs(x - center[0]) - half_size[0], abs(y - center[1]) - half_size[1], abs(z - center[2]) - half_size[2]
    outside = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2 + np.maximum(qz, 0) ** 2)
    return outside + np.minimum(np.maximum(np.maximum(qx, qy), qz), 0)


def organic_mesh():
    spacing = 2.0
    xs = np.arange(-10, FOOTPRINT + 10.01, spacing, dtype=np.float32)
    ys = np.arange(-10, FOOTPRINT + 10.01, spacing, dtype=np.float32)
    zs = np.arange(-10, 202.01, spacing, dtype=np.float32)
    x, y, z = np.meshgrid(xs, ys, zs, indexing="ij")
    field = np.full(x.shape, 1e4, dtype=np.float32)

    for start, end, r0, r1 in stand_segments():
        delta = end - start
        t = np.clip(((x - start[0]) * delta[0] + (y - start[1]) * delta[1] + (z - start[2]) * delta[2]) / np.dot(delta, delta), 0, 1)
        distance = np.sqrt((x - start[0] - t * delta[0]) ** 2 + (y - start[1] - t * delta[1]) ** 2 + (z - start[2] - t * delta[2]) ** 2)
        field = np.minimum(field, distance - (r0 + t * (r1 - r0)))

    field = gaussian_filter(field, 1.15)
    envelope = np.maximum.reduce((-x, x - FOOTPRINT, -y, y - FOOTPRINT, -z, z - 200))
    field = np.maximum(field, envelope)

    angle = np.deg2rad(12)
    local_y = 20 + np.cos(angle) * (y - 20) - np.sin(angle) * (z - 35)
    local_z = 35 + np.sin(angle) * (y - 20) + np.cos(angle) * (z - 35)
    guitar = box_sdf(x, local_y, local_z, (FOOTPRINT / 2, 20 + CRADLE_GAP / 2, 210), (FOOTPRINT, CRADLE_GAP / 2 + 4, 175))
    field = np.maximum(field, -guitar)

    image = vtk.vtkImageData()
    image.SetDimensions(field.shape)
    image.SetOrigin(float(xs[0]), float(ys[0]), float(zs[0]))
    image.SetSpacing(spacing, spacing, spacing)
    image.GetPointData().SetScalars(numpy_to_vtk(field.ravel(order="F"), deep=True))

    contour = vtk.vtkFlyingEdges3D()
    contour.SetInputData(image)
    contour.SetValue(0, 0)
    triangles = vtk.vtkTriangleFilter()
    triangles.SetInputConnection(contour.GetOutputPort())
    high_clean = vtk.vtkCleanPolyData()
    high_clean.SetInputConnection(triangles.GetOutputPort())
    high_clean.Update()
    writer = vtk.vtkSTLWriter()
    writer.SetFileName(str(OUT / "guitar-floor-stand.stl"))
    writer.SetFileTypeToBinary()
    writer.SetInputData(high_clean.GetOutput())
    assert writer.Write() == 1

    decimate = vtk.vtkDecimatePro()
    decimate.SetInputConnection(triangles.GetOutputPort())
    decimate.SetTargetReduction(0.88)
    decimate.PreserveTopologyOn()
    decimate.SplittingOff()
    clean = vtk.vtkCleanPolyData()
    clean.SetInputConnection(decimate.GetOutputPort())
    clean.Update()
    writer.SetFileName(str(OUT / "guitar-floor-stand-solid.stl"))
    writer.SetInputData(clean.GetOutput())
    assert writer.Write() == 1

    preview = Mesh.Mesh(str(OUT / "guitar-floor-stand.stl"))
    solid_mesh = Mesh.Mesh(str(OUT / "guitar-floor-stand-solid.stl"))
    assert preview.isSolid() and solid_mesh.isSolid() and preview.CountFacets > solid_mesh.CountFacets
    return preview, solid_mesh


def add_length(obj, name, value):
    obj.addProperty("App::PropertyLength", name, "Dimensions")
    setattr(obj, name, value)


def build():
    mesh, solid_mesh = organic_mesh()
    shape = Part.Shape()
    shape.makeShapeFromMesh(solid_mesh.Topology, 0.08)
    solid = Part.makeSolid(shape)
    assert solid.isValid() and len(solid.Solids) == 1

    doc = App.newDocument("GuitarFloorStand")
    params = doc.addObject("App::FeaturePython", "Parameters")
    for name, value in (("GuitarBodyThickness", BODY_THICKNESS), ("PadThickness", PAD_THICKNESS), ("CradleGap", CRADLE_GAP), ("Footprint", FOOTPRINT)):
        add_length(params, name, value)

    stand = doc.addObject("PartDesign::Feature", "Stand")
    stand.Label = "Organic Cellular 45 mm Guitar Stand"
    stand.Shape = solid
    if stand.ViewObject:
        stand.ViewObject.ShapeColor = (0.12, 0.10, 0.17)
        stand.ViewObject.Visibility = False
    preview = doc.addObject("Mesh::Feature", "OrganicPreview")
    preview.Label = "Smooth Organic Preview / Print Mesh"
    preview.Mesh = mesh
    if preview.ViewObject:
        preview.ViewObject.ShapeColor = (0.12, 0.10, 0.17)
        preview.ViewObject.DisplayMode = "Shaded"
        if hasattr(preview.ViewObject, "CreaseAngle"):
            preview.ViewObject.CreaseAngle = 180.0
    doc.recompute()
    doc.saveAs(str(OUT / "Guitar Floor Stand.FCStd"))
    step_path = OUT / "guitar-floor-stand.step"
    step_path.unlink(missing_ok=True)
    Part.export([stand], str(step_path))
    App.closeDocument(doc.Name)
    (OUT / "guitar-floor-stand-solid.stl").unlink()
    print(f"Built smooth organic stand: {mesh.CountFacets} facets")


if __name__ == "__main__":
    build()
