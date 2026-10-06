"""A small production smoke check, keeping well below the public build rate limit."""
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

import verify_runtime as verify

BASE = sys.argv[1].rstrip("/")
verify.BASE = BASE + "/api/generate"

with urlopen(Request(BASE + "/api/health", headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as response:
    health = json.load(response)
assert health["ok"] and health["models"] == 53

records = [verify.check(payload) for payload in [
    dict(model="parts_tray", parameters=dict(length=180, height=30, columns=4, rows=3)),
    dict(model="cable_comb", parameters=dict(cable_diameters=[2, 3, 5, 9])),
    dict(model="divider_joint", parameters=dict(ports=[0, 90, 180])),
]]
invalid = [
    {"model": "../../unknown", "parameters": {}},
    {"model": "parts_tray", "parameters": {"length": "180"}},
    {"model": "parts_tray", "parameters": {"columns": 2.5}},
    {"model": "parts_tray", "parameters": {"__proto__": {}}},
    {"model": "parts_tray", "parameters": {"length": 1001}},
]
for payload in invalid:
    status, body, _ = verify.request(payload)
    assert status == 400 and "error" in json.loads(body), (status, body)

report = dict(endpoint=BASE, health=health, geometry_checks=records, rejected_inputs=len(invalid))
(Path(__file__).resolve().parent.parent / "review/cloud_live_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("Live Worker passed: custom dimensions, numeric lists, selectable topology, mesh validity/hashes, rejected inputs.")
