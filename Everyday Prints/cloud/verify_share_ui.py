"""Verify clipboard ordering, current sharing feedback and slow-copy recovery."""
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

CLIPBOARD = """window.copies = [];
Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
  writeText: text => new Promise((resolve, reject) => window.copies.push({ text, resolve, reject }))
} });
window.finishCopy = index => { window.clipboardText = window.copies[index].text; window.copies[index].resolve(); };
window.rejectCopy = index => window.copies[index].reject(new Error('Controlled clipboard denial'));"""


def main():
    archive, metadata, mesh = fixture("parts_tray")
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1080})
        context.set_default_timeout(20000)
        if OFFLINE:
            attach_assets(context)

        def setup(page):
            page.clock.install()
            page.add_init_script(CLIPBOARD)
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            page.locator('[data-model="parts_tray"]').click()
            page.wait_for_function("() => !document.querySelector('#download').disabled")

        def copy(page, length=None):
            if length is not None:
                page.locator('[data-parameter="length"]').fill(length)
            page.locator("#share").click()

        def finish(page, index):
            page.evaluate("index => window.finishCopy(index)", index)
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")

        def copied(page):
            page.wait_for_function("() => document.querySelector('#share-message').textContent.includes('Link copied')")

        def clipboard_length(page):
            return page.evaluate("JSON.parse(new URL(window.clipboardText).searchParams.get('p')).length")

        def feedback_preserves_form_and_download_gates(page):
            setup(page)
            page.locator('[data-parameter="length"]').fill("180.55")
            before = page.locator("#form-message").inner_text()
            copy(page)
            finish(page, 0)
            copied(page)
            assert clipboard_length(page) == 180.55
            assert page.locator("#form-message").inner_text() == before
            assert page.locator("#download").is_disabled()
            assert page.locator("#share-message").get_attribute("role") == "status"

        def changed_and_returned_edits_suppress_old_feedback(page):
            setup(page)
            copy(page)
            page.locator('[data-parameter="length"]').fill("190.5")
            page.locator('[data-parameter="length"]').fill("150")
            before = page.locator("#form-message").inner_text()
            finish(page, 0)
            assert page.locator("#share-message").is_hidden()
            assert page.locator("#form-message").inner_text() == before
            assert page.locator("#download").is_enabled()

        def revert_reset_and_import_cancel_sharing_feedback(page):
            setup(page)
            copy(page)
            page.locator('[data-parameter="length"]').fill("190.5")
            page.locator("#revert-parameters").click()
            finish(page, 0)
            assert page.locator("#share-message").is_hidden()
            copy(page)
            page.locator("#reset-parameters").click()
            finish(page, 1)
            assert page.locator("#share-message").is_hidden()
            copy(page)
            page.locator("#dimensions-file").set_input_files({"name": "parameters.json", "mimeType": "application/json", "buffer": json.dumps(metadata).encode()})
            page.wait_for_function("() => document.querySelector('[data-parameter=length]').value === '180.5'")
            finish(page, 2)
            assert page.locator("#share-message").is_hidden()
            assert page.locator("#download").is_disabled()

        def rapid_copies_write_only_latest_queued_link(page):
            setup(page)
            for value in ("170.5", "180.5", "190.5"):
                copy(page, value)
            assert page.evaluate("window.copies.length") == 1
            finish(page, 0)
            page.wait_for_function("() => window.copies.length === 2")
            assert "Link copied" not in page.locator("#share-message").inner_text()
            assert page.evaluate("JSON.parse(new URL(window.copies[1].text).searchParams.get('p')).length") == 190.5
            finish(page, 1)
            copied(page)
            assert clipboard_length(page) == 190.5

        def queued_copy_survives_old_writer_denial(page):
            setup(page)
            copy(page, "170.5")
            copy(page, "180.5")
            page.evaluate("window.rejectCopy(0)")
            page.wait_for_function("() => window.copies.length === 2")
            finish(page, 1)
            copied(page)
            assert clipboard_length(page) == 180.5

        def slow_copy_offers_current_url_without_blocking(page):
            setup(page)
            copy(page, "170.5")
            copy(page, "180.5")
            page.clock.fast_forward(3001)
            assert "page URL" in page.locator("#share-message").inner_text()
            assert page.evaluate("JSON.parse(new URL(location.href).searchParams.get('p')).length") == 180.5
            assert page.locator("#rebuild").is_enabled() and page.locator("#share").is_enabled()
            assert page.evaluate("window.copies.length") == 1
            page.screenshot(path=str(ROOT / "review/cloud_share_waiting.png"))
            finish(page, 0)
            finish(page, 1)
            copied(page)
            assert clipboard_length(page) == 180.5

        def model_switch_keeps_latest_requested_clipboard(page):
            setup(page)
            copy(page, "180.5")
            page.locator("#close-editor").click()
            page.wait_for_function("() => !document.querySelector('#editor').open && !new URL(location.href).searchParams.has('model')")
            page.locator('[data-model="cable_comb"]').click()
            page.wait_for_function("() => !document.querySelector('#download').disabled")
            assert page.locator("#share-message").is_hidden()
            copy(page)
            finish(page, 0)
            finish(page, 1)
            copied(page)
            assert page.evaluate("new URL(window.clipboardText).searchParams.get('model')") == "cable_comb"

        def copy_during_build_preserves_progress_and_stop(page):
            page.add_init_script(DEFERRED_BODY + """const realFetch = window.fetch;
              window.fetch = async (...args) => {
                const response = await realFetch(...args);
                if (String(args[0]).includes('/api/generate')) {
                  const bytes = await response.arrayBuffer();
                  window.deferFileBody(response, bytes, () => new Promise(resolve => { window.releaseBuild = resolve; }));
                }
                return response;
              };""")
            page.route("**/api/generate", lambda route: route.fulfill(body=mesh, headers=headers({**metadata, "format": "stl", "file_sha256": metadata["mesh_sha256"]}, "model/stl")))
            setup(page)
            page.locator('[data-parameter="length"]').fill("180.5")
            page.locator("#rebuild").click()
            page.wait_for_function("() => typeof window.releaseBuild === 'function'")
            before = page.locator("#form-message").inner_text()
            copy(page)
            finish(page, 0)
            copied(page)
            assert page.locator("#form-message").inner_text() == before
            assert page.locator("#stop-build").is_visible()
            assert page.locator("#download").is_disabled()
            page.locator("#stop-build").click()
            page.evaluate("window.releaseBuild()")
            assert page.locator("#share-message").is_hidden()

        def invalid_drafts_and_missing_clipboard_recover(page):
            setup(page)
            page.locator('[data-parameter="length"]').fill("")
            copy(page)
            assert page.evaluate("window.copies.length") == 0
            assert "enter a number" in page.locator("#form-message").inner_text()
            page.locator('[data-parameter="length"]').fill("180.5")
            page.evaluate("Object.defineProperty(navigator, 'clipboard', { value: undefined })")
            copy(page)
            page.wait_for_function("() => document.querySelector('#share-message').textContent.includes('page URL')")
            assert page.evaluate("JSON.parse(new URL(location.href).searchParams.get('p')).length") == 180.5

        def mobile_keyboard_copy_and_denial_fallback(page):
            page.set_viewport_size({"width": 390, "height": 844})
            setup(page)
            page.locator('[data-parameter="length"]').fill("180.55")
            page.locator("#share").focus()
            page.locator("#share").press("Enter")
            page.evaluate("window.rejectCopy(0)")
            page.wait_for_function("() => document.querySelector('#share-message').textContent.includes('page URL')")
            assert page.locator("#share").evaluate("button => button === document.activeElement")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.locator("#share-message").scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / "review/cloud_share_mobile.png"))

        for test in (feedback_preserves_form_and_download_gates,
                     changed_and_returned_edits_suppress_old_feedback,
                     revert_reset_and_import_cancel_sharing_feedback,
                     rapid_copies_write_only_latest_queued_link,
                     queued_copy_survives_old_writer_denial,
                     slow_copy_offers_current_url_without_blocking,
                     model_switch_keeps_latest_requested_clipboard,
                     copy_during_build_preserves_progress_and_stop,
                     invalid_drafts_and_missing_clipboard_recover,
                     mobile_keyboard_copy_and_denial_fallback):
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
        transport="compiled assets with controlled clipboard writes and real CAD fixtures" if OFFLINE else "local HTTP bridge and controlled clipboard writes")
    (ROOT / "review/cloud_share_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert not failures, report


if __name__ == "__main__":
    main()
