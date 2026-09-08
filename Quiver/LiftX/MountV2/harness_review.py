"""Review explicit neutral STEP exports using the installed text-to-CAD harness."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[2]
SCRIPTS = Path.home() / ".codex/skills/cad/scripts"


def run(*args):
    result = subprocess.run([sys.executable, str(SCRIPTS/args[0]), *args[1:]],
                            cwd=WORKSPACE, capture_output=True, text=True, encoding="utf-8")
    print(" ".join(args), flush=True)
    if result.stderr:
        print(result.stderr, flush=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return json.loads(result.stdout)


def main():
    (ROOT/"3MF").mkdir(exist_ok=True)
    (ROOT/"Images").mkdir(exist_ok=True)
    reports = {}
    names = ("quiver_chassis_petg", "bow_dock_petg", "mount_pattern_gauge", "LiftX_Quiver_Assembly")
    for name in names:
        step = f"Quiver/LiftX/MountV2/STEP/{name}.step"
        run("artifact", step, "--force")
        facts = run("inspect", "refs", step, "--facts", "--planes", "--positioning")
        validity = run("inspect", "validate", step)
        assert facts["ok"] and validity["ok"], name
        reports[name] = {"facts": facts, "validity": validity}
        if name != "LiftX_Quiver_Assembly":
            reports[name]["mesh_export"] = run("export", step, "--3mf", str(ROOT/"3MF"/(name+".3mf")), "--json")
    (ROOT/"harness_checks.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    snapshots = run("snapshot", "--job", "Quiver/LiftX/MountV2/snapshot_jobs.json", "--json")
    (ROOT/"snapshot_results.json").write_text(json.dumps(snapshots, indent=2), encoding="utf-8")
    print(json.dumps(snapshots, indent=2))


if __name__ == "__main__":
    main()
