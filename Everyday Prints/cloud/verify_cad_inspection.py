"""Inspect every exported STEP and kit component with the installed CAD skill."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
SAMPLES = ROOT / "review/cloud_export_samples"


def saved_evidence(target, relative, digest, command):
    """Resume only checks for the same STEP, with all requested inspection data."""
    refs_path = target.parent / "cad_refs.json"
    path = target.parent / f"cad_{command}.json"
    try:
        refs = json.loads(refs_path.read_text())
        token, = refs["tokens"]
        if (refs.get("ok") is not True or token["stepPath"] != relative or
                token["stepHash"] != digest or
                not {"entryFacts", "planes", "entryPositioning"}.issubset(token)):
            return None
        if command == "refs":
            return refs
        result = json.loads(path.read_text())
        same_step = result.get("verified_step_sha256") == digest
        # Older inspection runs predate the fingerprint field. Their validation
        # must follow the matching facts check, with no subsequent STEP edit.
        if not same_step:
            same_step = path.stat().st_mtime >= refs_path.stat().st_mtime >= target.stat().st_mtime
        if (same_step and result.get("ok") is True and result.get("failureCount") == 0 and
                result.get("entry") == token["cadPath"]):
            return result
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", type=Path,
        default=Path.home() / ".codex/skills/cad/scripts/inspect",
        help="Path to the installed CAD skill's inspect launcher.")
    parser.add_argument("--resume", action="store_true",
        help="Reuse completed checks whose STEP fingerprint still matches.")
    args = parser.parse_args()
    if not (args.inspect / "__main__.py").is_file():
        parser.error("The CAD skill inspect launcher is missing; set --inspect to its installed path.")
    cases = json.loads((ROOT / "review/cloud_export_validation.json").read_text())["cases"]
    records = []
    for case in cases:
        name = case["model"]
        directory = SAMPLES / (name + "_original" if case["original"] else name)
        targets = [directory / f"{name}.step"]
        targets += [directory / "parts" / part["model"] / f"{part['model']}.step"
                    for part in case["components"]]
        for target in targets:
            if not target.resolve().is_relative_to(SAMPLES.resolve()) or not target.is_file():
                raise ValueError(f"Missing or unsupported STEP sample: {target}")
            relative = target.relative_to(ROOT).as_posix()
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            refs_reused = False
            for command in ("refs", "validate"):
                result = saved_evidence(target, relative, digest, command) if args.resume and (command == "refs" or refs_reused) else None
                reused = result is not None
                if not reused:
                    options = ["--facts", "--planes", "--positioning"] if command == "refs" else []
                    invocation = [sys.executable, str(args.inspect), command, relative, *options]
                    process = subprocess.run(invocation, cwd=ROOT, capture_output=True, text=True, timeout=180)
                    if process.returncode:
                        raise RuntimeError(f"CAD inspection failed for {relative}: {process.stderr}\n{process.stdout}")
                    result = json.loads(process.stdout)
                    if command == "refs" and result.get("tokens", [{}])[0].get("stepHash") != digest:
                        # The inspector can return an older selector sidecar for
                        # a replaced imported STEP. Refresh its render package,
                        # then require proof that the inspected bytes are current.
                        print(f"Refreshing STEP inspection artifact: {relative}", flush=True)
                        refresh = subprocess.run([sys.executable, str(args.inspect.parent / "artifact"), relative, "--force"],
                            cwd=ROOT, capture_output=True, text=True, timeout=180)
                        if refresh.returncode:
                            raise RuntimeError(f"CAD artifact refresh failed for {relative}: {refresh.stderr}\n{refresh.stdout}")
                        process = subprocess.run(invocation, cwd=ROOT, capture_output=True, text=True, timeout=180)
                        if process.returncode:
                            raise RuntimeError(f"CAD inspection failed after refresh for {relative}: {process.stderr}\n{process.stdout}")
                        result = json.loads(process.stdout)
                if result.get("ok") is not True:
                    raise ValueError(f"CAD {command} did not pass for {relative}: {result}")
                if command == "refs":
                    token, = result["tokens"]
                    if token["stepHash"] != digest or token["stepPath"] != relative:
                        raise ValueError(f"CAD inspection fingerprint does not match the STEP: {relative}")
                    refs_reused = reused
                if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                    raise ValueError(f"STEP changed during inspection: {relative}")
                if not reused:
                    result["verified_step_sha256"] = digest
                    (target.parent / f"cad_{command}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                records.append(dict(target=relative, command=command, ok=True, step_sha256=digest, reused=reused))
        print(f"PASS STEP inspection {name} and {len(targets) - 1} kit components", flush=True)
    (ROOT / "review/cloud_export_cad_inspection.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"Verified {len(records) // 2} STEP samples with facts, planes, positioning, and solid validation.")


if __name__ == "__main__":
    main()
