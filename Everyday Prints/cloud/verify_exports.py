"""Check real CAD downloads and rebuilding their saved dimensions offline."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import unquote
from urllib.request import Request, urlopen
from zipfile import ZipFile
from validation_job import native_request

import numpy as np
import trimesh
from build123d import import_step

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8086/generate"
SAMPLES = ROOT / "review/cloud_export_samples"


def request(payload):
    if BASE == "--native":
        return native_request(payload)
    try:
        response = urlopen(Request(BASE, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}), timeout=120)
    except HTTPError as error:
        return error.code, error.read(), error.headers
    with response:
        return response.status, response.read(), response.headers


def check(payload, original=False):
    started = time.monotonic()
    name = payload["model"]
    status, mesh, headers = request(payload)
    assert status == 200, (name, status, mesh[:400])
    preview = json.loads(unquote(headers["X-Model-Metadata"]))
    preview_hash = hashlib.sha256(mesh).hexdigest()
    assert preview_hash == preview["mesh_sha256"]
    if original:
        catalog = json.loads((CLOUD / "public/catalog.json").read_text())
        item = next(m for m in catalog["models"] if m["name"] == name)
        original_mesh = trimesh.load(CLOUD / "public" / item["mesh"].lstrip("/"), force="mesh")
        np.testing.assert_allclose(original_mesh.extents, preview["bounds_mm"], atol=.01, rtol=0)
        assert abs(original_mesh.volume - preview["volume_mm3"]) / preview["volume_mm3"] < .001
    status, body, headers = request({**payload, "format": "cad"})
    assert status == 200 and headers["Content-Type"] == "application/zip", (name, status, body[:400])
    metadata = json.loads(unquote(headers["X-Model-Metadata"]))
    assert metadata["parameters"] == preview["parameters"]
    assert metadata["mesh_sha256"] == preview_hash, "Export tessellation differs from preview"
    assert hashlib.sha256(body).hexdigest() == metadata["file_sha256"]
    directory = SAMPLES / (name + ("_original" if original else ""))
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "download.zip").write_bytes(body)
    with ZipFile(io.BytesIO(body)) as archive:
        assert archive.testzip() is None
        assert len(set(archive.namelist())) == len(archive.namelist())
        for filename in archive.namelist():
            path = PurePosixPath(filename)
            assert not path.is_absolute() and ".." not in path.parts
        hashes = json.loads(archive.read("SHA256SUMS.json"))
        assert set(hashes) == set(archive.namelist()) - {"SHA256SUMS.json"}
        for filename, digest in hashes.items():
            assert hashlib.sha256(archive.read(filename)).hexdigest() == digest
        saved = json.loads(archive.read("parameters.json"))
        assert saved["parameters"] == metadata["parameters"]
        for filename in (name + ".step", "rebuild.py", "LICENSE", "NOTICE", "requirements.txt", "sources/" + name + ".step.py"):
            assert filename in hashes
        if metadata["printable"]:
            assert archive.read(name + ".stl") == mesh
            stl = trimesh.load(io.BytesIO(mesh), file_type="stl", force="mesh")
            threemf = trimesh.load(io.BytesIO(archive.read(name + ".3mf")), file_type="3mf", force="mesh")
            for loaded in (stl, threemf):
                assert loaded.is_watertight and loaded.is_volume
                assert abs(loaded.bounds[0, 2]) < 1e-5
                np.testing.assert_allclose(loaded.extents, metadata["bounds_mm"], atol=.01, rtol=0)
                assert abs(loaded.volume - metadata["volume_mm3"]) / metadata["volume_mm3"] < .001
            assert len(stl.faces) == len(threemf.faces)
            with ZipFile(io.BytesIO(archive.read(name + ".3mf"))) as container:
                model_xml = container.read(next(p for p in container.namelist() if p.endswith(".model")))
                assert b'unit="millimeter"' in model_xml
        else:
            assert name + ".stl" not in hashes and name + ".3mf" not in hashes
            assert metadata["kit"] and saved["kit"] == metadata["kit"]
        archive.extractall(directory)
    solid = import_step(directory / f"{name}.step")
    assert solid.is_valid and len(solid.solids()) == metadata["solid_count"]
    assert all(s.volume > 0 for s in solid.solids())
    np.testing.assert_allclose(list(solid.bounding_box().size), metadata["bounds_mm"], atol=.001, rtol=0)
    assert abs(solid.volume - metadata["volume_mm3"]) / metadata["volume_mm3"] < 1e-7
    components = []
    for part in metadata.get("kit", []):
        model = part["model"]
        folder = directory / "parts" / model
        applied = json.loads((folder / "parameters.json").read_text())
        assert applied["quantity"] == part["quantity"] and applied["role"] == part["role"]
        assert applied["printable"] and applied["solid_count"] == 1
        for key in applied["parameters"].keys() & metadata["parameters"].keys():
            assert applied["parameters"][key] == metadata["parameters"][key]
        component = import_step(folder / f"{model}.step")
        assert component.is_valid and len(component.solids()) == 1 and abs(component.bounding_box().min.Z) < 1e-6
        for extension in ("stl", "3mf"):
            loaded = trimesh.load(folder / f"{model}.{extension}", force="mesh")
            assert loaded.is_watertight and loaded.is_volume and loaded.body_count == 1
            assert abs(loaded.bounds[0, 2]) < 1e-5
            np.testing.assert_allclose(loaded.extents, list(component.bounding_box().size), atol=.01, rtol=0)
            assert abs(loaded.volume - component.volume) / component.volume < .001
        component_mesh = (folder / f"{model}.stl").read_bytes()
        assert hashlib.sha256(component_mesh).hexdigest() == applied["mesh_sha256"]
        # Multiplicity is checked against independently exported assembly solids,
        # including rotated parts; volumes are invariant under those placements.
        matches = sum(abs(s.volume - component.volume) / component.volume < 1e-7 for s in solid.solids())
        assert matches == (part["quantity"] if part["role"] == "component" else 0), (name, model, matches)
        components.append(dict(model=model, quantity=part["quantity"], role=part["role"], parameters=applied["parameters"],
            bounds_mm=applied["bounds_mm"], mesh_sha256=applied["mesh_sha256"], assembly_volume_matches=matches))
    rebuilt = subprocess.run([sys.executable, str(directory / "rebuild.py")], cwd=directory,
        capture_output=True, text=True, timeout=90)
    assert rebuilt.returncode == 0, rebuilt.stderr
    rebuilt_metadata = json.loads((directory / "rebuilt/parameters.json").read_text())
    assert rebuilt_metadata["kit"] == metadata.get("kit", [])
    rebuilt_solid = import_step(directory / "rebuilt" / f"{name}.step")
    assert rebuilt_solid.is_valid and len(rebuilt_solid.solids()) == len(solid.solids())
    np.testing.assert_allclose(list(rebuilt_solid.bounding_box().size), metadata["bounds_mm"], atol=.001, rtol=0)
    assert abs(rebuilt_solid.volume - solid.volume) / solid.volume < 1e-7
    if metadata["printable"]:
        assert (directory / "rebuilt" / f"{name}.stl").read_bytes() == mesh
    else:
        assert not list((directory / "rebuilt").glob("*.stl"))
        assert not list((directory / "rebuilt").glob("*.3mf"))
        for part in metadata["kit"]:
            model = part["model"]
            rebuilt_part = json.loads((directory / "rebuilt/parts" / model / "parameters.json").read_text())
            assert rebuilt_part["quantity"] == part["quantity"] and rebuilt_part["role"] == part["role"]
            assert (directory / "rebuilt/parts" / model / f"{model}.stl").read_bytes() == (directory / "parts" / model / f"{model}.stl").read_bytes()
    record = dict(model=name, original=original, parameters=metadata["parameters"],
        printable=metadata["printable"], bounds_mm=metadata["bounds_mm"],
        solid_count=metadata["solid_count"], mesh_sha256=preview_hash,
        archive_sha256=metadata["file_sha256"], archive_bytes=len(body),
        files=list(hashes), components=components, seconds=round(time.monotonic() - started, 2))
    print(f"PASS {name}{' original' if original else ''}: STEP, transfer, sources and rebuild", flush=True)
    return record


def main():
    cases = [
        ({"model": "parts_tray", "parameters": {}}, True),
        ({"model": "parts_tray", "parameters": {"length": 180.5}}, False),
        ({"model": "cable_comb", "parameters": {"cable_diameters": [2, 3.5, 9]}}, False),
        ({"model": "sliding_lid", "parameters": {"length": 160}}, False),
        ({"model": "soap_dish_assembly", "parameters": {"length": 160}}, False),
        ({"model": "divider_joint_assembly", "parameters": {"ports": [0, 90, 180]}}, False),
        ({"model": "sanding_assembly", "parameters": {"length": 120}}, False),
        ({"model": "sliding_box_assembly", "parameters": {"length": 160}}, False),
        ({"model": "ruler_stop_assembly", "parameters": {"ruler_width": 20}}, False),
        ({"model": "strap_clamp_assembly", "parameters": {"strap_width": 20, "leg_length": 25}}, False),
    ]
    records = [check(payload, original) for payload, original in cases]
    rejected = [{"model": "parts_tray", "format": value} for value in [None, "step", [], 1]]
    rejected += [{"model": "parts_tray", "format": "cad", "parameters": {"columns": 2.5}},
                 {"model": "parts_tray", "format": "cad", "parameters": {"pocket_radius": .1}}]
    for payload in rejected:
        status, body, _ = request(payload)
        assert 400 <= status < 500 and "error" in json.loads(body), (payload, status)
    # Verify the native Container entry point, which wraps the same files in JSON.
    runtime = ROOT.parent / ".cad-cache/cloud-runtime"
    status, native_file, native_headers = native_request({"model": "parts_tray", "parameters": {"length": 180.5}, "format": "cad"})
    assert status == 200
    native_metadata = json.loads(unquote(native_headers["X-Model-Metadata"]))
    assert native_metadata["format"] == "cad"
    assert native_metadata["mesh_sha256"] == records[1]["mesh_sha256"]
    assert hashlib.sha256(native_file).hexdigest() == native_metadata["file_sha256"]
    # Prove saved parameters are used after extracting the source, not just defaults.
    directory = SAMPLES / "parts_tray"
    path = directory / "parameters.json"
    saved = json.loads(path.read_text())
    changed = {**saved, "parameters": {**saved["parameters"], "length": 190.5}}
    path.write_text(json.dumps(changed), encoding="utf-8")
    try:
        process = subprocess.run([sys.executable, str(directory / "rebuild.py")], cwd=directory,
            capture_output=True, text=True, timeout=90)
        assert process.returncode == 0, process.stderr
        updated = import_step(directory / "rebuilt/parts_tray.step")
        assert abs(updated.bounding_box().size.X - 190.5) < .001
    finally:
        path.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    # Editing the saved assembly dimensions updates every corresponding print.
    kit_directory = SAMPLES / "soap_dish_assembly"
    path = kit_directory / "parameters.json"
    saved = json.loads(path.read_text())
    changed = {**saved, "parameters": {**saved["parameters"], "length": 170}}
    path.write_text(json.dumps(changed), encoding="utf-8")
    try:
        process = subprocess.run([sys.executable, str(kit_directory / "rebuild.py")], cwd=kit_directory,
            capture_output=True, text=True, timeout=90)
        assert process.returncode == 0, process.stderr
        rebuilt_metadata = json.loads((kit_directory / "rebuilt/parameters.json").read_text())
        assert rebuilt_metadata["kit"] == saved["kit"]
        for part in saved["kit"]:
            applied = json.loads((kit_directory / "rebuilt/parts" / part["model"] / "parameters.json").read_text())
            assert applied["quantity"] == part["quantity"] and applied["role"] == part["role"]
            assert applied["parameters"]["length"] == 170
            part_shape = import_step(kit_directory / "rebuilt/parts" / part["model"] / (part["model"] + ".step"))
            np.testing.assert_allclose(list(part_shape.bounding_box().size), applied["bounds_mm"], atol=.001, rtol=0)
    finally:
        path.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    report = dict(endpoint=BASE, runtime_version=(runtime / "version.txt").read_text(),
        passed=len(records), rejected=len(rejected), native_contract=True,
        edited_parameters_rebuilt=True, edited_assembly_components_rebuilt=True,
        rebuilt_inventory_preserved=True, cases=records,
        snapshot_note="Pure export workflow: canonical geometry unchanged; existing model snapshots remain applicable.")
    (ROOT / "review/cloud_export_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Verified {len(records)} CAD downloads, {len(rejected)} rejected inputs and native job output.", flush=True)


if __name__ == "__main__":
    main()
