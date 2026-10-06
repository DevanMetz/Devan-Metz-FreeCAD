"""Small internal-only HTTP bridge to isolated, time-limited CAD job processes."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
BUILD_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def respond(self, status, body, content_type="application/json", extra=None):
        if isinstance(body, dict):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Runtime-Version", (ROOT / "version.txt").read_text().strip())
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self.respond(200, {"ok": True})
        else:
            self.respond(404, {"error": "Not found."})

    def do_POST(self):
        if self.path != "/generate":
            return self.respond(404, {"error": "Not found."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.respond(400, {"error": "Invalid content length."})
        if not 0 < length <= 16384:
            self.close_connection = True
            return self.respond(413, {"error": "Parameter request is too large."})
        body = self.rfile.read(length)
        if not BUILD_LOCK.acquire(blocking=False):
            return self.respond(503, {"error": "The CAD builder is busy. Try again shortly."}, extra={"Retry-After": "5"})
        status, content_type, extra = 200, "application/json", {}
        try:
            with tempfile.TemporaryDirectory(prefix="cad-job-") as temporary:
                directory = Path(temporary)
                result = subprocess.run([sys.executable, str(ROOT / "runner.py"), str(directory)],
                                        input=body, capture_output=True, timeout=90, cwd=ROOT)
                if result.returncode:
                    try:
                        error = json.loads(result.stdout.decode().splitlines()[-1])
                    except (ValueError, IndexError):
                        error = {"error": "This combination could not be built. Adjust the parameters."}
                    status, response_body = 422, error
                else:
                    metadata = json.loads((directory / "metadata.json").read_text())
                    cad = metadata["format"] == "cad"
                    response_body = (directory / ("model.zip" if cad else "model.stl")).read_bytes()
                    content_type = "application/zip" if cad else "model/stl"
                    extra = {
                        "X-Model-Metadata": quote(json.dumps(metadata, separators=(",", ":"))),
                        "Content-Disposition": f'attachment; filename="{metadata["model"]}-custom.{"zip" if cad else "stl"}"',
                    }
        except subprocess.TimeoutExpired:
            status, response_body = 422, {"error": "This build exceeded 90 seconds. Reduce repeated features or simplify the parameters."}
        except Exception:
            status, response_body = 500, {"error": "The CAD builder could not finish the request. Try again."}
        finally:
            BUILD_LOCK.release()
        # Release the compute slot before the response becomes observable to the next caller.
        self.respond(status, response_body, content_type, extra)

    def log_message(self, format, *args):
        print(format % args, flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1]) if len(sys.argv) > 1 else 8080), Handler).serve_forever()
