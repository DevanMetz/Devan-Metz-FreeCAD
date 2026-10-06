"""Build explicit CAD sources and preserve machine-readable review evidence.

Requires the CAD skill runtime; set CAD_SKILL_DIR if it is installed elsewhere.
Run this file with the Python environment containing requirements.txt.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
CAD = Path(os.environ.get("CAD_SKILL_DIR", Path.home() / ".codex/skills/cad")) / "scripts"
NAMES = ["parts_tray", "cable_comb", "divider_foot", "divider_fit_coupon",
         "phone_stand", "corner_square", "handle_marking_jig", "tube_squeezer",
         "soap_dish_tray", "soap_dish_insert", "label_stand", "paint_pyramid",
         "cable_winder", "hex_bit_rack", "hex_bit_fit_coupon", "sanding_block",
         "sanding_wedge", "cable_grommet", "radius_template", "center_finder",
         "brush_rest", "utility_peg", "sliding_box", "sliding_lid",
         "sliding_fit_channel", "sliding_fit_slider", "round_stock_cradle",
         "tie_anchor", "workshop_funnel", "fold_clip", "cord_clip", "hand_knob", "slotted_shim",
         "marking_saddle", "roll_adapter", "bookend", "corner_cable_guide",
         "workshop_scoop", "plant_marker", "ruler_stop", "ruler_wedge",
         "tube_reducer", "socket_fit_ring", "strap_corner", "sorting_sieve", "sieve_aperture_coupon",
         "divider_joint"]
ASSEMBLIES = ["soap_dish_assembly", "sanding_assembly", "sliding_box_assembly", "ruler_stop_assembly", "strap_clamp_assembly",
              "divider_joint_assembly"]


def current_view_packets():
    """Resolve review images locally, including after moving or unzipping the collection."""
    jobs = []
    for name in NAMES + ASSEMBLIES:
        outputs = []
        for view in ("iso", "opposite", "top", "front"):
            matches = sorted((ROOT / "review").glob(f"{name}_{view}_*.png"))
            if not matches:
                raise FileNotFoundError(f"Missing {view} snapshot for {name}; rebuild with --snapshots.")
            outputs.append({"path": str(matches[-1])})
        jobs.append({"input": str(ROOT / f"{name}.step.py"), "outputs": outputs})
    return jobs


def run(tool, *args):
    process = subprocess.run([sys.executable, str(CAD / tool), *map(str, args)],
                             cwd=ROOT, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    if process.returncode:
        raise RuntimeError(f"{tool} failed:\n{process.stdout}\n{process.stderr}")
    return process.stdout


def save_snapshot_catalog(output):
    """Retain current views of untouched designs when rebuilding a subset."""
    path = ROOT / "review" / "snapshot_catalog.json"
    existing = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {"jobs": []}
    current = {Path(job["input"]).name: job for job in existing["jobs"]}
    current.update({Path(job["input"]).name: job for job in json.loads(output)["jobs"]})
    ordered = [current[f"{name}.step.py"] for name in NAMES+ASSEMBLIES if f"{name}.step.py" in current]
    path.write_text(json.dumps({"jobs": ordered}, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="Explicit model basenames; default is the collection.")
    parser.add_argument("--snapshots", action="store_true", help="Render four review views per selected model.")
    args = parser.parse_args()
    names = args.names or NAMES+ASSEMBLIES
    if any(n not in NAMES+ASSEMBLIES for n in names):
        parser.error("Unknown model name.")
    review = ROOT / "review"
    review.mkdir(exist_ok=True)
    print("Generating STEP and CAD render packages...", flush=True)
    result = run("gen", *[f"{n}.step.py" for n in names], "--write", "--json")
    (review / "generation.jsonl").write_text(result, encoding="utf-8")
    for name in names:
        target = f"{name}.step.py"
        facts = run("inspect", "refs", target, "--facts", "--planes", "--positioning")
        (review / f"{name}.facts.json").write_text(facts, encoding="utf-8")
        soundness = run("inspect", "validate", target)
        (review / f"{name}.validity.json").write_text(soundness, encoding="utf-8")
        if name in NAMES:
            result = run("export", target, "--stl", "--3mf", "--mesh-tolerance", ".005",
                         "--mesh-angular-tolerance", ".05", "--json")
            (review / f"{name}.exports.json").write_text(result, encoding="utf-8")
        print(f"Validated and exported {name}", flush=True)
    if args.snapshots:
        jobs = []
        for name in names:
            views = {"iso": "iso", "opposite": {"direction": [-1, 1, -.8]},
                     "top": "top", "front": "front"}
            jobs.append({"input": str(ROOT / f"{name}.step.py"), "mode": "view",
                         "outputs": [{"path": str(review / f"{name}_{view}.png"),
                                      "camera": camera} for view, camera in views.items()],
                         "render": {"width": 1000, "height": 750,
                                    "viewLabels": True, "padding": .13}})
        job_file = review / "snapshot_jobs.json"
        job_file.write_text(json.dumps(jobs, indent=2), encoding="utf-8")
        print("Rendering CAD review views...", flush=True)
        output = run("snapshot", "--job", job_file.as_posix(), "--json")
        (review / "snapshot_results.json").write_text(output, encoding="utf-8")
        save_snapshot_catalog(output)
    print("Selected models built. Run validate_designs.py for feature and parameter checks.", flush=True)


if __name__ == "__main__":
    main()
