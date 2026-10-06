"""Verify catalog mesh recovery without CAD jobs or lost customizer drafts."""
import json
import os
from pathlib import Path
import sys
import traceback
from urllib.parse import quote

from playwright.sync_api import expect, sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from browser_transfers import DEFERRED_BODY
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = "--offline" in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5178")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT.parent / ".cad-cache/browsers"))

FAULTS = DEFERRED_BODY + r"""window.originalFaults = [];
window.originalRequests = [];
window.originalTransfers = [];
const realFetch = window.fetch;
window.fetch = async (...args) => {
  const url = String(args[0]);
  if (!/\/models\/[^/]+\.stl$/.test(url)) return realFetch(...args);
  window.originalRequests.push({ url, cache: args[1]?.cache || 'default' });
  const fault = window.originalFaults.shift();
  const response = await realFetch(...args);
  if (!fault) return response;
  const stats = { mode: fault.mode, cancelled: 0, released: false, pulls: 0 };
  window.originalTransfers.push(stats);
  const wait = () => new Promise(resolve => { stats.release = resolve; });
  if (fault.mode === 'headers') {
    const cancel = response.body.cancel.bind(response.body);
    response.body.cancel = () => { stats.cancelled++; return cancel(); };
    await wait();
    return response;
  }
  if (fault.mode === 'body') {
    const bytes = await response.arrayBuffer();
    window.deferFileBody(response, bytes, wait);
    const getReader = response.body.getReader;
    response.body.getReader = () => {
      const reader = getReader();
      return {
        read: () => { stats.pulls++; return reader.read(); },
        cancel: () => { stats.cancelled++; return fault.neverCancel ? new Promise(() => {}) : reader.cancel(); },
        releaseLock: () => { stats.released = true; reader.releaseLock(); }
      };
    };
    return response;
  }
  await response.body.cancel();
  const stream = new ReadableStream({
    pull(controller) {
      stats.pulls++;
      if (fault.mode === 'corrupt') { controller.enqueue(new Uint8Array(4)); controller.close(); }
      else if (fault.mode === 'oversize') controller.enqueue(new Uint8Array(2 * 1024 * 1024));
    },
    cancel() { stats.cancelled++; return fault.neverCancel ? new Promise(() => {}) : undefined; }
  }, { highWaterMark: 0 });
  return new Response(stream, {
    status: fault.mode === 'failure' ? 503 : 200,
    headers: { 'Content-Type': fault.contentType ?? (fault.mode === 'html' ? 'text/html' : 'model/stl'), 'Content-Length': '1' }
  });
};"""


def main():
    original, custom = fixture("parts_tray_original"), fixture("parts_tray")
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1080}, accept_downloads=True)
        context.set_default_timeout(20000)
        if OFFLINE:
            attach_assets(context)

        def setup(page, mode="failure", model="parts_tray", parameters=None, raw_parameters=None, **fault_options):
            page.add_init_script(FAULTS)
            page.add_init_script("window.originalFaults.push(" + json.dumps(dict(mode=mode, **fault_options)) + ");")
            jobs = []

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload)
                assert payload["model"] == "parts_tray"
                data = custom if payload["parameters"]["length"] == 180.5 else original
                archive, metadata, mesh = data
                if payload.get("format") == "cad":
                    route.fulfill(body=archive, headers=headers(metadata))
                else:
                    metadata = {**metadata, "format": "stl", "file_sha256": metadata["mesh_sha256"]}
                    route.fulfill(body=mesh, headers=headers(metadata, "model/stl"))

            page.route("**/api/generate", generate)
            query = "?model=" + model
            if parameters is not None or raw_parameters is not None:
                query += "&p=" + quote(raw_parameters if raw_parameters is not None else json.dumps(parameters))
            page.goto(BASE + query)
            expect(page.locator("#editor")).to_be_visible()
            if mode in ("headers", "body"):
                page.wait_for_function("() => typeof window.originalTransfers.at(-1)?.release === 'function'")
            else:
                expect(page.locator("#preview-loading")).to_be_hidden()
            expect(page.locator("#retry-original")).to_be_enabled()
            return jobs

        def settled(page):
            expect(page.locator("#preview-loading")).to_be_hidden()
            expect(page.locator("#original-recovery")).to_be_hidden()

        def release(page, index=0):
            page.evaluate("index => window.originalTransfers[index].release()", index)
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")

        def history_state(page):
            return page.evaluate("({ length: history.length, state: history.state, url: location.href })")

        def load(page, record):
            page.locator(".saved-dimensions summary").click()
            with page.expect_file_chooser() as event:
                page.locator("#load-dimensions").click()
            event.value.set_files({"name": "parameters.json", "mimeType": "application/json", "buffer": json.dumps(record).encode("utf-8")})

        def download(page, button="download"):
            with page.expect_download() as event:
                page.locator("#" + button).click()
            return Path(event.value.path()).read_bytes()

        def failure_retries_static_asset_and_preserves_history(page):
            jobs = setup(page, neverCancel=True)
            assert page.evaluate("window.originalTransfers[0].cancelled") == 1
            expect(page.locator(".viewer-help")).to_contain_text("unavailable")
            before = history_state(page)
            page.locator("#retry-original").click()
            settled(page)
            assert history_state(page) == before
            assert page.evaluate("window.originalRequests.at(-1).cache") == "reload"
            assert download(page) == (CLOUD / "public/models/parts_tray.stl").read_bytes()
            assert not jobs

        def html_response_is_cancelled_without_reading(page):
            jobs = setup(page, "html", neverCancel=True)
            stats = page.evaluate("window.originalTransfers[0]")
            assert stats["cancelled"] == 1 and stats["pulls"] == 0, stats
            page.locator("#retry-original").click()
            settled(page)
            assert page.locator("#download-cad").is_enabled() and not jobs

        def mixed_case_html_is_cancelled_without_reading(page):
            jobs = setup(page, "html", contentType="Text/HTML; Charset=UTF-8", neverCancel=True)
            stats = page.evaluate("window.originalTransfers[0]")
            assert stats["cancelled"] == 1 and stats["pulls"] == 0, stats
            assert page.locator("#transfer-status").is_hidden()
            page.locator("#retry-original").click()
            settled(page)
            assert download(page) == (CLOUD / "public/models/parts_tray.stl").read_bytes()
            assert not jobs

        def failed_retry_keeps_draft_and_allows_another_retry(page):
            jobs = setup(page)
            page.locator("#param-length").fill("180.5")
            page.evaluate("window.originalFaults.push({mode:'failure', neverCancel:true})")
            page.locator("#retry-original").click()
            expect(page.locator("#preview-loading")).to_be_hidden()
            expect(page.locator("#form-message")).to_contain_text("could not be loaded")
            assert page.locator("#param-length").input_value() == "180.5"
            assert page.locator("#retry-original").is_enabled() and page.locator("#download").is_disabled()
            assert page.evaluate("window.originalTransfers[1].cancelled") == 1
            page.locator("#retry-original").click()
            settled(page)
            assert page.locator("#download").is_disabled() and not jobs

        def corrupted_original_recovers_with_verified_mesh(page):
            jobs = setup(page, "corrupt")
            expect(page.locator("#form-message")).to_contain_text("could not be verified")
            assert page.locator("#download").is_disabled()
            page.locator("#retry-original").click()
            settled(page)
            assert download(page) == (CLOUD / "public/models/parts_tray.stl").read_bytes() and not jobs

        def oversized_original_recovers_without_cad(page):
            jobs = setup(page, "oversize")
            expect(page.locator("#form-message")).to_contain_text("8 MiB")
            stats = page.evaluate("window.originalTransfers[0]")
            assert stats["pulls"] == 5 and stats["cancelled"] == 1, stats
            page.locator("#retry-original").click()
            settled(page)
            assert page.locator("#download").is_enabled() and not jobs

        def pending_reader_cancels_and_late_bytes_are_ignored(page):
            jobs = setup(page, "body", neverCancel=True)
            page.locator("#param-length").fill("180.50")
            before = history_state(page)
            page.locator("#retry-original").click()
            settled(page)
            stats = page.evaluate("window.originalTransfers[0]")
            assert stats["cancelled"] == 1 and stats["released"], stats
            assert page.locator("#param-length").input_value() == "180.50"
            assert page.locator("#download").is_disabled()
            message = page.locator("#form-message").inner_text()
            release(page)
            assert page.locator("#form-message").inner_text() == message
            assert page.locator("#model-size").inner_text() == "150 × 100 × 24"
            assert history_state(page) == before and not jobs

        def stale_headers_cancel_unused_response(page):
            jobs = setup(page, "headers")
            page.locator("#retry-original").click()
            settled(page)
            release(page)
            assert page.evaluate("window.originalTransfers[0].cancelled") == 1
            assert download(page) == (CLOUD / "public/models/parts_tray.stl").read_bytes() and not jobs

        def invalid_raw_draft_and_field_feedback_survive(page):
            jobs = setup(page, model="cable_comb")
            page.locator("#param-cable_diameters").fill(" 2, , 9 ")
            page.locator("#param-depth").fill("")
            before = history_state(page)
            values = page.locator("#parameter-fields input").evaluate_all("inputs => inputs.map(input => input.value)")
            page.locator("#retry-original").click()
            settled(page)
            assert page.locator("#parameter-fields input").evaluate_all("inputs => inputs.map(input => input.value)") == values
            expect(page.locator("#param-cable_diameters")).to_have_attribute("aria-invalid", "true")
            expect(page.locator("#error-cable_diameters")).to_be_visible()
            assert page.locator("#download").is_disabled() and page.locator("#download-cad").is_disabled()
            assert history_state(page) == before and not jobs

        def accepted_file_confirmation_and_exact_values_survive(page):
            jobs = setup(page)
            load(page, {"model": "parts_tray", "units": "mm", "parameters": {"length": 180.5}})
            expect(page.locator("#form-message")).to_contain_text("Saved dimensions loaded.")
            before = history_state(page)
            page.locator("#retry-original").click()
            settled(page)
            expect(page.locator("#form-message")).to_contain_text("Saved dimensions loaded.")
            assert json.loads(download(page, "save-dimensions"))["parameters"]["length"] == 180.5
            assert history_state(page) == before and not jobs

        def rejected_file_feedback_is_not_dismissed(page):
            jobs = setup(page)
            load(page, {"model": "parts_tray", "units": "mm", "parameters": {"length": -1}})
            expect(page.locator("#dimensions-error")).to_be_visible()
            error = page.locator("#dimensions-error").inner_text()
            page.locator("#retry-original").click()
            settled(page)
            assert page.locator("#dimensions-error").inner_text() == error
            assert page.locator("#form-message").inner_text() == error
            assert page.locator("#download").is_enabled() and not jobs

        def different_model_file_keeps_confirmation_through_retry(page):
            jobs = setup(page)
            page.evaluate("window.originalFaults.push({mode:'body'})")
            load(page, {"model": "cable_comb", "units": "mm", "parameters": {"depth": 40}})
            expect(page.locator("#form-message")).to_contain_text("Saved dimensions loaded.")
            page.wait_for_function("() => typeof window.originalTransfers.at(-1)?.release === 'function'")
            before = history_state(page)
            page.locator("#retry-original").click()
            settled(page)
            release(page, 1)
            expect(page.locator("#form-message")).to_contain_text("Saved dimensions loaded.")
            assert page.locator("#param-depth").input_value() == "40"
            assert page.locator("#download").is_disabled()
            assert history_state(page) == before and not jobs

        def rejected_shared_link_explanation_returns_after_retry(page):
            jobs = setup(page, raw_parameters="{broken")
            page.locator("#retry-original").click()
            settled(page)
            expect(page.locator("#form-message")).to_contain_text("Shared dimensions could not be applied.")
            assert page.locator("#param-length").input_value() == "150" and not jobs

        def edited_shared_link_keeps_newer_feedback_and_focus(page):
            jobs = setup(page, raw_parameters="{broken")
            page.evaluate("window.originalFaults.push({mode:'body'})")
            page.locator("#retry-original").click()
            page.wait_for_function("() => typeof window.originalTransfers.at(-1)?.release === 'function'")
            page.locator("#param-length").fill("180.5")
            release(page, 1)
            settled(page)
            expect(page.locator("#param-length")).to_be_focused()
            assert "Shared dimensions" not in page.locator("#form-message").inner_text()
            assert page.locator("#download").is_disabled() and not jobs

        def rapid_retries_keep_only_latest_response(page):
            jobs = setup(page, "body")
            page.evaluate("window.originalFaults.push({mode:'body'})")
            page.locator("#retry-original").click()
            page.wait_for_function("() => window.originalTransfers.length === 2 && typeof window.originalTransfers[1].release === 'function'")
            page.locator("#retry-original").click()
            settled(page)
            release(page, 1)
            release(page, 0)
            assert all(stat["cancelled"] == 1 and stat["released"] for stat in page.evaluate("window.originalTransfers"))
            assert len(page.evaluate("window.originalRequests")) == 3 and not jobs

        def custom_build_supersedes_pending_retry(page):
            jobs = setup(page)
            page.evaluate("window.originalFaults.push({mode:'body'})")
            page.locator("#retry-original").click()
            page.wait_for_function("() => typeof window.originalTransfers.at(-1)?.release === 'function'")
            page.locator("#param-length").fill("180.5")
            page.locator("#rebuild").click()
            page.wait_for_function("() => !document.querySelector('#download').disabled")
            release(page, 1)
            assert page.locator("#model-size").inner_text() == "180.5 × 100 × 24"
            assert download(page) == custom[2] and len(jobs) == 1
            assert download(page, "download-cad") == custom[0]
            count = len(jobs)
            page.locator("#retry-original").dispatch_event("click")
            assert download(page, "download-cad") == custom[0] and len(jobs) == count

        def model_switch_discards_pending_retry(page):
            jobs = setup(page)
            page.evaluate("window.originalFaults.push({mode:'body'})")
            page.locator("#retry-original").click()
            page.wait_for_function("() => typeof window.originalTransfers.at(-1)?.release === 'function'")
            page.locator("#close-editor").click()
            expect(page.locator("#editor")).to_be_hidden()
            page.locator('[data-model="cable_comb"]').click()
            settled(page)
            release(page, 1)
            assert page.locator("#model-title").inner_text() == "Desk-edge cable comb"
            assert download(page) == (CLOUD / "public/models/cable_comb.stl").read_bytes() and not jobs

        def reference_assembly_recovers_without_printable_stl(page):
            jobs = setup(page, model="soap_dish_assembly")
            page.locator("#retry-original").click()
            settled(page)
            assert page.locator("#download").is_hidden()
            assert page.locator("#download-cad").is_enabled()
            expect(page.locator("#reference-note")).to_be_visible()
            assert page.locator("#part-links button").count() > 0 and not jobs

        def mobile_keyboard_retry_restores_reachable_focus(page):
            page.set_viewport_size({"width": 390, "height": 844})
            jobs = setup(page)
            button = page.locator("#retry-original")
            box = button.bounding_box()
            assert box["height"] >= 44
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            button.scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / "review/cloud_original_retry_mobile.png"))
            button.focus()
            button.press("Enter")
            settled(page)
            expect(page.locator("#parameter-fields input").first).to_be_focused()
            assert page.locator("#download").is_enabled() and not jobs

        for check in (
            failure_retries_static_asset_and_preserves_history,
            html_response_is_cancelled_without_reading,
            mixed_case_html_is_cancelled_without_reading,
            failed_retry_keeps_draft_and_allows_another_retry,
            corrupted_original_recovers_with_verified_mesh,
            oversized_original_recovers_without_cad,
            pending_reader_cancels_and_late_bytes_are_ignored,
            stale_headers_cancel_unused_response,
            invalid_raw_draft_and_field_feedback_survive,
            accepted_file_confirmation_and_exact_values_survive,
            rejected_file_feedback_is_not_dismissed,
            different_model_file_keeps_confirmation_through_retry,
            rejected_shared_link_explanation_returns_after_retry,
            edited_shared_link_keeps_newer_feedback_and_focus,
            rapid_retries_keep_only_latest_response,
            custom_build_supersedes_pending_retry,
            model_switch_discards_pending_retry,
            reference_assembly_recovers_without_printable_stl,
            mobile_keyboard_retry_restores_reachable_focus,
        ):
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                check(page)
                assert not errors, errors
                passed.append(check.__name__)
                print("PASS", check.__name__, flush=True)
            except Exception:
                failures.append({"check": check.__name__, "error": traceback.format_exc()})
                print("FAIL", check.__name__, failures[-1]["error"], flush=True)
            finally:
                page.close()
        browser.close()
    report = {"base": BASE, "passed": passed, "failures": failures}
    (ROOT / "review/cloud_original_retry_ui_validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
