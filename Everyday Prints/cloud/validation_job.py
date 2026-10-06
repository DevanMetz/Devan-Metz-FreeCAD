"""Use the real native Container job contract for verification without HTTP."""
import base64
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote

RUNTIME = Path(__file__).resolve().parent.parent.parent / ".cad-cache/cloud-runtime"
SCRATCH = RUNTIME.parent / "verification-jobs"


def native_request(payload):
    SCRATCH.mkdir(exist_ok=True)
    # Lib3MF cannot create files in Windows AppContainer temporary directories.
    # Keep test scratch space in the workspace while running the same job source.
    launcher = "import runpy,sys,tempfile; tempfile.tempdir=sys.argv[1]; runpy.run_path(sys.argv[2],run_name='__main__')"
    try:
        result = subprocess.run([sys.executable, "-c", launcher, str(SCRATCH), str(RUNTIME / "run_job.py")],
            cwd=RUNTIME, input=json.dumps(payload), capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return 422, b'{"error":"This build exceeded 90 seconds."}', {"Content-Type": "application/json"}
    try:
        response = json.loads(result.stdout.splitlines()[-1])
    except (ValueError, IndexError) as error:
        raise RuntimeError("Native CAD job returned no readable result: " + result.stderr[-500:]) from error
    if result.returncode or "error" in response:
        return 422, json.dumps(response).encode(), {"Content-Type": "application/json"}
    metadata = response["metadata"]
    cad = metadata["format"] == "cad"
    return 200, base64.b64decode(response["file"]), {
        "Content-Type": "application/zip" if cad else "model/stl",
        "X-Model-Metadata": quote(json.dumps(metadata)),
        "Content-Disposition": f'attachment; filename="{metadata["model"]}-custom.{"zip" if cad else "stl"}"',
    }
