"""Verify consistent parameter checks across drafts, saved files and share links."""
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
from urllib.parse import urlencode, urlparse, parse_qs

from playwright.sync_api import sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from browser_transfers import DEFERRED_BODY
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = "--offline" in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5178")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT.parent / ".cad-cache/browsers"))

CLIPBOARD = """window.copies = [];
Object.defineProperty(navigator, 'clipboard', { value: {
  writeText: text => { window.copies.push(text); return Promise.resolve(); }
} });"""


def main():
    archive, metadata, mesh = fixture("parts_tray_original")
    catalog = json.loads((CLOUD / "public/catalog.json").read_text(encoding="utf-8"))["models"]
    models = {item["name"]: item for item in catalog}
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1080}, accept_downloads=True)
        context.set_default_timeout(20000)
        if OFFLINE:
            attach_assets(context)

        def flush(page):
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")

        def ready(page):
            page.wait_for_function("() => document.querySelector('#editor').open && !document.querySelector('#download').disabled")

        def setup(page, name="parts_tray"):
            page.add_init_script(CLIPBOARD)
            jobs, downloads = [], []

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload)
                if payload["model"] == metadata["model"] and payload["parameters"] == metadata["parameters"]:
                    if payload.get("format") == "cad":
                        route.fulfill(body=archive, headers=headers(metadata))
                    else:
                        details = {**metadata, "format": "stl", "file_sha256": metadata["mesh_sha256"]}
                        route.fulfill(body=mesh, headers=headers(details, "model/stl"))
                else:
                    route.fulfill(status=422, json={"error": "Unexpected CAD job in a parameter preflight check."})

            page.route("**/api/generate", generate)
            page.on("download", lambda download: downloads.append(download.suggested_filename))
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            page.locator(f'[data-model="{name}"]').click()
            ready(page)
            page.locator(".saved-dimensions summary").click()
            return jobs, downloads

        def error(page, text):
            page.wait_for_function("text => { const node = document.querySelector('#form-message'); return node.classList.contains('error') && node.textContent.includes(text); }", arg=text)

        def input_file(page, name, parameters):
            record = {"model": name, "parameters": parameters, "units": "mm"}
            page.locator("#dimensions-file").set_input_files({"name": "parameters.json", "mimeType": "application/json", "buffer": json.dumps(record).encode("utf-8")})

        def download(page, button):
            with page.expect_download() as event:
                page.locator("#" + button).click()
            return event.value.suggested_filename, Path(event.value.path()).read_bytes()

        def share_url(name, parameters):
            return BASE + "/?" + urlencode({"model": name, "p": json.dumps(parameters)})

        def assert_original(page, name="parts_tray"):
            item = models[name]
            for field in item["parameters"]:
                value = page.locator(f'[data-parameter="{field["key"]}"]').input_value()
                parsed = [float(number.strip()) for number in value.split(",")] if field["type"] == "list" else float(value)
                assert parsed == field["default"], (name, field["key"], value)
            assert page.locator("#download").is_enabled()
            assert page.locator("#parameters").evaluate("form => form.checkValidity()")
            shared = parse_qs(urlparse(page.url).query).get("p")
            assert not shared or json.loads(shared[0]) == item["defaults"]

        def scalar_ranges_gate_all_actions_before_building(page):
            jobs, downloads = setup(page)
            cases = [("length", "29.99", "between 30 and 250"), ("length", "250.01", "between 30 and 250"),
                     ("columns", "9", "between 1 and 8"), ("columns", "2.5", "whole number"),
                     ("pocket_radius", "-0.01", "at least 0"),
                     ("outer_radius", "1001", "numbers between"), ("outer_radius", "-1001", "numbers between")]
            for key, value, expected in cases:
                page.locator("#reset-parameters").click()
                page.locator(f'[data-parameter="{key}"]').fill(value)
                error(page, expected)
                assert page.locator("#mesh-status").inner_text() == "Fix invalid dimensions"
                assert page.locator("#download").is_disabled() and page.locator("#download-cad").is_disabled()
                assert not page.locator("#parameters").evaluate("form => form.checkValidity()")
                page.locator("#save-dimensions").click()
                page.locator("#share").click()
                page.locator("#rebuild").click()
                page.locator("#parameters").dispatch_event("submit")
                flush(page)
                error(page, expected)
                assert not jobs and not downloads and page.evaluate("window.copies.length") == 0
                assert not page.evaluate("new URL(location.href).searchParams.has('p')")
            page.locator("#revert-parameters").click()
            assert_original(page)

        def rejected_files_are_atomic_and_keep_cached_downloads(page):
            jobs, _ = setup(page)
            assert download(page, "download-cad")[1] == archive
            url = page.url
            cases = [({"length": 251}, "between 30 and 250"), ({"width": 29.9}, "between 30 and 250"),
                     ({"columns": 9}, "between 1 and 8"), ({"pocket_radius": -0.1}, "at least 0"),
                     ({"length": 180.55, "width": 251}, "Width:"),
                     ({"length": "180.55"}, "numbers between"), ({"unexpected": 1}, "Unknown parameter")]
            for parameters, expected in cases:
                input_file(page, "parts_tray", parameters)
                error(page, expected)
                assert_original(page)
                assert page.url == url
                assert page.locator("#model-size").inner_text() == "150 × 100 × 24"
            assert download(page, "download-cad")[1] == archive
            assert len(jobs) == 2, "Rejected files discarded the verified CAD cache"

        def list_preflight_blocks_caps_and_wrong_numeric_types(page):
            jobs, downloads = setup(page, "cable_comb")
            for value, expected in [("3, 1001", "numbers between"), ("3, -1001", "numbers between"),
                                    ('[3, "4"]', "1 to 16 numbers"), ("[3, true]", "1 to 16 numbers"),
                                    ("[3, null]", "1 to 16 numbers"), ("3,", "1 to 16 numbers"),
                                    (", ".join(["3"] * 17), "1 to 16 numbers")]:
                page.locator('[data-parameter="cable_diameters"]').fill(value)
                error(page, expected)
                page.locator("#save-dimensions").click()
                page.locator("#share").click()
                page.locator("#rebuild").click()
                flush(page)
                assert not jobs and not downloads and page.evaluate("window.copies.length") == 0
                assert page.locator("#download").is_disabled()
            page.locator("#revert-parameters").click()
            assert_original(page, "cable_comb")

        def valid_decimal_and_ordered_list_links_round_trip(page):
            jobs, _ = setup(page)
            page.locator('[data-parameter="length"]').fill("180.55")
            assert page.locator("#parameters").evaluate("form => form.checkValidity()")
            name, data = download(page, "save-dimensions")
            assert name == "parts_tray-dimensions.json"
            record = json.loads(data)
            assert record["parameters"]["length"] == 180.55
            page.locator("#share").click()
            page.wait_for_function("() => document.querySelector('#share-message').textContent.includes('Link copied')")
            url = page.evaluate("window.copies[0]")
            assert json.loads(parse_qs(urlparse(url).query)["p"][0])["length"] == 180.55
            page.goto(url)
            page.wait_for_function("() => document.querySelector('#preview-loading').hidden")
            assert page.locator('[data-parameter="length"]').input_value() == "180.55"
            assert "Shared dimensions loaded" in page.locator("#form-message").inner_text()
            assert page.locator("#download").is_disabled()
            input_file(page, "parts_tray", record["parameters"])
            page.wait_for_function("() => document.querySelector('#form-message').textContent.includes('Saved dimensions loaded')")
            ordered = [9, 2, 3.55]
            page.goto(share_url("cable_comb", {"cable_diameters": ordered}))
            page.wait_for_function("() => document.querySelector('#preview-loading').hidden")
            assert page.locator('[data-parameter="cable_diameters"]').input_value() == "9, 2, 3.55"
            page.locator(".saved-dimensions summary").click()
            assert json.loads(download(page, "save-dimensions")[1])["parameters"]["cable_diameters"] == ordered
            page.locator("#share").click()
            page.wait_for_function("window.copies.length === 1")
            assert page.evaluate("JSON.parse(new URL(window.copies[0]).searchParams.get('p')).cable_diameters") == ordered
            assert not jobs

        def invalid_link_parameters_restore_defaults_with_explanation(page):
            jobs, _ = setup(page)
            cases = [("parts_tray", value) for value in [None, [], 0, False,
                     {"length": "180.55"}, {"length": True}, {"length": [180]}, {"columns": 9},
                     {"length": 180.55, "width": 251}, {"outer_radius": 1001}, {"unexpected": 1}]]
            cases += [("cable_comb", {"cable_diameters": "3, 4"}), ("cable_comb", {"cable_diameters": [3, "4"]})]
            for name, parameters in cases:
                page.goto(share_url(name, parameters))
                ready(page)
                error(page, "Shared dimensions could not be applied. Original dimensions are shown.")
                assert_original(page, name)
                assert not page.evaluate("new URL(location.href).searchParams.has('p')")
                assert not jobs

        def malformed_and_oversized_links_offer_working_originals(page):
            jobs, _ = setup(page)
            for text, expected in [("{", "not valid JSON"), ("", "not valid JSON"), ("undefined", "not valid JSON"), (" " * 10001, "too large")]:
                page.goto(BASE + "/?" + urlencode({"model": "parts_tray", "p": text}))
                ready(page)
                error(page, expected)
                assert_original(page)
                assert not page.evaluate("new URL(location.href).searchParams.has('p')")
            assert not jobs

        def invalid_range_drafts_survive_history_without_becoming_links(page):
            jobs, downloads = setup(page)
            page.locator('[data-parameter="length"]').fill("251")
            page.go_back()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            page.go_forward()
            page.wait_for_function("() => document.querySelector('#editor').open && document.querySelector('#preview-loading').hidden")
            error(page, "between 30 and 250")
            assert page.locator('[data-parameter="length"]').input_value() == "251"
            assert page.locator("#download").is_disabled()
            page.locator("#save-dimensions").click()
            page.locator("#share").click()
            flush(page)
            assert not downloads and page.evaluate("window.copies.length") == 0
            assert not page.evaluate("new URL(location.href).searchParams.has('p')")
            page.locator("#revert-parameters").click()
            assert_original(page)
            assert hashlib.sha256(download(page, "download")[1]).hexdigest() == models["parts_tray"]["mesh_sha256"]
            assert not jobs

        def mobile_keyboard_errors_and_revert_keep_verified_files(page):
            jobs, downloads = setup(page)
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator('[data-parameter="length"]').fill("251")
            page.locator("#share").focus()
            page.locator("#share").press("Enter")
            error(page, "between 30 and 250")
            assert not downloads and page.evaluate("window.copies.length") == 0
            assert page.locator("#editor").evaluate("editor => editor.scrollWidth <= editor.clientWidth")
            page.locator("#form-message").scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / "review/cloud_parameters_mobile.png"))
            page.locator("#revert-parameters").focus()
            page.locator("#revert-parameters").press("Enter")
            assert_original(page)
            assert hashlib.sha256(download(page, "download")[1]).hexdigest() == models["parts_tray"]["mesh_sha256"]
            assert not jobs

        def late_link_feedback_respects_edits_and_reset(page):
            page.add_init_script(DEFERRED_BODY + """const holdOriginal = new URL(location.href).searchParams.has('p');
window.releaseOriginalBody = null;
const originalFetch = window.fetch;
window.fetch = async (...args) => {
  const response = await originalFetch(...args);
  if (!holdOriginal || !new URL(args[0], location.href).pathname.endsWith('/parts_tray.stl')) return response;
  const bytes = await response.arrayBuffer();
  window.deferFileBody(response, bytes, () => new Promise(resolve => { window.releaseOriginalBody = resolve; }));
  return response;
};""")
            jobs, _ = setup(page)
            for supplied, action, expected in [(251, "edit", "Your edits are ready"),
                                              (251, "reset", "Preview matches"),
                                              (251, "silent-edit", "Your edits are ready"),
                                              (180.55, "edit", "Your edits are ready")]:
                page.goto(share_url("parts_tray", {"length": supplied}))
                page.wait_for_function("() => typeof window.releaseOriginalBody === 'function'")
                if action == "reset":
                    page.locator("#reset-parameters").click()
                elif action == "silent-edit":
                    page.locator('[data-parameter="length"]').evaluate("input => { input.value = '190.55'; }")
                else:
                    page.locator('[data-parameter="length"]').fill("190.55")
                page.evaluate("window.releaseOriginalBody()")
                page.wait_for_function("() => document.querySelector('#preview-loading').hidden")
                flush(page)
                assert not page.locator("#form-message").evaluate("node => node.classList.contains('error')"), page.locator("#form-message").inner_text()
                assert expected in page.locator("#form-message").inner_text()
                if action == "reset":
                    assert_original(page)
                else:
                    assert page.locator('[data-parameter="length"]').input_value() == "190.55"
                    assert page.locator("#download").is_disabled()
            assert not jobs

        for test in (scalar_ranges_gate_all_actions_before_building,
                     rejected_files_are_atomic_and_keep_cached_downloads,
                     list_preflight_blocks_caps_and_wrong_numeric_types,
                     valid_decimal_and_ordered_list_links_round_trip,
                     invalid_link_parameters_restore_defaults_with_explanation,
                     malformed_and_oversized_links_offer_working_originals,
                     invalid_range_drafts_survive_history_without_becoming_links,
                     mobile_keyboard_errors_and_revert_keep_verified_files,
                     late_link_feedback_respects_edits_and_reset):
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
    report = dict(endpoint=BASE, passed=passed, failures=failures,
        cad_fixture_sha256=hashlib.sha256(archive).hexdigest(),
        transport="compiled assets with real original CAD ZIP and controlled clipboard" if OFFLINE else "local HTTP bridge with real original CAD ZIP")
    (ROOT / "review/cloud_parameters_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert not failures, report


if __name__ == "__main__":
    main()
