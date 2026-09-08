"""Check current export provenance and package only the current, reviewed files."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import trimesh

ROOT = Path(__file__).resolve().parent


def main():
    checks = json.loads((ROOT/"geometry_checks.json").read_text())
    harness = json.loads((ROOT/"harness_checks.json").read_text())
    snapshots = json.loads((ROOT/"snapshot_results.json").read_text())
    assert snapshots["ok"] and checks["maximum_rigid_slide_interference_mm3"] < .05
    for name, part in checks["parts"].items():
        step = ROOT/"STEP"/(name+".step")
        digest = hashlib.sha256(step.read_bytes()).hexdigest()
        assert digest == part["step_sha256"], (name, "stale geometry checks")
        assert digest == harness[name]["facts"]["tokens"][0]["stepHash"], (name, "stale harness")
        assert harness[name]["validity"]["ok"]
        scene = trimesh.load(str(ROOT/"3MF"/(name+".3mf")), force="scene")
        assert all(mesh.is_watertight and mesh.is_winding_consistent for mesh in scene.geometry.values())
        assert max(abs(a-b) for a,b in zip(scene.extents,part["bbox_mm"])) < .01, (name,scene.extents)
    assert harness["LiftX_Quiver_Assembly"]["validity"]["occurrenceCount"] == 2
    files = [ROOT/n for n in ("README.md", "CAD_BRIEF.md", "REVIEW.md", "LiftX_Quiver_LH.FCStd", "geometry_checks.json",
             "harness_checks.json", "snapshot_results.json", "check_design.py", "harness_review.py", "snapshot_jobs.json", "package_release.py")]
    for folder, extension in (("STEP","*.step"),("STL","*.stl"),("3MF","*.3mf")):
        files.extend(sorted((ROOT/folder).glob(extension)))
    for job in snapshots["jobs"]:
        assert job["ok"]
        files.extend(Path(output["path"]) for output in job["outputs"])
    archive = ROOT/"LiftX_LH_MountV2_Print_Pack.zip"
    with ZipFile(archive,"w",ZIP_DEFLATED) as pack:
        for path in files:
            assert path.is_file(), path
            pack.write(path, "Quiver/LiftX/MountV2/"+path.relative_to(ROOT).as_posix())
        pack.write(ROOT.parent/"lift_x_quiver_generator.py", "Quiver/LiftX/lift_x_quiver_generator.py")
    with ZipFile(archive) as pack:
        assert pack.testzip() is None
    print(f"PASS: 3MF extents/manifold checks; current STEP hashes; packaged {len(files)+1} files: {archive}")


if __name__ == "__main__":
    main()
