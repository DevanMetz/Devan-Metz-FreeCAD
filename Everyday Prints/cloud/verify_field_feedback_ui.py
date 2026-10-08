"""Verify visible, associated errors without losing verified files or CAD progress."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import traceback

from playwright.sync_api import sync_playwright, expect
from browser_assets import OFFLINE_BASE, attach_assets
from browser_transfers import DEFERRED_BODY
from verify_dimensions_ui import FILES
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = "--offline" in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5178")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT.parent / ".cad-cache/browsers"))

CLIPBOARD = """window.copies=[];
Object.defineProperty(navigator, 'clipboard', { value: {
  writeText: text => { window.copies.push(text); return Promise.resolve(); }
} });"""

HOLD = DEFERRED_BODY + """window.holdBuild=false; window.releaseBuild=null;
const actualFetch=window.fetch;
window.fetch=async (...args) => {
  const response=await actualFetch(...args);
  if (!window.holdBuild || !String(args[0]).includes('/api/generate')) return response;
  const bytes=await response.arrayBuffer();
  window.deferFileBody(response, bytes, () => new Promise(resolve => { window.releaseBuild=resolve; }));
  return response;
};"""


def main():
    _, metadata, mesh = fixture("parts_tray")
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1080}, accept_downloads=True)
        context.set_default_timeout(20000)
        if OFFLINE:
            attach_assets(context)

        def flush(page):
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")

        def setup(page, model="parts_tray", mobile=False):
            page.add_init_script(FILES + CLIPBOARD + HOLD)
            if mobile:
                page.set_viewport_size({"width": 390, "height": 844})
            jobs, downloads = [], []

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload)
                if payload["model"] == metadata["model"] and payload["parameters"] == metadata["parameters"]:
                    details = {**metadata, "format": "stl", "file_sha256": metadata["mesh_sha256"]}
                    route.fulfill(body=mesh, headers=headers(details, "model/stl"))
                else:
                    route.fulfill(status=422, json={"error": "Unexpected CAD work in a field-feedback check."})

            page.route("**/api/generate", generate)
            page.on("download", lambda download: downloads.append(download.suggested_filename))
            page.goto(BASE)
            page.locator(f'[data-model="{model}"]').click()
            page.wait_for_function("() => !document.querySelector('#download-cad').disabled")
            page.locator(".saved-dimensions > summary").click()
            return jobs, downloads

        def field(page, key):
            return page.locator(f'[data-parameter="{key}"]')

        def visible_in_viewport(locator):
            assert locator.evaluate("node => { const rect=node.getBoundingClientRect(); return rect.top>=0 && rect.bottom<=innerHeight; }")

        def close_reachable(page):
            assert page.locator("#close-editor").evaluate("button => { const r=button.getBoundingClientRect(); return !!document.elementFromPoint(r.left+r.width/2, r.top+r.height/2)?.closest('#close-editor'); }")

        def flagged(page, key, text, focused=False):
            input = field(page, key)
            expect(input).to_have_attribute("aria-invalid", "true")
            expect(input).to_have_accessible_description(re.compile(re.escape(text)))
            assert not input.evaluate("input => input.checkValidity()")
            assert page.locator(f"#error-{key}").is_visible()
            if focused:
                assert input.evaluate("input => input===document.activeElement")
                visible_in_viewport(input)
                visible_in_viewport(page.locator(f"#error-{key}"))

        def clean(page):
            assert page.locator('[data-parameter][aria-invalid="true"]').count() == 0
            assert page.locator(".parameter-error:not([hidden])").count() == 0
            assert page.locator("#parameters").evaluate("form => form.checkValidity()")

        def input_file(page, parameters, name="parameters.json", model="parts_tray", chooser=False):
            data = json.dumps({"model": model, "parameters": parameters, "units": "mm"}).encode("utf-8")
            file = {"name": name, "mimeType": "application/json", "buffer": data}
            if chooser:
                with page.expect_file_chooser() as event:
                    page.locator("#load-dimensions").click()
                event.value.set_files(file)
            else:
                page.locator("#dimensions-file").set_input_files(file)

        def file_error(page):
            expect(page.locator("#dimensions-error")).to_be_visible()
            expect(page.locator("#load-dimensions")).to_have_accessible_description(re.compile("Saved dimensions could not be loaded"))

        def release_file(page, index):
            page.evaluate("index => window.pendingDimensionReads[index]()", index)
            flush(page)

        def mobile_save_exposes_the_offscreen_invalid_field(page):
            jobs, downloads = setup(page, "sliding_box", mobile=True)
            field(page, "sample_height").fill("25")
            page.locator("#save-dimensions").click()
            flagged(page, "sample_height", "between 12 and 24", focused=True)
            close_reachable(page)
            page.screenshot(path=str(ROOT / "review/cloud_field_feedback_mobile.png"))
            assert not jobs and not downloads

        def copy_link_focuses_invalid_field_without_copying(page):
            jobs, downloads = setup(page, "sliding_box", mobile=True)
            field(page, "sample_height").fill("25")
            page.locator("#share").click()
            flagged(page, "sample_height", "between 12 and 24", focused=True)
            assert page.evaluate("window.copies.length") == 0
            field(page, "sample_height").fill("16")
            clean(page)
            assert page.locator("#download").is_enabled()
            assert not jobs and not downloads

        def numeric_list_errors_participate_in_native_validation(page):
            jobs, downloads = setup(page, "cable_comb")
            field(page, "cable_diameters").fill("3, 1001")
            flagged(page, "cable_diameters", "numbers between")
            assert not page.locator("#parameters").evaluate("form => form.checkValidity()")
            page.locator("#rebuild").click()
            flagged(page, "cable_diameters", "numbers between", focused=True)
            field(page, "cable_diameters").fill("9, 2, 3.55")
            clean(page)
            expect(field(page, "cable_diameters")).to_have_accessible_description("1 to 16 numbers, separated by commas; order is kept. Preview: 3, 4, 5, 6, 8 mm")
            assert not jobs and not downloads

        def correcting_resetting_and_reverting_clear_field_errors(page):
            jobs, _ = setup(page)
            field(page, "length").fill("251")
            flagged(page, "length", "between 30 and 250")
            field(page, "length").fill("180.55")
            clean(page)
            field(page, "columns").fill("2.5")
            flagged(page, "columns", "whole number")
            page.locator("#reset-parameters").click()
            clean(page)
            field(page, "length").fill("")
            flagged(page, "length", "enter a number")
            page.locator("#revert-parameters").click()
            clean(page)
            assert page.locator("#download").is_enabled()
            assert not jobs

        def failed_imports_describe_the_file_and_keep_valid_inputs(page):
            jobs, _ = setup(page, "sliding_box", mobile=True)
            input_file(page, {"length": 251}, chooser=True)
            file_error(page)
            flush(page)
            visible_in_viewport(page.locator("#dimensions-error"))
            close_reachable(page)
            clean(page)
            assert page.locator("#model-title").inner_text() == "Sliding-lid box"
            assert page.locator("#download").is_enabled()
            page.screenshot(path=str(ROOT / "review/cloud_dimensions_error_mobile.png"))
            close_reachable(page)
            assert not jobs

        def new_actions_dismiss_obsolete_file_errors(page):
            jobs, _ = setup(page)
            for action in ("edit", "reset", "revert", "save", "valid-file", "navigation"):
                if action == "revert":
                    field(page, "length").fill("180.55")
                input_file(page, {"length": 251})
                file_error(page)
                if action == "edit":
                    field(page, "length").fill("170.55")
                elif action == "revert":
                    page.locator("#revert-parameters").click()
                elif action == "valid-file":
                    input_file(page, {})
                    page.wait_for_function("() => document.querySelector('#form-message').textContent.includes('match the verified')")
                elif action == "navigation":
                    page.locator("#close-editor").click()
                    page.wait_for_function("() => !document.querySelector('#editor').open")
                    page.locator('[data-model="cable_comb"]').click()
                    page.wait_for_function("() => !document.querySelector('#download').disabled")
                else:
                    page.locator("#reset-parameters" if action == "reset" else "#save-dimensions").click()
                assert page.locator("#dimensions-error").is_hidden()
                expect(page.locator("#load-dimensions")).to_have_accessible_description("Drop one dimensions JSON, versions backup or CAD/kit ZIP anywhere in this editor. The file choosers also work.")
            assert not jobs

        def long_import_errors_stay_bounded_and_fit_mobile_layout(page):
            jobs, _ = setup(page, mobile=True)
            input_file(page, {"unexpected_" + "x" * 1000: 1}, chooser=True)
            file_error(page)
            text = page.locator("#dimensions-error").inner_text()
            assert "Unknown parameter" in text and "…" in text and len(text) < 170
            visible_in_viewport(page.locator("#dimensions-error"))
            assert page.locator("#editor").evaluate("editor => editor.scrollWidth <= editor.clientWidth")
            clean(page)
            assert page.locator("#download").is_enabled() and not jobs

        def stale_file_reads_cannot_restore_dismissed_errors(page):
            jobs, _ = setup(page)
            for index, action in enumerate(("edit", "reset", "new-file")):
                input_file(page, {"length": 251}, name=f"slow-{index}.json")
                page.wait_for_function("count => window.pendingDimensionReads.length===count", arg=index + 1)
                if action == "edit":
                    field(page, "length").fill("170.55")
                elif action == "reset":
                    page.locator("#reset-parameters").click()
                else:
                    input_file(page, {"length": 180.55})
                    page.wait_for_function("() => document.querySelector('#form-message').textContent.includes('Saved dimensions loaded')")
                release_file(page, index)
                assert page.locator("#dimensions-error").is_hidden()
                clean(page)
            assert field(page, "length").input_value() == "180.55" and not jobs

        def invalid_copy_during_build_preserves_progress_and_recovery(page):
            jobs, downloads = setup(page)
            field(page, "length").fill("180.5")
            page.evaluate("window.holdBuild=true")
            page.locator("#rebuild").click()
            page.wait_for_function("() => typeof window.releaseBuild==='function'")
            progress = page.locator("#form-message").inner_text()
            field(page, "length").fill("251")
            page.locator("#share").click()
            flagged(page, "length", "between 30 and 250", focused=True)
            assert page.locator("#form-message").inner_text() == progress
            assert page.locator("#stop-build").is_visible()
            assert page.evaluate("window.copies.length") == 0
            page.locator("#stop-build").click()
            page.locator("#revert-parameters").click()
            page.evaluate("window.releaseBuild()")
            flush(page)
            clean(page)
            assert field(page, "length").input_value() == "150"
            assert page.locator("#download").is_enabled()
            assert len(jobs) == 1 and not downloads

        def history_restores_invalid_drafts_and_their_associated_errors(page):
            jobs, _ = setup(page)
            field(page, "length").fill("251")
            page.go_back()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            page.go_forward()
            page.wait_for_function("() => document.querySelector('#editor').open && document.querySelector('#preview-loading').hidden")
            flagged(page, "length", "between 30 and 250")
            page.locator("#save-dimensions").click()
            flagged(page, "length", "between 30 and 250", focused=True)
            field(page, "length").fill("150")
            clean(page)
            assert page.locator("#download").is_enabled() and not jobs

        def keyboard_save_and_copy_recover_without_rebuilding(page):
            jobs, _ = setup(page, mobile=True)
            field(page, "length").fill("251")
            page.locator("#save-dimensions").focus()
            page.locator("#save-dimensions").press("Enter")
            flagged(page, "length", "between 30 and 250", focused=True)
            field(page, "length").fill("180.55")
            with page.expect_download() as event:
                page.locator("#save-dimensions").focus()
                page.locator("#save-dimensions").press("Enter")
            assert json.loads(Path(event.value.path()).read_bytes())["parameters"]["length"] == 180.55
            page.locator("#share").focus()
            page.locator("#share").press("Enter")
            page.wait_for_function("() => window.copies.length===1")
            assert page.evaluate("JSON.parse(new URL(window.copies[0]).searchParams.get('p')).length") == 180.55
            clean(page)
            assert not jobs

        for test in (mobile_save_exposes_the_offscreen_invalid_field, copy_link_focuses_invalid_field_without_copying,
                     numeric_list_errors_participate_in_native_validation, correcting_resetting_and_reverting_clear_field_errors,
                     failed_imports_describe_the_file_and_keep_valid_inputs, new_actions_dismiss_obsolete_file_errors,
                     long_import_errors_stay_bounded_and_fit_mobile_layout,
                     stale_file_reads_cannot_restore_dismissed_errors, invalid_copy_during_build_preserves_progress_and_recovery,
                     history_restores_invalid_drafts_and_their_associated_errors, keyboard_save_and_copy_recover_without_rebuilding):
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                test(page)
                assert not errors, errors
                passed.append(test.__name__)
                print(f"PASS {test.__name__}", flush=True)
            except Exception as exc:
                failures.append(dict(test=test.__name__, error=str(exc), traceback=traceback.format_exc(), browser_errors=errors))
                print(f"FAIL {test.__name__}: {failures[-1]['traceback']}", flush=True)
            finally:
                page.close()
        context.close()
        browser.close()
    report = dict(endpoint=BASE, passed=passed, failures=failures, mesh_sha256=hashlib.sha256(mesh).hexdigest(),
        transport="compiled assets with real CAD fixture and controlled local file reads" if OFFLINE else "local HTTP bridge and controlled local file reads")
    (ROOT / "review/cloud_field_feedback_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert not failures, report


if __name__ == "__main__":
    main()
