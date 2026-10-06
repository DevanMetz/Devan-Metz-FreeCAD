"""Verify that optional 3D loading never blocks verified mesh/CAD downloads.

Real exported CAD fixtures and compiled viewer code are replayed with controlled
delays and failures. Run verify_exports.py first; use --offline without a server.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
from urllib.parse import urlparse
from zipfile import ZipFile

from playwright.sync_api import sync_playwright
from browser_assets import ASSETS, OFFLINE_BASE, attach_assets
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = "--offline" in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5178")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT.parent / ".cad-cache/browsers"))


def main():
    original, custom = fixture("parts_tray_original"), fixture("parts_tray")
    passed, failures = [], []
    pending_by_page = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1080}, accept_downloads=True)
        context.set_default_timeout(20000)
        if OFFLINE:
            attach_assets(context)

        def deliver(route):
            body = (ASSETS / urlparse(route.request.url).path.lstrip("/")).read_bytes() if OFFLINE else route.fetch().body()
            # Observe module evaluation separately from creating its renderer.
            route.fulfill(body=body + b"\nwindow.viewerModuleLoaded = true;", content_type="text/javascript")

        def setup(page, hold_viewer=True):
            waiting, modules, jobs = [], [], []
            pending_by_page[page] = waiting

            def module(route):
                modules.append(route.request.url)
                if hold_viewer:
                    waiting.append(route)
                else:
                    deliver(route)

            page.route("**/assets/viewer-*.js" if OFFLINE else "**/web/viewer.js*", module)

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload.get("format", "stl"))
                body, metadata, mesh = custom if payload["parameters"]["length"] == 180.5 else original
                if payload.get("format") == "cad":
                    route.fulfill(body=body, headers=headers(metadata))
                else:
                    metadata = {**metadata, "format": "stl", "file_sha256": metadata["mesh_sha256"]}
                    route.fulfill(body=mesh, headers=headers(metadata, "model/stl"))

            page.route("**/api/generate", generate)
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            page.locator('[data-model="parts_tray"]').click()
            return waiting, modules, jobs

        def ready(page):
            page.wait_for_function("() => !document.querySelector('#download').disabled")

        def viewer_ready(page):
            page.wait_for_function("() => document.querySelector('#viewer').getAttribute('aria-busy') === 'false' && document.querySelector('#viewer canvas')")
            assert page.locator("#viewer canvas").count() == 1
            assert page.locator("#fallback-image").is_hidden()
            assert page.locator(".view-tools").is_visible()

        def fallback(page, loading=False):
            assert page.locator("#fallback-image").is_visible()
            badge = page.locator("#preview-badge").text_content()
            assert badge == "Original catalog image", badge
            assert page.locator(".view-tools").is_hidden()
            assert page.locator("#viewer").get_attribute("aria-busy") == str(loading).lower()
            assert "original model" in page.locator("#download-note").inner_text()

        def download(page, button="download"):
            with page.expect_download() as event:
                page.locator("#" + button).click()
            return Path(event.value.path()).read_bytes()

        def open_custom(page):
            ready(page)
            page.locator('[data-parameter="length"]').fill("180.5")
            page.locator("#rebuild").click()
            ready(page)

        def release(page, waiting):
            assert len(waiting) == 1, "Model changes started duplicate viewer downloads"
            deliver(waiting.pop())
            page.wait_for_function("() => window.viewerModuleLoaded === true")
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")

        def held_original_download_and_export(page):
            waiting, _, jobs = setup(page)
            ready(page)
            fallback(page, loading=True)
            assert download(page) == (CLOUD / "public/models/parts_tray.stl").read_bytes()
            assert download(page, "download-cad") == original[0]
            assert jobs == ["stl", "cad"]
            fallback(page, loading=True)
            release(page, waiting)
            viewer_ready(page)
            assert download(page) == original[2]
            assert download(page, "download-cad") == original[0]
            assert jobs == ["stl", "cad"], "Late 3D initialization discarded the verified CAD cache"

        def held_custom_files_and_late_upgrade(page):
            waiting, _, jobs = setup(page)
            open_custom(page)
            fallback(page, loading=True)
            assert page.locator("#rebuild").is_enabled()
            assert page.locator("#stop-build").is_hidden()
            assert page.locator("#model-size").inner_text() == "180.5 × 100 × 24"
            assert download(page) == custom[2]
            with page.expect_download() as event:
                page.locator("#download-cad").click()
            with ZipFile(event.value.path()) as archive:
                assert archive.read("parts_tray.stl") == custom[2]
                assert json.loads(archive.read("parameters.json"))["parameters"]["length"] == 180.5
            assert jobs == ["stl", "cad"]
            page.screenshot(path=str(ROOT / "review/cloud_viewer_loading_fallback.png"))
            release(page, waiting)
            viewer_ready(page)
            assert page.locator("#model-size").inner_text() == "180.5 × 100 × 24"
            assert "exact mesh" in page.locator("#download-note").inner_text()
            assert download(page) == custom[2]

        def close_before_module_initialization(page):
            waiting, _, _ = setup(page)
            ready(page)
            page.locator("#close-editor").click()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            release(page, waiting)
            assert page.locator("#viewer canvas").count() == 0, "A closed editor created an unused renderer"
            page.locator('[data-model="cable_comb"]').click()
            ready(page)
            viewer_ready(page)
            assert page.locator("#model-size").inner_text() == "59 × 32 × 4"

        def switch_models_during_load(page):
            waiting, _, _ = setup(page)
            ready(page)
            page.locator("#close-editor").click()
            page.wait_for_function("() => !new URL(location.href).searchParams.has('model')")
            page.locator('[data-model="cable_comb"]').click()
            ready(page)
            assert download(page) == (CLOUD / "public/models/cable_comb.stl").read_bytes()
            release(page, waiting)
            viewer_ready(page)
            assert page.locator("#model-size").inner_text() == "59 × 32 × 4"
            assert page.locator("#mesh-status").inner_text() == "Original dimensions"
            assert download(page) == (CLOUD / "public/models/cable_comb.stl").read_bytes()

        def failed_module_keeps_downloads(page):
            waiting, modules, _ = setup(page)
            open_custom(page)
            assert len(waiting) == 1
            waiting.pop().abort()
            page.wait_for_function("() => document.querySelector('#viewer').getAttribute('aria-busy') === 'false'")
            fallback(page)
            assert "unavailable" in page.locator(".viewer-help").inner_text()
            assert download(page) == custom[2]
            assert download(page, "download-cad") == custom[0]
            page.locator("#close-editor").click()
            page.wait_for_function("() => !new URL(location.href).searchParams.has('model')")
            page.locator('[data-model="cable_comb"]').click()
            ready(page)
            page.wait_for_function("() => document.querySelector('#viewer').getAttribute('aria-busy') === 'false'")
            fallback(page)
            assert len(modules) == 1

        def no_webgl_keeps_downloads(page):
            page.add_init_script("""const original = HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                return type.startsWith('webgl') ? null : original.call(this, type, ...args);
              };""")
            setup(page, hold_viewer=False)
            open_custom(page)
            page.wait_for_function("() => document.querySelector('#viewer').getAttribute('aria-busy') === 'false'")
            fallback(page)
            assert page.locator("#viewer canvas").count() == 0
            assert download(page) == custom[2]
            assert download(page, "download-cad") == custom[0]

        def failed_renderer_keeps_verified_files(page):
            _, modules, _ = setup(page, hold_viewer=False)
            ready(page)
            viewer_ready(page)
            page.evaluate("""async url => {
              const { ModelViewer } = await import(url);
              const load = ModelViewer.prototype.load, dispose = ModelViewer.prototype.dispose;
              ModelViewer.prototype.load = function(...args) {
                if (window.failViewerLoad) throw new Error('Controlled rendering failure');
                return load.apply(this, args);
              };
              ModelViewer.prototype.dispose = function() {
                window.viewerDisposals = (window.viewerDisposals || 0) + 1;
                return dispose.call(this);
              };
              window.failViewerLoad = true;
            }""", modules[0])
            open_custom(page)
            fallback(page)
            assert page.evaluate("window.viewerDisposals") == 1
            assert page.locator("#viewer canvas").count() == 0
            assert download(page) == custom[2]
            assert download(page, "download-cad") == custom[0]

        def corrupt_mesh_stays_blocked(page):
            mesh = bytearray((CLOUD / "public/models/parts_tray.stl").read_bytes())
            mesh[0] ^= 1
            page.route("**/models/parts_tray.stl", lambda route: route.fulfill(body=bytes(mesh), content_type="model/stl"))
            _, modules, _ = setup(page)
            page.wait_for_function("() => document.querySelector('#form-message').classList.contains('error')")
            assert page.locator("#download").is_disabled()
            assert page.locator("#download-cad").is_disabled()
            assert page.locator("#viewer").get_attribute("aria-busy") == "false"
            assert not modules, "Unverified mesh started the optional viewer"

        for test in (held_original_download_and_export, held_custom_files_and_late_upgrade,
                     close_before_module_initialization, switch_models_during_load,
                     failed_module_keeps_downloads, no_webgl_keeps_downloads,
                     failed_renderer_keeps_verified_files, corrupt_mesh_stays_blocked):
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                test(page)
                assert not errors, errors
                passed.append(test.__name__)
                print(f"PASS {test.__name__}", flush=True)
            except Exception as error:
                failures.append(dict(test=test.__name__, error=str(error), traceback=traceback.format_exc(), browser_errors=errors))
                print(f"FAIL {test.__name__}: {failures[-1]['traceback']}", flush=True)
            finally:
                for route in pending_by_page.pop(page, []):
                    route.abort()
                page.close()
        context.close()
        browser.close()
    report = dict(endpoint=BASE, passed=passed, failures=failures,
        fixture_archive_sha256=hashlib.sha256(custom[0]).hexdigest(),
        transport="compiled assets and real CAD fixtures with controlled viewer loading" if OFFLINE else "local HTTP bridge with controlled viewer loading")
    (ROOT / "review/cloud_viewer_loading_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert not failures, report


if __name__ == "__main__":
    main()
