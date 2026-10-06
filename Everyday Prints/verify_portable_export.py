"""Exercise the public exporter from a copied source-only directory."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import trimesh
from build123d import import_step

ROOT = Path(__file__).resolve().parent


def main():
    results = []
    with tempfile.TemporaryDirectory(prefix="everyday-prints-portable-") as scratch:
        copied = Path(scratch)/"sources"
        copied.mkdir()
        for path in ROOT.glob("*.py"):
            shutil.copy2(path,copied/path.name)
        cases = [
            ("label_stand",["slot_gap=1.2","lean_angle=20"],(50,24,12),1),
            ("cable_grommet",["hole_diameter=50","opening=0"],(58,58,18.4),1),
            ("radius_template",["radii=[4,8,12,16]"],(80,80,3),1),
            ("sanding_assembly",[],(100,50,34.5833333333),3),
            ("sliding_lid",["width=70","side_clearance=0.4"],(123.2,64.4,5.4),1),
            ("sliding_box_assembly",["open_distance=0"],(126,80,33.1),2),
            ("ruler_stop",["ruler_width=20","ruler_thickness=0.8"],(28.4,10,24),1),
            ("ruler_wedge",["ruler_width=20","ruler_thickness=0.8"],(35,18,7),1),
            ("ruler_stop_assembly",["ruler_width=20","ruler_thickness=0.8","reference_length=160"],(160,28.4,10.8),3),
            ("tube_reducer",["large_diameter=40","small_diameter=25","large_clearance=0.6"],(45.4,45.4,72),1),
            ("socket_fit_ring",["tube_diameter=25","clearance=0.6"],(30.4,30.4,8),1),
            ("strap_corner",["strap_width=20","leg_length=25"],(33,33,28.5),1),
            ("strap_clamp_assembly",["strap_width=20","leg_length=25","frame_width=140","frame_depth=100","frame_height=25"],(156,116,28.5),6),
            ("sorting_sieve",["hole_diameter=5","pitch=8"],(135,90,18),1),
            ("sieve_aperture_coupon",["hole_diameter=5","offsets=[-0.3,0,0.3]"],(40,18,2.4),1),
            ("divider_joint",["ports=[0,90,180]"],(40.2,24.2,18),1),
            ("divider_joint_assembly",["ports=[0,90]","reference_length=60","reference_height=35"],(68.2,68.2,37.4),3),
        ]
        for name,settings,bounds,count in cases:
            output = copied/"output"/name
            command = [sys.executable,str(copied/"export_design.py"),name,"--output-dir",str(output)]
            for setting in settings:
                command.extend(["--set",setting])
            process = subprocess.run(command,cwd=scratch,capture_output=True,text=True)
            assert process.returncode == 0, process.stdout+process.stderr
            record = json.loads((output/"parameters.json").read_text(encoding="utf-8"))
            assert record["solid_count"] == count
            assert np.allclose(record["bounds_mm"],bounds,atol=1e-5,rtol=0), (name,record['bounds_mm'],bounds)
            step = import_step(output/f"{name}.step")
            assert step.is_valid and len(step.solids()) == count
            assert np.allclose(tuple(step.bounding_box().size),bounds,atol=1e-5,rtol=0)
            assert abs(step.volume/record["volume_mm3"]-1) < 1e-6
            if count == 1:
                for extension in ("stl","3mf"):
                    mesh = trimesh.load(output/f"{name}.{extension}",force="mesh")
                    assert mesh.is_watertight and mesh.is_winding_consistent and mesh.body_count == 1
                    assert np.allclose(mesh.extents,bounds,atol=.01,rtol=0)
                    assert abs(mesh.volume/record["volume_mm3"]-1) < .001
            else:
                assert not (output/f"{name}.stl").exists()
                assert not (output/f"{name}.3mf").exists()
            results.append(dict(model=name,overrides=settings,formats=record["formats"],
                                step_round_trip=True,mesh_checks_passed=count==1))
            print(f"PASS portable export: {name}",flush=True)
        # A rejected key must not silently generate a default part.
        invalid = copied/"rejected"
        process = subprocess.run([sys.executable,str(copied/"export_design.py"),"label_stand",
                                  "--set","slot_gapp=2","--output-dir",str(invalid)],
                                 cwd=scratch,capture_output=True,text=True)
        assert process.returncode != 0 and "Unknown parameter" in process.stderr and not invalid.exists()
    report = dict(copied_sources_only=True,cad_skill_invoked=False,cases=results,
                  unknown_parameter_rejected=True,physical_print_tested=False)
    (ROOT/"review"/"portable_export_validation.json").write_text(json.dumps(report,indent=2),encoding="utf-8")


if __name__ == "__main__":
    main()
