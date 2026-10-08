"""Verify saved dimensions, actual CAD metadata and late local file reads."""
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

from playwright.sync_api import sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from browser_transfers import DEFERRED_BODY
from validation_job import native_request
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = "--offline" in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5178")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT.parent / ".cad-cache/browsers"))

FILES = """window.fileReads = 0;
window.pendingDimensionReads = [];
const fileBytes = File.prototype.arrayBuffer;
File.prototype.arrayBuffer = function() {
  window.fileReads++;
  if (this.name === 'unreadable.json') return Promise.reject(new DOMException('Controlled unreadable file', 'NotReadableError'));
  if (!this.name.startsWith('slow')) return fileBytes.call(this);
  return new Promise(resolve => window.pendingDimensionReads.push(async () => resolve(await fileBytes.call(this))));
};"""

HOLD = DEFERRED_BODY + """window.holdDimensionBuild = false;
window.releaseDimensionBuild = null;
const realFetch = window.fetch;
window.fetch = async (...args) => {
  const response = await realFetch(...args);
  if (!window.holdDimensionBuild || !String(args[0]).includes('/api/generate')) return response;
  const bytes = await response.arrayBuffer();
  window.deferFileBody(response, bytes, () => new Promise(resolve => { window.releaseDimensionBuild = resolve; }));
  return response;
};"""


def main():
    fixtures = {name: fixture(name) for name in ("parts_tray", "cable_comb", "soap_dish_assembly")}
    previews = {name: value[2] for name, value in fixtures.items() if value[2] is not None}
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1080}, accept_downloads=True)
        context.set_default_timeout(20000)
        metadata = fixtures["soap_dish_assembly"][1]
        payload = {"model": metadata["model"], "parameters": metadata["parameters"]}
        if OFFLINE:
            attach_assets(context)
            status, mesh, _ = native_request(payload)
            assert status == 200
        else:
            response = context.request.post(BASE + "/api/generate", data=payload, timeout=120000)
            assert response.ok, response.text()
            mesh = response.body()
        assert hashlib.sha256(mesh).hexdigest() == metadata["mesh_sha256"]
        previews[metadata["model"]] = mesh

        def setup(page, name="parts_tray"):
            page.add_init_script(FILES + HOLD)
            jobs = []

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload)
                archive, metadata, _ = fixtures[payload["model"]]
                if payload.get("format") == "cad":
                    route.fulfill(body=archive, headers=headers(metadata))
                else:
                    metadata = {**metadata, "format": "stl", "file_sha256": metadata["mesh_sha256"]}
                    route.fulfill(body=previews[payload["model"]], headers=headers(metadata, "model/stl"))

            page.route("**/api/generate", generate)
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            page.locator(f'[data-model="{name}"]').click()
            ready(page)
            page.locator(".saved-dimensions summary").click()
            return jobs

        def ready(page):
            page.wait_for_function("() => !document.querySelector('#download-cad').disabled")

        def input_file(page, record, name="parameters.json", chooser=False):
            text = record if isinstance(record, str) else json.dumps(record)
            file = {"name": name, "mimeType": "application/json", "buffer": text.encode("utf-8")}
            if chooser:
                with page.expect_file_chooser() as event:
                    page.locator("#load-dimensions").click()
                event.value.set_files(file)
            else:
                page.locator("#dimensions-file").set_input_files(file)

        def loaded(page, matches=False):
            text = "match the verified" if matches else "loaded. Update"
            page.wait_for_function("text => document.querySelector('#form-message').textContent.includes(text)", arg=text)

        def download(page, button):
            with page.expect_download() as event:
                page.locator("#" + button).click()
            return event.value.suggested_filename, Path(event.value.path()).read_bytes()

        def saved(page):
            name, data = download(page, "save-dimensions")
            return name, json.loads(data)

        def custom(page, name="parts_tray"):
            input_file(page, fixtures[name][1])
            loaded(page)
            page.locator("#rebuild").click()
            ready(page)

        def release(page, index):
            page.evaluate("index => window.pendingDimensionReads[index]()", index)
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")

        def save_unbuilt_decimal_dimensions(page):
            jobs = setup(page)
            page.locator('[data-parameter="length"]').fill("180.55")
            name, record = saved(page)
            assert name == "parts_tray-dimensions.json"
            assert record["model"] == "parts_tray" and record["units"] == "mm"
            assert record["parameters"]["length"] == 180.55
            assert "bounds_mm" not in record and "mesh_sha256" not in record
            assert page.locator("#download").is_disabled()
            assert not jobs, "Saving dimensions started CAD work"

        def real_cad_metadata_loads_then_builds_exact_files(page):
            jobs = setup(page)
            input_file(page, fixtures["parts_tray"][1], chooser=True)
            loaded(page)
            assert page.locator('[data-parameter="length"]').input_value() == "180.5"
            assert page.locator("#model-size").inner_text() == "150 × 100 × 24"
            assert page.locator("#download").is_disabled() and not jobs
            page.locator("#rebuild").click()
            ready(page)
            assert download(page, "download")[1] == previews["parts_tray"]
            assert download(page, "download-cad")[1] == fixtures["parts_tray"][0]
            assert len(jobs) == 2

        def matching_file_repairs_edits_and_keeps_cached_cad(page):
            jobs = setup(page)
            custom(page)
            assert download(page, "download-cad")[1] == fixtures["parts_tray"][0]
            page.locator('[data-parameter="length"]').fill("")
            input_file(page, fixtures["parts_tray"][1])
            loaded(page, matches=True)
            assert download(page, "download")[1] == previews["parts_tray"]
            assert download(page, "download-cad")[1] == fixtures["parts_tray"][0]
            assert len(jobs) == 2

        def list_file_opens_model_and_preserves_history(page):
            jobs = setup(page)
            page.locator('[data-parameter="length"]').fill("190.5")
            input_file(page, fixtures["cable_comb"][1])
            loaded(page)
            assert page.locator('[data-parameter="cable_diameters"]').input_value() == "2, 3.5, 9"
            assert page.locator("#download").is_disabled() and not jobs
            assert page.evaluate("JSON.parse(new URL(location.href).searchParams.get('p')).cable_diameters") == [2, 3.5, 9]
            page.go_back()
            page.wait_for_function("() => new URL(location.href).searchParams.get('model') === 'parts_tray' && document.querySelector('#preview-loading').hidden")
            assert page.locator('[data-parameter="length"]').input_value() == "190.5"
            page.go_forward()
            page.wait_for_function("() => new URL(location.href).searchParams.get('model') === 'cable_comb' && document.querySelector('#preview-loading').hidden")
            assert page.locator('[data-parameter="cable_diameters"]').input_value() == "2, 3.5, 9"
            assert not jobs

        def assembly_dimensions_keep_canonical_kit(page):
            jobs = setup(page, "soap_dish_assembly")
            record = {**fixtures["soap_dish_assembly"][1], "kit": [{"model": "wrong", "quantity": 99}], "printable": True}
            input_file(page, record)
            loaded(page)
            _, saved_record = saved(page)
            assert saved_record["kit"] == fixtures["soap_dish_assembly"][1]["kit"]
            assert saved_record["parameters"]["length"] == 160
            assert page.locator("#download").is_hidden() and not jobs
            page.locator("#rebuild").click()
            ready(page)
            assert download(page, "download-cad")[1] == fixtures["soap_dish_assembly"][0]
            assert len(jobs) == 2

        def rejected_files_preserve_edits_preview_and_cad(page):
            jobs = setup(page)
            custom(page)
            download(page, "download-cad")
            page.locator('[data-parameter="length"]').fill("190.5")
            valid = {"model": "parts_tray", "parameters": {}, "units": "mm"}
            cases = [("{", "not valid JSON"),
                ({**valid, "units": "inch"}, "millimeters"),
                ({**valid, "model": "unknown"}, "not in the library"),
                ({**valid, "parameters": {"unexpected": 1}}, "Unknown parameter"),
                ({**valid, "parameters": {"columns": 2.5}}, "whole number"),
                ({**valid, "parameters": {"length": 1001}}, "numbers between"),
                ({**valid, "parameters": None}, "parameters object")]
            for record, expected in cases:
                input_file(page, record)
                page.wait_for_function("text => { const node = document.querySelector('#form-message'); return node.classList.contains('error') && node.textContent.includes(text); }", arg=expected)
                assert page.locator('[data-parameter="length"]').input_value() == "190.5"
                assert page.locator("#model-size").inner_text() == "180.5 × 100 × 24"
                assert page.locator("#download").is_disabled()
            page.locator("#revert-parameters").click()
            assert download(page, "download-cad")[1] == fixtures["parts_tray"][0]
            assert len(jobs) == 2

        def oversized_and_unreadable_files_allow_recovery(page):
            jobs = setup(page)
            input_file(page, " " * 16385)
            page.wait_for_function("() => document.querySelector('#form-message').textContent.includes('16 KiB')")
            assert page.evaluate("window.fileReads") == 0, "Oversized file was fully read"
            input_file(page, fixtures["parts_tray"][1], name="unreadable.json")
            page.wait_for_function("() => document.querySelector('#form-message').textContent.includes('could not be read')")
            assert page.locator('[data-parameter="length"]').input_value() == "150"
            input_file(page, fixtures["parts_tray"][1])
            loaded(page)
            assert page.locator('[data-parameter="length"]').input_value() == "180.5" and not jobs

        def late_file_reads_respect_edits_selections_and_navigation(page):
            jobs = setup(page)
            record = fixtures["parts_tray"][1]
            input_file(page, record, name="slow-edits.json")
            page.wait_for_function("() => window.pendingDimensionReads.length === 1")
            page.locator('[data-parameter="length"]').fill("190.5")
            release(page, 0)
            assert page.locator('[data-parameter="length"]').input_value() == "190.5"
            input_file(page, record, name="slow-selection.json")
            page.wait_for_function("() => window.pendingDimensionReads.length === 2")
            input_file(page, {"model": "parts_tray", "parameters": {"length": 170.25}, "units": "mm"})
            loaded(page)
            release(page, 1)
            assert page.locator('[data-parameter="length"]').input_value() == "170.25"
            input_file(page, record, name="slow-navigation.json")
            page.wait_for_function("() => window.pendingDimensionReads.length === 3")
            page.locator("#close-editor").click()
            page.wait_for_function("() => !document.querySelector('#editor').open && !new URL(location.href).searchParams.has('model')")
            page.locator('[data-model="phone_stand"]').click()
            ready(page)
            release(page, 2)
            assert page.evaluate("new URL(location.href).searchParams.get('model')") == "phone_stand"
            assert page.locator("#download").is_enabled() and not jobs

        def busy_controls_ignore_forced_file_changes(page):
            jobs = setup(page)
            page.locator('[data-parameter="length"]').fill("180.5")
            page.evaluate("window.holdDimensionBuild = true")
            page.locator("#rebuild").click()
            page.wait_for_function("() => typeof window.releaseDimensionBuild === 'function'")
            assert page.locator("#save-dimensions").is_disabled()
            assert page.locator("#load-dimensions").is_disabled()
            input_file(page, fixtures["cable_comb"][1])
            assert page.evaluate("window.fileReads") == 0
            assert page.locator('[data-parameter="length"]').input_value() == "180.5"
            page.locator("#stop-build").click()
            assert page.locator("#save-dimensions").is_enabled()
            assert page.locator("#load-dimensions").is_enabled()
            input_file(page, {"model": "parts_tray", "parameters": {}, "units": "mm"})
            loaded(page, matches=True)
            page.evaluate("window.releaseDimensionBuild()")
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            assert page.locator('[data-parameter="length"]').input_value() == "150"
            assert page.locator("#model-size").inner_text() == "150 × 100 × 24"
            assert len(jobs) == 1

        def returned_edits_and_reset_discard_pending_files(page):
            jobs = setup(page)
            record = fixtures["parts_tray"][1]
            input_file(page, record, name="slow-revert.json")
            page.wait_for_function("() => window.pendingDimensionReads.length === 1")
            page.locator('[data-parameter="length"]').fill("190.5")
            page.locator("#revert-parameters").click()
            release(page, 0)
            assert page.locator('[data-parameter="length"]').input_value() == "150"
            assert page.locator("#download").is_enabled()
            input_file(page, record, name="slow-returned-edit.json")
            page.wait_for_function("() => window.pendingDimensionReads.length === 2")
            page.locator('[data-parameter="length"]').fill("190.5")
            page.locator('[data-parameter="length"]').fill("150")
            release(page, 1)
            assert page.locator('[data-parameter="length"]').input_value() == "150"
            input_file(page, record, name="slow-reset.json")
            page.wait_for_function("() => window.pendingDimensionReads.length === 3")
            page.locator("#reset-parameters").click()
            release(page, 2)
            assert page.locator('[data-parameter="length"]').input_value() == "150"
            assert page.locator("#download").is_enabled() and not jobs

        def mobile_keyboard_file_chooser_and_save(page):
            page.set_viewport_size({"width": 390, "height": 844})
            jobs = setup(page)
            for name in ("save-dimensions", "load-dimensions"):
                box = page.locator("#" + name).bounding_box()
                assert box["height"] >= 44 and box["width"] >= 44
            button = page.locator("#load-dimensions")
            button.focus()
            with page.expect_file_chooser() as event:
                button.press("Enter")
            event.value.set_files({"name": "dimensions.json", "mimeType": "application/json", "buffer": json.dumps(fixtures["parts_tray"][1]).encode()})
            loaded(page)
            assert page.locator('[data-parameter="length"]').evaluate("input => input === document.activeElement")
            page.locator("#save-dimensions").focus()
            with page.expect_download() as event:
                page.locator("#save-dimensions").press("Enter")
            assert json.loads(Path(event.value.path()).read_bytes())["parameters"]["length"] == 180.5
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.locator(".parameters-panel").evaluate("panel => panel.scrollIntoView({ block: 'start' })")
            page.screenshot(path=str(ROOT / "review/cloud_dimensions_mobile.png"))
            assert not jobs

        for test in (save_unbuilt_decimal_dimensions, real_cad_metadata_loads_then_builds_exact_files,
                     matching_file_repairs_edits_and_keeps_cached_cad, list_file_opens_model_and_preserves_history,
                     assembly_dimensions_keep_canonical_kit, rejected_files_preserve_edits_preview_and_cad,
                     oversized_and_unreadable_files_allow_recovery,
                     late_file_reads_respect_edits_selections_and_navigation,
                     busy_controls_ignore_forced_file_changes,
                     returned_edits_and_reset_discard_pending_files,
                     mobile_keyboard_file_chooser_and_save):
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
        fixtures_sha256={name: hashlib.sha256(data[0]).hexdigest() for name, data in fixtures.items()},
        transport="compiled assets and real CAD fixtures with controlled local file reads" if OFFLINE else "local HTTP bridge and real CAD fixtures")
    (ROOT / "review/cloud_dimensions_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert not failures, report


if __name__ == "__main__":
    main()
