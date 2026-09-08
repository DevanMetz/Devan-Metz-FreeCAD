"""Deterministic CAD regression checks. Run with FreeCAD's bundled Python."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import FreeCAD as App
import Mesh
import Part

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("quiver", ROOT.parent / "lift_x_quiver_generator.py")
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)


def check():
    chassis = q.production_solid(q.handed(q.make_chassis()), "chassis")
    dock_local = q.production_solid(q.handed(q.make_bow_dock()), "dock")
    # Catch a label-only LH model: the bow-contact plane must actually mirror.
    if q.HAND == "LH":
        assert abs(dock_local.BoundBox.YMax-30) < 1e-6
        assert abs(chassis.BoundBox.YMin+43) < 1e-6
    else:
        assert abs(dock_local.BoundBox.YMin+30) < 1e-6
    dock = q.translated(dock_local, App.Vector(0, 0, q.MOUNT_Z))
    foam = q.translated(q.handed(q.make_foam_reference()), App.Vector(0, 0, q.HOOD_Z))
    q.validate_functional_geometry(chassis, dock, foam)
    report = {"hand": q.HAND, "units": "mm", "bow_fit": "UNVERIFIED: sight attachment and OEM blocks not measured", "parts": {}}
    for name, shape in (("quiver_chassis_petg", chassis), ("bow_dock_petg", dock_local), ("mount_pattern_gauge", q.make_fit_gauge())):
        q.validate(name, shape)
        path = ROOT / "STEP" / (name + ".step")
        roundtrip = Part.read(str(path))
        q.validate(name + " round trip", roundtrip)
        error = abs(shape.Volume-roundtrip.Volume)
        assert error < 0.01, (name, error)
        b, rb = q.manufacturing_shape(name, shape).BoundBox, roundtrip.BoundBox
        dims = [b.XLength, b.YLength, b.ZLength]
        assert max(abs(a-c) for a,c in zip(dims,[rb.XLength,rb.YLength,rb.ZLength])) < 1e-5
        assert max(dims) <= 252
        mesh = Mesh.Mesh(str(ROOT / "STL" / (name+".stl")))
        assert mesh.isSolid() and mesh.hasNonManifolds() is False
        report["parts"][name] = {"bbox_mm": dims, "volume_cm3": shape.Volume/1000,
            "valid_solids": len(shape.Solids), "step_roundtrip_volume_error_mm3": error,
            "stl_closed_manifold": True, "step_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        downward = [f for f in mesh.Facets if f.Normal.z < -math.sqrt(.5)-1e-5 and max(p[2] for p in f.Points) > .4]
        report["parts"][name]["area_below_45deg_excluding_bed_mm2"] = sum(f.Area for f in downward)
    report["printability_note"] = "Mesh overhang screen, not a sliced toolpath. Local bridges/ledge supports remain; not support-free."
    report["main_basket_flare_minimum_angle_above_horizontal_deg"] = math.degrees(math.atan2(54, (44+52-(24-2))/math.sqrt(2)))

    # The top ring must remain one annulus at and between all taper stations.
    hood = q.handed(q.make_hood())
    rings = []
    for z in (53.9, 54.1, 55, 57, 58.9, 59.1, 59.8):
        slab = Part.makeBox(150, 120, 0.05, App.Vector(-75, -60, z))
        ring = hood.common(slab)
        assert len(ring.Solids) == 1 and ring.isValid(), (z, len(ring.Solids))
        topfaces = [f for f in ring.Faces if f.BoundBox.ZLength < 1e-6]
        assert len(topfaces) == 2 and all(len(f.Wires)==2 for f in topfaces), z
        rings.append({"local_z": z, "one_continuous_annulus": True, "area_mm2": ring.Volume/.05})
    report["basket_rim_sections"] = rings

    # Actual driver/washer envelopes with assembled chassis, not just bare flange.
    access = []
    for z in ((q.DOCK_HEIGHT-q.AMO_HOLE_SPACING)/2, (q.DOCK_HEIGHT+q.AMO_HOLE_SPACING)/2):
        driver = Part.makeCylinder(6, 35, App.Vector(q.MOUNT_HOLE_X,-23.99,z), App.Vector(0,1,0))
        driver = q.translated(q.handed(driver), App.Vector(0,0,q.MOUNT_Z))
        interference = driver.common(chassis.fuse(dock)).Volume
        assert interference < .05, ("driver", z, interference)
        access.append({"assembly_z": z+q.MOUNT_Z, "driver_diameter_mm": 12, "collision_mm3": interference})
    report["mounting_screw_access"] = access
    report["mount_pattern"] = {"pitch_mm": q.AMO_HOLE_SPACING, "nominal_clearance_diameter_mm": q.AMO_SCREW_CLEARANCE,
                              "lower_slot_travel_mm": q.MOUNT_SLOT_TRAVEL, "expected_thread_only_if_verified": "10-24 UNC"}

    # Separate rigid guide motion from intentional contact with the flexure.
    latch_zone = Part.makeBox(16.4, 12, 81, App.Vector(-8.2,-16,-4))
    rigid_local = dock_local.cut(q.handed(latch_zone))
    rigid = q.translated(rigid_local, App.Vector(0,0,q.MOUNT_Z))
    sweep = []
    for lift in range(0, 85):
        raised = q.translated(chassis, App.Vector(0,0,lift))
        hard = raised.common(rigid).Volume
        latch_contact = raised.common(dock).Volume
        sweep.append({"lift_mm": lift, "rigid_collision_mm3": hard, "undeformed_latch_contact_mm3": latch_contact})
    report["slide_sweep"] = sweep
    report["maximum_rigid_slide_interference_mm3"] = max(s["rigid_collision_mm3"] for s in sweep)
    report["maximum_undeformed_latch_contact_mm3"] = max(s["undeformed_latch_contact_mm3"] for s in sweep)
    report["slide_note"] = "Rigid guide sweep only; contact with undeflected spring tooth is intentional. Fatigue and release force not qualified."
    (ROOT / "geometry_checks.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("slide_sweep", "basket_rim_sections")}, indent=2))
    assert report["maximum_rigid_slide_interference_mm3"] < .05, "Rigid slide path blocked"


if __name__ == "__main__":
    check()
