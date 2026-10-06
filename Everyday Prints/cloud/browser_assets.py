"""Serve the compiled app through Playwright routes with real native CAD jobs.

This verifies the production frontend without an HTTP listener. Browser requests
to the reserved .test origin are fulfilled locally before reaching the network.
"""
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlparse

from validation_job import native_request

ASSETS = Path(__file__).resolve().parent / ".cloudflare/output/v0/workers/default/assets"
OFFLINE_BASE = "https://everyday-prints.test"


def attach_assets(context):
    assert (ASSETS / "catalog.json").is_file(), "Run cf build before offline browser checks."

    def serve(route):
        path = unquote(urlparse(route.request.url).path).lstrip("/")
        if path == "api/generate":
            status, body, headers = native_request(route.request.post_data_json)
            route.fulfill(status=status, body=body, headers=headers)
            return
        asset = (ASSETS / (path or "index.html")).resolve()
        if not asset.is_relative_to(ASSETS.resolve()) or not asset.is_file():
            route.fulfill(status=404, body="Not found")
            return
        mime = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
        route.fulfill(body=asset.read_bytes(), headers={"Content-Type": mime})

    context.route(OFFLINE_BASE + "/**", serve)
