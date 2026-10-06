"""Exercise real CAD generation over the internal HTTP contract, not stub geometry."""
import hashlib
import io
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.parse import unquote
from urllib.request import Request, urlopen
from validation_job import native_request

CLOUD = Path(__file__).resolve().parent
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8086/generate"


def request(payload):
    if BASE == "--native":
        return native_request(payload)
    body = json.dumps(payload).encode()
    try:
        response = urlopen(Request(BASE, data=body, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}), timeout=600)
    except HTTPError as error:
        return error.code, error.read(), error.headers
    with response:
        return response.status, response.read(), response.headers


def check(payload):
    import trimesh
    started = time.monotonic()
    status, mesh, headers = request(payload)
    if status != 200:
        raise AssertionError(f"{payload['model']}: HTTP {status}: {mesh.decode()}")
    metadata = json.loads(unquote(headers["X-Model-Metadata"]))
    assert hashlib.sha256(mesh).hexdigest() == metadata["mesh_sha256"]
    loaded = trimesh.load(io.BytesIO(mesh), file_type="stl", force="mesh")
    assert loaded.is_watertight and loaded.is_volume, payload["model"]
    if metadata["printable"]:
        assert abs(loaded.bounds[0, 2]) < 1e-5
        assert metadata["solid_count"] == 1
    record = dict(model=payload["model"], parameters=metadata["parameters"], bounds_mm=metadata["bounds_mm"],
                  mesh_sha256=metadata["mesh_sha256"], mesh_bytes=len(mesh),
                  triangles=len(loaded.faces), seconds=round(time.monotonic()-started, 2))
    print(f"PASS {record['model']} {record['seconds']}s", flush=True)
    return record


def main():
    models = json.loads((CLOUD / "public/catalog.json").read_text())["models"]
    tests = [dict(model=model["name"], parameters={}) for model in models if model["kind"] == "print"]
    tests += [
        dict(model="parts_tray", parameters=dict(length=180, height=30, columns=4, rows=3)),
        dict(model="cable_comb", parameters=dict(cable_diameters=[2, 3, 5, 9])),
        dict(model="divider_joint", parameters=dict(ports=[0, 90, 180])),
        dict(model="sliding_box", parameters=dict(length=160)),
        dict(model="sliding_lid", parameters=dict(length=160)),
        dict(model="soap_dish_assembly", parameters={}),
        dict(model="divider_joint_assembly", parameters=dict(ports=[0, 90, 180])),
    ]
    records = [check(payload) for payload in tests]
    failures = [
        {"model": "../../evil", "parameters": {}},
        {"model": "parts_tray", "parameters": {"__proto__": {}}},
        {"model": "parts_tray", "parameters": {"length": "180"}},
        {"model": "parts_tray", "parameters": {"columns": 2.5}},
        {"model": "parts_tray", "parameters": {"length": 1001}},
        {"model": "cable_comb", "parameters": {"cable_diameters": [2]*17}},
        {"model": "parts_tray", "parameters": {"pocket_radius": 0.1}},
    ]
    for payload in failures:
        status, body, _ = request(payload)
        assert 400 <= status < 500, (payload, status, body)
        assert "error" in json.loads(body)
    report = dict(endpoint=BASE, passed=len(records), rejected=len(failures), models=records)
    path = CLOUD.parent / "review/cloud_runtime_validation.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Verified {len(records)} mesh jobs and {len(failures)} rejected inputs.", flush=True)


if __name__ == "__main__":
    main()
