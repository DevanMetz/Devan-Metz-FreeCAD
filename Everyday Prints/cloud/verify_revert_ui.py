"""Verify restoring edited inputs to the last verified preview without rebuilding.

Real CAD fixtures cover scalars, numeric lists, kit quantities and cached files.
Delayed readers expose late-result races after stopping a preview or export.
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
from validation_job import native_request
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = "--offline" in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5178")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT.parent / ".cad-cache/browsers"))

HOLD = DEFERRED_BODY + """window.holdRevert = null;
window.pendingRevertBodies = [];
const realFetch = window.fetch;
window.fetch = async (...args) => {
  const response = await realFetch(...args);
  if (!String(args[0]).includes('/api/generate')) return response;
  const format = JSON.parse(args[1].body).format || 'stl';
  if (window.holdRevert !== format) return response;
  const bytes = await response.arrayBuffer();
  window.deferFileBody(response, bytes, () => new Promise(resolve => window.pendingRevertBodies.push(resolve)));
  return response;
};"""


def main():
    fixtures = {name: fixture(name) for name in ("parts_tray", "cable_comb", "soap_dish_assembly")}
    previews = {name: data[2] for name, data in fixtures.items() if data[2] is not None}
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1080}, accept_downloads=True)
        context.set_default_timeout(20000)
        assembly = fixtures["soap_dish_assembly"][1]
        payload = {"model": assembly["model"], "parameters": assembly["parameters"]}
        if OFFLINE:
            attach_assets(context)
            status, mesh, _ = native_request(payload)
            assert status == 200
        else:
            response = context.request.post(BASE + "/api/generate", data=payload, timeout=120000)
            assert response.ok, response.text()
            mesh = response.body()
        assert hashlib.sha256(mesh).hexdigest() == assembly["mesh_sha256"]
        previews[assembly["model"]] = mesh

        def setup(page, name="parts_tray", open_model=True):
            page.add_init_script(HOLD)
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
            if open_model:
                page.locator(f'[data-model="{name}"]').click()
                ready(page)
            return jobs

        def ready(page):
            page.wait_for_function("() => !document.querySelector('#download-cad').disabled")

        def custom(page, name="parts_tray"):
            for key, value in fixtures[name][1]["parameters"].items():
                text = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
                page.locator(f'[data-parameter="{key}"]').fill(text)
            page.locator("#rebuild").click()
            ready(page)
            assert page.locator("#revert-parameters").is_hidden()

        def download(page, button="download"):
            with page.expect_download() as event:
                page.locator("#" + button).click()
            return Path(event.value.path()).read_bytes()

        def revert(page):
            page.locator("#revert-parameters").click()
            assert page.locator("#revert-parameters").is_hidden()
            assert page.locator("#download-cad").is_enabled()
            assert "Preview matches" in page.locator("#form-message").inner_text()

        def release(page):
            page.evaluate("() => { window.holdRevert = null; window.pendingRevertBodies[0](); }")
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")

        def scalar_revert_reuses_verified_files(page):
            jobs = setup(page)
            custom(page)
            assert download(page, "download-cad") == fixtures["parts_tray"][0]
            page.locator('[data-parameter="length"]').fill("190.5")
            page.locator('[data-parameter="columns"]').fill("")
            assert page.locator("#download").is_disabled()
            revert(page)
            assert page.locator('[data-parameter="length"]').input_value() == "180.5"
            assert page.locator('[data-parameter="columns"]').input_value() == "3"
            assert download(page) == previews["parts_tray"]
            assert download(page, "download-cad") == fixtures["parts_tray"][0]
            assert len(jobs) == 2, "Reverting rebuilt verified files"

        def invalid_list_revert_preserves_order(page):
            jobs = setup(page, "cable_comb")
            custom(page, "cable_comb")
            field = page.locator('[data-parameter="cable_diameters"]')
            field.fill("[2,")
            assert page.locator("#download").is_disabled()
            revert(page)
            assert page.locator('[data-parameter="cable_diameters"]').input_value() == "2, 3.5, 9"
            assert download(page) == previews["cable_comb"]
            assert len(jobs) == 1

        def reset_keeps_original_and_revert_restores_custom(page):
            jobs = setup(page)
            custom(page)
            page.locator("#reset-parameters").click()
            assert page.locator('[data-parameter="length"]').input_value() == "150"
            assert page.locator("#download").is_disabled()
            revert(page)
            assert page.locator('[data-parameter="length"]').input_value() == "180.5"
            assert page.locator("#model-size").inner_text() == "180.5 × 100 × 24"
            assert len(jobs) == 1

        def pending_export_disables_revert_until_stopped(page):
            jobs = setup(page)
            custom(page)
            downloads = []
            page.on("download", lambda value: downloads.append(value))
            page.evaluate("window.holdRevert = 'cad'")
            page.locator("#download-cad").click()
            page.wait_for_function("() => window.pendingRevertBodies.length === 1")
            page.locator('[data-parameter="length"]').fill("190.5")
            assert page.locator("#revert-parameters").is_visible()
            assert page.locator("#revert-parameters").is_disabled()
            page.locator("#revert-parameters").dispatch_event("click")
            assert page.locator('[data-parameter="length"]').input_value() == "190.5"
            page.locator("#stop-build").click()
            revert(page)
            release(page)
            assert not downloads, "Stopped export downloaded after reverting"
            assert page.locator('[data-parameter="length"]').input_value() == "180.5"
            assert download(page, "download-cad") == fixtures["parts_tray"][0]
            assert len(jobs) == 3

        def stopped_preview_reverts_and_rejects_late_mesh(page):
            jobs = setup(page)
            page.evaluate("window.holdRevert = 'stl'")
            page.locator('[data-parameter="length"]').fill("180.5")
            page.locator("#rebuild").click()
            page.wait_for_function("() => window.pendingRevertBodies.length === 1")
            assert page.locator("#revert-parameters").is_disabled()
            page.locator("#stop-build").click()
            revert(page)
            release(page)
            assert page.locator('[data-parameter="length"]').input_value() == "150"
            assert page.locator("#model-size").inner_text() == "150 × 100 × 24"
            assert download(page) == (CLOUD / "public/models/parts_tray.stl").read_bytes()
            assert len(jobs) == 1
            assert page.evaluate("new URL(location.href).searchParams.has('p')") is False

        def missing_preview_keeps_revert_hidden(page):
            jobs = setup(page, open_model=False)
            page.route("**/models/parts_tray.stl", lambda route: route.abort())
            page.locator('[data-model="parts_tray"]').click()
            page.wait_for_function("() => document.querySelector('#preview-loading').hidden")
            page.locator('[data-parameter="length"]').fill("")
            assert page.locator("#revert-parameters").is_hidden()
            page.locator("#revert-parameters").dispatch_event("click")
            assert page.locator('[data-parameter="length"]').input_value() == ""
            assert page.locator("#download-cad").is_disabled()
            assert not jobs

        def history_and_shared_url_follow_reverted_parameters(page):
            jobs = setup(page)
            custom(page)
            page.locator('[data-parameter="length"]').fill("190.5")
            page.go_back()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            page.go_forward()
            page.wait_for_function("() => document.querySelector('#editor').open && document.querySelector('#preview-loading').hidden")
            assert page.locator('[data-parameter="length"]').input_value() == "190.5"
            revert(page)
            assert page.evaluate("JSON.parse(new URL(location.href).searchParams.get('p')).length") == 180.5
            page.go_back()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            page.go_forward()
            ready(page)
            assert page.locator('[data-parameter="length"]').input_value() == "180.5"
            assert page.locator("#revert-parameters").is_hidden()
            assert download(page) == previews["parts_tray"]
            assert len(jobs) == 1

        def assembly_revert_reuses_kit_and_shared_dimensions(page):
            jobs = setup(page, "soap_dish_assembly")
            custom(page, "soap_dish_assembly")
            assert download(page, "download-cad") == fixtures["soap_dish_assembly"][0]
            page.locator('[data-parameter="length"]').fill("170")
            revert(page)
            assert page.locator("#download").is_hidden()
            assert "parts kit" in page.locator("#download-cad").inner_text()
            assert download(page, "download-cad") == fixtures["soap_dish_assembly"][0]
            assert len(jobs) == 2
            page.locator('[data-part="soap_dish_tray"]').click()
            page.wait_for_function("() => document.querySelector('#preview-loading').hidden")
            assert page.locator('[data-parameter="length"]').input_value() == "160"
            assert page.locator("#download").is_disabled()

        def mobile_keyboard_revert_restores_focus(page):
            page.set_viewport_size({"width": 390, "height": 844})
            jobs = setup(page)
            custom(page)
            page.locator('[data-parameter="rows"]').fill("2.5")
            button = page.locator("#revert-parameters")
            button.scroll_into_view_if_needed()
            assert button.is_visible() and button.is_enabled()
            for control in (button, page.locator("#reset-parameters")):
                box = control.bounding_box()
                assert box["width"] >= 44 and box["height"] >= 44, box
            page.screenshot(path=str(ROOT / "review/cloud_revert_mobile.png"))
            button.focus()
            button.press("Enter")
            assert button.is_hidden()
            assert page.locator('[data-parameter="length"]').evaluate("input => input === document.activeElement")
            assert page.locator('[data-parameter="rows"]').input_value() == "2"
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert download(page) == previews["parts_tray"]
            assert len(jobs) == 1, "Keyboard revert submitted a new build"

        for test in (scalar_revert_reuses_verified_files, invalid_list_revert_preserves_order,
                     reset_keeps_original_and_revert_restores_custom,
                     pending_export_disables_revert_until_stopped,
                     stopped_preview_reverts_and_rejects_late_mesh,
                     missing_preview_keeps_revert_hidden,
                     history_and_shared_url_follow_reverted_parameters,
                     assembly_revert_reuses_kit_and_shared_dimensions,
                     mobile_keyboard_revert_restores_focus):
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
        transport="compiled assets and real CAD fixtures with controlled delayed transfers" if OFFLINE else "local HTTP bridge and real CAD fixtures")
    (ROOT / "review/cloud_revert_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert not failures, report


if __name__ == "__main__":
    main()
