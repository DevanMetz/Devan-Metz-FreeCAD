"""Verify file confirmation independently of original-preview transfers."""
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

from playwright.sync_api import expect, sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from browser_transfers import DEFERRED_BODY
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = "--offline" in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5178")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT.parent / ".cad-cache/browsers"))

HOLD = DEFERRED_BODY + """window.originalMode = '';
window.releaseOriginal = null;
const realFetch = window.fetch;
window.fetch = async (...args) => {
  const response = await realFetch(...args);
  if (!window.originalMode || !String(args[0]).endsWith('/models/cable_comb.stl')) return response;
  const mode = window.originalMode;
  const wait = () => new Promise(resolve => { window.releaseOriginal = resolve; });
  if (mode === 'body') {
    const bytes = await response.arrayBuffer();
    window.deferFileBody(response, bytes, wait);
  } else {
    await wait();
    if (mode === 'failure') throw new Error('The model preview could not be loaded.');
  }
  return response;
};"""


def main():
    archive, metadata, mesh = fixture("cable_comb")
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1080}, accept_downloads=True)
        context.set_default_timeout(20000)
        if OFFLINE:
            attach_assets(context)

        def setup(page, mode=""):
            page.add_init_script(HOLD)
            jobs = []

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload)
                assert payload["model"] == metadata["model"]
                assert payload["parameters"] == metadata["parameters"]
                if payload.get("format") == "cad":
                    route.fulfill(body=archive, headers=headers(metadata))
                else:
                    value = {**metadata, "format": "stl", "file_sha256": metadata["mesh_sha256"]}
                    route.fulfill(body=mesh, headers=headers(value, "model/stl"))

            page.route("**/api/generate", generate)
            page.goto(BASE)
            page.locator('[data-model="parts_tray"]').click()
            page.wait_for_function("() => !document.querySelector('#download-cad').disabled")
            page.locator(".saved-dimensions summary").click()
            page.evaluate("mode => window.originalMode = mode", mode)
            return jobs

        def load(page, record=metadata):
            text = record if isinstance(record, str) else json.dumps(record)
            with page.expect_file_chooser() as event:
                page.locator("#load-dimensions").click()
            event.value.set_files({"name": "parameters.json", "mimeType": "application/json", "buffer": text.encode("utf-8")})

        def confirmed(page):
            expect(page.locator("#form-message")).to_contain_text("Saved dimensions loaded.")
            expect(page.locator("#parameter-fields input").first).to_be_focused()
            expect(page.locator("#dimensions-error")).to_be_hidden()

        def waiting(page):
            page.wait_for_function("() => typeof window.releaseOriginal === 'function'")
            assert page.locator("#preview-loading").is_visible()
            assert page.locator("#download").is_disabled() and page.locator("#download-cad").is_disabled()

        def release(page):
            page.evaluate("window.releaseOriginal()")
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")

        def settled(page):
            expect(page.locator("#preview-loading")).to_be_hidden()

        def download(page, button):
            with page.expect_download() as event:
                page.locator("#" + button).click()
            return Path(event.value.path()).read_bytes()

        def failed_original_keeps_file_confirmation_and_mobile_focus(page):
            page.set_viewport_size({"width": 390, "height": 844})
            jobs = setup(page)
            page.route("**/models/cable_comb.stl", lambda route: route.fulfill(status=503, body="Controlled unavailable preview"))
            record = {"model": "cable_comb", "parameters": {"depth": 40}, "units": "mm"}
            load(page, record)
            confirmed(page)
            settled(page)
            expect(page.locator("#form-message")).to_contain_text("preview could not be loaded")
            assert page.locator("#param-depth").input_value() == "40"
            assert page.locator("#download").is_disabled() and page.locator("#download-cad").is_disabled()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator("#form-message").scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / "review/cloud_dimensions_preview_mobile.png"))
            saved = json.loads(download(page, "save-dimensions"))
            assert saved["model"] == "cable_comb" and saved["parameters"]["depth"] == 40
            assert page.evaluate("JSON.parse(new URL(location.href).searchParams.get('p')).depth") == 40
            assert not jobs

        def corrupt_original_keeps_accepted_dimensions(page):
            jobs = setup(page)
            page.route("**/models/cable_comb.stl", lambda route: route.fulfill(body=b"corrupt mesh", content_type="model/stl"))
            load(page)
            confirmed(page)
            settled(page)
            expect(page.locator("#form-message")).to_contain_text("could not be verified")
            assert page.locator("#param-cable_diameters").input_value() == "2, 3.5, 9"
            assert page.locator("#download").is_disabled() and not jobs

        def delayed_headers_confirm_before_preview_and_save_exact_values(page):
            jobs = setup(page, "headers")
            load(page)
            confirmed(page)
            waiting(page)
            assert page.locator("#load-dimensions").is_enabled() and page.locator("#rebuild").is_enabled()
            assert json.loads(download(page, "save-dimensions"))["parameters"] == metadata["parameters"]
            release(page)
            settled(page)
            expect(page.locator("#form-message")).to_contain_text("Saved dimensions loaded.")
            assert "Shared dimensions" not in page.locator("#form-message").inner_text()
            assert page.locator("#download").is_disabled() and not jobs

        def delayed_matching_body_enables_only_verified_original(page):
            jobs = setup(page, "body")
            load(page, {"model": "cable_comb", "parameters": {}, "units": "mm"})
            confirmed(page)
            waiting(page)
            release(page)
            settled(page)
            expect(page.locator("#form-message")).to_have_text("Saved dimensions match the verified preview.")
            expect(page.locator("#download")).to_be_enabled()
            data = download(page, "download")
            original = (CLOUD / ".cloudflare/output/v0/workers/default/assets/models/cable_comb.stl").read_bytes()
            assert data == original and not jobs

        def unavailable_original_builds_and_downloads_exact_saved_model(page):
            jobs = setup(page)
            page.route("**/models/cable_comb.stl", lambda route: route.fulfill(status=404, body="Controlled missing original"))
            load(page)
            confirmed(page)
            settled(page)
            page.locator("#rebuild").click()
            expect(page.locator("#download-cad")).to_be_enabled()
            assert download(page, "download") == mesh
            assert download(page, "download-cad") == archive
            assert len(jobs) == 2

        def late_original_failure_keeps_new_field_error(page):
            jobs = setup(page, "failure")
            load(page)
            confirmed(page)
            waiting(page)
            field = page.locator("#param-depth")
            field.fill("")
            before = page.locator("#form-message").inner_text()
            release(page)
            settled(page)
            expect(page.locator("#form-message")).to_have_text(before)
            expect(field).to_have_attribute("aria-invalid", "true")
            expect(page.locator("#mesh-status")).to_have_text("Fix invalid dimensions")
            assert page.locator("#download").is_disabled() and not jobs

        def late_verified_original_keeps_rejected_file_error(page):
            jobs = setup(page, "body")
            load(page, {"model": "cable_comb", "parameters": {}, "units": "mm"})
            confirmed(page)
            waiting(page)
            load(page, "{")
            expect(page.locator("#dimensions-error")).to_contain_text("not valid JSON")
            before = page.locator("#form-message").inner_text()
            release(page)
            settled(page)
            expect(page.locator("#form-message")).to_have_text(before)
            expect(page.locator("#dimensions-error")).to_contain_text("not valid JSON")
            expect(page.locator("#download")).to_be_enabled()
            assert not jobs

        def newer_matching_file_reflects_late_verified_preview(page):
            jobs = setup(page, "body")
            load(page)
            confirmed(page)
            waiting(page)
            load(page, {"model": "cable_comb", "parameters": {}, "units": "mm"})
            confirmed(page)
            release(page)
            settled(page)
            expect(page.locator("#form-message")).to_have_text("Saved dimensions match the verified preview.")
            expect(page.locator("#download")).to_be_enabled()
            assert not jobs

        def reset_reflects_late_verified_original_without_old_file_feedback(page):
            jobs = setup(page, "body")
            load(page)
            confirmed(page)
            waiting(page)
            page.locator("#reset-parameters").click()
            release(page)
            settled(page)
            expect(page.locator("#form-message")).to_have_text("Preview matches these parameters.")
            expect(page.locator("#download")).to_be_enabled()
            assert not jobs

        def building_saved_model_supersedes_late_original_failure(page):
            jobs = setup(page, "failure")
            load(page)
            confirmed(page)
            waiting(page)
            page.locator("#rebuild").click()
            expect(page.locator("#download-cad")).to_be_enabled()
            before = page.locator("#form-message").inner_text()
            release(page)
            expect(page.locator("#form-message")).to_have_text(before)
            assert download(page, "download") == mesh
            assert download(page, "download-cad") == archive
            assert len(jobs) == 2

        def switching_models_discards_late_original_failure(page):
            jobs = setup(page, "failure")
            load(page)
            confirmed(page)
            waiting(page)
            page.locator("#close-editor").click()
            page.locator('[data-model="phone_stand"]').click()
            expect(page.locator("#download-cad")).to_be_enabled()
            before = page.locator("#form-message").inner_text()
            release(page)
            expect(page.locator("#form-message")).to_have_text(before)
            assert page.evaluate("new URL(location.href).searchParams.get('model')") == "phone_stand"
            assert not jobs

        def second_model_file_keeps_its_values_and_focus(page):
            jobs = setup(page, "failure")
            load(page)
            confirmed(page)
            waiting(page)
            load(page, {"model": "parts_tray", "parameters": {"length": 180.55}, "units": "mm"})
            confirmed(page)
            settled(page)
            before = page.locator("#form-message").inner_text()
            release(page)
            expect(page.locator("#form-message")).to_have_text(before)
            expect(page.locator("#param-length")).to_be_focused()
            assert page.locator("#param-length").input_value() == "180.55"
            assert page.evaluate("new URL(location.href).searchParams.get('model')") == "parts_tray"
            assert not jobs

        tests = (failed_original_keeps_file_confirmation_and_mobile_focus,
                 corrupt_original_keeps_accepted_dimensions,
                 delayed_headers_confirm_before_preview_and_save_exact_values,
                 delayed_matching_body_enables_only_verified_original,
                 unavailable_original_builds_and_downloads_exact_saved_model,
                 late_original_failure_keeps_new_field_error,
                 late_verified_original_keeps_rejected_file_error,
                 newer_matching_file_reflects_late_verified_preview,
                 reset_reflects_late_verified_original_without_old_file_feedback,
                 building_saved_model_supersedes_late_original_failure,
                 switching_models_discards_late_original_failure,
                 second_model_file_keeps_its_values_and_focus)
        for test in tests:
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
    report = dict(endpoint=BASE, passed=passed, failures=failures,
                  fixtures_sha256={"cable_comb": hashlib.sha256(archive).hexdigest()},
                  transport="compiled assets and real CAD fixtures with controlled original-preview transfers" if OFFLINE else "local HTTP bridge and real CAD fixtures")
    (ROOT / "review/cloud_dimensions_preview_validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    assert not failures, report


if __name__ == "__main__":
    main()
