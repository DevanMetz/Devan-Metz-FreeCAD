"""Native Container exec contract; same CAD generator as the local HTTP bridge."""
import base64
import json
from pathlib import Path
import sys
import tempfile

from runner import generate

try:
    payload = json.loads(sys.stdin.read(16385))
    with tempfile.TemporaryDirectory(prefix="cad-job-") as temporary:
        directory = Path(temporary)
        output = generate(payload, directory).read_bytes()
        result = dict(metadata=json.loads((directory / "metadata.json").read_text()),
                      file=base64.b64encode(output).decode("ascii"))
    print(json.dumps(result, separators=(",", ":")))
except (ValueError, TypeError) as error:
    print(json.dumps({"error": str(error)}))
    sys.exit(2)
except Exception as error:
    print(json.dumps({"error": "The CAD builder could not construct this combination. Adjust the parameters."}))
    print(type(error).__name__, file=sys.stderr)
    sys.exit(3)
