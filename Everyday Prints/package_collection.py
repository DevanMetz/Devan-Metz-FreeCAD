"""Package sources, print files, documentation, and current validation evidence."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from build_collection import NAMES, ASSEMBLIES, current_view_packets

ROOT = Path(__file__).resolve().parent


def main():
    report = json.loads((ROOT/"review/design_validation.json").read_text(encoding="utf-8"))
    if set(report["models"]) != set(NAMES):
        raise RuntimeError("Run validate_designs.py for every current print file before packaging.")
    for name,digest in report["validated_files_sha256"].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Geometry changed after validation: {name}. Rebuild and validate before packaging.")
    fixed = [".gitattributes", "README.md", "CAD_BRIEF.md", "LICENSE", "NOTICE", "requirements.txt", "index.html", "INDEX.md", "make_index.py",
             "build_collection.py", "validate_designs.py", "make_preview.py",
             "package_collection.py", "export_design.py", "verify_portable_export.py", "soap_dish_common.py",
             "sanding_common.py", "sliding_box_common.py", "ruler_stop_common.py", "strap_corner_common.py",
             "divider_joint_common.py", "preview.png",
             "make_reducer_section.py", "tube_reducer_section.svg", "tube_reducer_section.png",
             "strap_clamp_preview.png", "sorting_sieve_preview.png", "divider_joint_preview.png", "THREAD_SUMMARY.md",
             "review/design_validation.json", "review/portable_export_validation.json", "review/BUILD_ENVIRONMENT.md",
             "review/VISUAL_REVIEW.md", "review/soap_dish_floor_alignment.json",
             "review/soap_dish_drain_gap.json"]
    model_files = [f"{name}{extension}" for name in NAMES
                   for extension in (".step.py", ".step", ".stl", ".3mf")]
    model_files += [f"{name}{extension}" for name in ASSEMBLIES for extension in (".step.py", ".step")]
    evidence = [f"review/{name}.{kind}.json" for name in NAMES for kind in ("facts", "validity", "exports")]
    evidence += [f"review/{name}.{kind}.json" for name in ASSEMBLIES for kind in ("facts", "validity")]
    previews = [Path(output["path"]).relative_to(ROOT).as_posix()
                for job in current_view_packets() for output in job["outputs"]]
    for prefix in ("soap_dish_contact_detail", "tube_squeezer_slot_detail"):
        matches = sorted((ROOT / "review").glob(prefix + "_*.png"))
        if not matches:
            raise FileNotFoundError(f"Missing detail snapshot: {prefix}")
        previews.append(matches[-1].relative_to(ROOT).as_posix())
    cloud = ROOT / "cloud"
    cloud_source = [path.relative_to(ROOT).as_posix()
                    for pattern in ("*.py", "*.ts", "*.json", "*.md", "*.html", ".gitignore")
                    for path in cloud.glob(pattern)]
    cloud_source += [path.relative_to(ROOT).as_posix()
                     for directory in (cloud / "web", cloud / "runtime", cloud / "src", cloud / "tests")
                     for path in directory.iterdir() if path.is_file()]
    cloud_source += ["cloud/public/favicon.svg", "cloud/public/_headers"]
    cloud_evidence = [path.relative_to(ROOT).as_posix()
                      for pattern in ("cloud_*.json", "cloud_*.png")
                      for path in (ROOT / "review").glob(pattern)]
    files = sorted(set(fixed + model_files + evidence + previews + cloud_source + cloud_evidence))
    manifest = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}
    (ROOT / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    archive = ROOT / "everyday-prints.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=9) as bundle:
        for name in files + ["SHA256SUMS.json"]:
            bundle.write(ROOT/name, "everyday-prints/" + name)
    with ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        for name, digest in manifest.items():
            assert hashlib.sha256(bundle.read("everyday-prints/"+name)).hexdigest() == digest
    print(f"Packaged {len(NAMES)} models, {len(files)+1} files; verified archive CRCs and SHA-256 hashes.")


if __name__ == "__main__":
    main()
