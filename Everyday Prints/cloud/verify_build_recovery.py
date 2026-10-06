"""Verify stopping stalled builds, deadlines, retries, and late responses.

Run verify_exports.py first for real CAD fixtures. --offline serves the compiled
app locally. Virtual time tests the 15-minute deadline without a real wait.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

from playwright.sync_api import sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from browser_transfers import DEFERRED_BODY
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = "--offline" in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5178")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT.parent / ".cad-cache/browsers"))
WAIT_MS = 15 * 60 * 1000


def main():
    original = fixture("parts_tray_original")
    custom = fixture("parts_tray")
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1080}, accept_downloads=True)
        context.set_default_timeout(20000)
        if OFFLINE:
            attach_assets(context)

        def setup(page):
            page.clock.install()
            # The original HTTP response completes. Its delayed header/body
            # promise deliberately ignores AbortSignal to expose late races.
            page.add_init_script(DEFERRED_BODY + """window.holdStage = null;
              window.pendingTransfers = [];
              const originalFetch = window.fetch;
              window.fetch = async (...args) => {
                const response = await originalFetch(...args);
                if (!String(args[0]).includes('/api/generate') || !window.holdStage) return response;
                const bytes = await response.arrayBuffer();
                const hold = () => new Promise(resolve => window.pendingTransfers.push(resolve));
                response.json = async () => JSON.parse(new TextDecoder().decode(bytes));
                if (window.holdStage === 'headers') {
                  window.deferFileBody(response, bytes, async () => {});
                  await hold();
                } else window.deferFileBody(response, bytes, hold);
                return response;
              };""")
            jobs = []

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
            page.wait_for_function("() => document.querySelector('#preview-loading').hidden")
            return jobs

        def build(page):
            page.locator('[data-parameter="length"]').fill("180.5")
            page.locator("#rebuild").click()

        def live(page):
            build(page)
            page.wait_for_function("() => !document.querySelector('#download-cad').disabled")

        def hold(page, stage="body"):
            page.evaluate("stage => { window.holdStage = stage; }", stage)

        def pending(page, count=1):
            page.wait_for_function("count => window.pendingTransfers.length === count", arg=count)
            assert page.locator("#stop-build").is_visible()

        def release(page, index=0):
            page.evaluate("index => window.pendingTransfers[index]()", index)
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")

        def stopped(page):
            assert page.locator("#stop-build").is_hidden()
            assert page.locator("#rebuild").is_enabled()
            assert "service may still finish" in page.locator("#form-message").inner_text()

        def cancel_preview_retry_late_transfer(page):
            setup(page)
            hold(page)
            build(page)
            pending(page)
            page.locator("#stop-build").click()
            stopped(page)
            assert page.locator('[data-parameter="length"]').input_value() == "180.5"
            assert page.locator("#model-size").inner_text() == "150 × 100 × 24"
            assert page.locator("#download").is_disabled()
            page.locator('[data-parameter="length"]').fill("150")
            with page.expect_download() as event:
                page.locator("#download").click()
            assert Path(event.value.path()).read_bytes() == (CLOUD / "public/models/parts_tray.stl").read_bytes()
            build(page)
            pending(page, 2)
            release(page)
            assert page.locator("#rebuild").is_disabled(), "Old cleanup unlocked a newer build"
            assert page.locator("#stop-build").is_visible()
            assert page.locator("#model-size").inner_text() == "150 × 100 × 24"
            release(page, 1)
            page.wait_for_function("() => !document.querySelector('#download').disabled")
            assert page.locator("#model-size").inner_text() == "180.5 × 100 × 24"
            assert page.locator("#stop-build").is_hidden()

        def cancel_cad_retry_late_transfer(page):
            jobs = setup(page)
            live(page)
            downloads = []
            page.on("download", lambda item: downloads.append(item))
            hold(page)
            page.locator("#download-cad").click()
            pending(page)
            page.locator("#stop-build").click()
            stopped(page)
            assert not page.locator("#download").is_disabled()
            assert not page.locator("#download-cad").is_disabled()
            page.locator("#download-cad").click()
            pending(page, 2)
            release(page)
            assert not downloads, "Stopped CAD transfer triggered a download"
            assert page.locator("#rebuild").is_disabled()
            with page.expect_download() as event:
                release(page, 1)
            assert Path(event.value.path()).read_bytes() == custom[0]
            assert jobs == ["stl", "cad", "cad"]
            assert page.locator("#stop-build").is_hidden()

        def preview_timeout_headers(page):
            setup(page)
            hold(page, "headers")
            build(page)
            pending(page)
            page.clock.fast_forward(WAIT_MS + 1)
            stopped(page)
            assert "15 minutes" in page.locator("#form-message").inner_text()
            assert "error" in page.locator("#form-message").get_attribute("class")
            assert page.locator('[data-parameter="length"]').input_value() == "180.5"
            assert page.locator("#download").is_disabled()
            release(page)
            assert page.locator("#model-size").inner_text() == "150 × 100 × 24"
            assert "15 minutes" in page.locator("#form-message").inner_text()

        def cad_timeout_body_retry(page):
            setup(page)
            live(page)
            hold(page)
            downloads = []
            page.on("download", lambda item: downloads.append(item))
            page.locator("#download-cad").click()
            pending(page)
            page.clock.fast_forward(WAIT_MS + 1)
            stopped(page)
            assert not page.locator("#download").is_disabled()
            assert not page.locator("#download-cad").is_disabled()
            release(page)
            assert not downloads
            assert "15 minutes" in page.locator("#form-message").inner_text()
            hold(page, None)
            with page.expect_download() as event:
                page.locator("#download-cad").click()
            assert Path(event.value.path()).read_bytes() == custom[0]

        def cancel_initial_cad_refresh(page):
            jobs = setup(page)
            downloads = []
            page.on("download", lambda item: downloads.append(item))
            hold(page)
            page.locator("#download-cad").click()
            pending(page)
            page.locator("#stop-build").click()
            stopped(page)
            release(page)
            assert jobs == ["stl"], "Cancelled refresh continued into a CAD export"
            assert not downloads
            assert not page.locator("#download").is_disabled()

        def previous_deadline_cannot_stop_retry(page):
            setup(page)
            hold(page)
            build(page)
            pending(page)
            page.locator("#stop-build").click()
            page.clock.fast_forward(WAIT_MS // 2)
            build(page)
            pending(page, 2)
            page.clock.fast_forward(WAIT_MS // 2 + 1)
            assert page.locator("#rebuild").is_disabled(), "A cancelled request's deadline stopped its retry"
            assert page.locator("#stop-build").is_visible()
            release(page, 1)
            page.wait_for_function("() => !document.querySelector('#download').disabled")
            release(page)
            assert page.locator("#model-size").inner_text() == "180.5 × 100 × 24"

        def navigation_hides_stop_control(page):
            setup(page)
            hold(page)
            build(page)
            pending(page)
            page.locator("#close-editor").click()
            page.wait_for_function("() => !new URL(location.href).searchParams.has('model')")
            page.locator('[data-model="cable_comb"]').click()
            page.wait_for_function("() => !document.querySelector('#download').disabled")
            assert page.locator("#stop-build").is_hidden()
            title = page.locator("#model-title").inner_text()
            release(page)
            page.clock.fast_forward(WAIT_MS + 1)
            assert page.locator("#model-title").inner_text() == title
            assert page.locator("#rebuild").is_enabled()
            assert "15 minutes" not in page.locator("#form-message").inner_text()

        def cancel_without_verified_preview(page):
            page.route("**/models/parts_tray.stl", lambda route: route.abort())
            setup(page)
            assert page.locator("#download").is_disabled()
            hold(page)
            build(page)
            pending(page)
            page.locator('[data-parameter="length"]').fill("")
            page.locator("#stop-build").click()
            stopped(page)
            assert page.locator('[data-parameter="length"]').input_value() == ""
            assert page.locator("#download").is_disabled()
            assert page.locator("#download-cad").is_disabled()
            assert page.locator("#mesh-status").inner_text() == "Fix invalid dimensions"
            assert page.locator('[data-parameter="length"]').get_attribute("aria-invalid") == "true"
            assert page.locator("#error-length").is_visible()
            assert page.locator("#fallback-image").is_visible()
            assert "unavailable" in page.locator(".viewer-help").inner_text()
            release(page)
            hold(page, None)
            live(page)
            assert page.locator("#stop-build").is_hidden()

        def mobile_keyboard_stop_control(page):
            page.set_viewport_size({"width": 390, "height": 844})
            jobs = setup(page)
            hold(page)
            build(page)
            pending(page)
            control = page.locator("#stop-build")
            control.scroll_into_view_if_needed()
            rect = control.bounding_box()
            assert 0 <= rect["x"] and rect["x"] + rect["width"] <= 390, rect
            assert 0 <= rect["y"] and rect["y"] + rect["height"] <= 844, rect
            assert control.evaluate("element => { const r=element.getBoundingClientRect(); return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2) === element; }")
            page.screenshot(path=str(ROOT / "review/cloud_build_recovery_mobile.png"))
            control.focus()
            page.keyboard.press("Enter")
            stopped(page)
            assert jobs == ["stl"], "Stop control submitted another build"
            release(page)

        def late_service_error_keeps_stop_message(page):
            setup(page)
            page.route("**/api/generate", lambda route: route.fulfill(status=503, json={"error": "Late service failure"}))
            hold(page, "headers")
            build(page)
            pending(page)
            page.locator("#stop-build").click()
            stopped(page)
            release(page)
            assert "Stopped waiting" in page.locator("#form-message").inner_text()
            assert "Late service failure" not in page.locator("#form-message").inner_text()

        for test in (cancel_preview_retry_late_transfer, cancel_cad_retry_late_transfer,
                     preview_timeout_headers, cad_timeout_body_retry,
                     cancel_initial_cad_refresh, previous_deadline_cannot_stop_retry,
                     navigation_hides_stop_control, cancel_without_verified_preview,
                     mobile_keyboard_stop_control, late_service_error_keeps_stop_message):
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
                page.close()
        context.close()
        browser.close()
    report = dict(endpoint=BASE, passed=passed, failures=failures, wait_deadline_ms=WAIT_MS,
        fixture_archive_sha256=hashlib.sha256(custom[0]).hexdigest(),
        transport="compiled assets through Playwright routes; real CAD fixtures" if OFFLINE else "local HTTP bridge; real CAD fixtures")
    (ROOT / "review/cloud_build_recovery_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert not failures, report


if __name__ == "__main__":
    main()
