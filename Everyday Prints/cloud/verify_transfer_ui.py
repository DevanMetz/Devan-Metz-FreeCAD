"""Verify streamed file limits and recovery using real exported CAD fixtures.

The compiled frontend receives controlled browser ReadableStreams. Oversized
streams offer more data than the reader should consume; pending streams exercise
actual cancellation rather than only ignoring a late HTTP response. Invalid
headers must be rejected before consuming a stalled body, and discarded late
responses must release unused streams without changing newer UI state.
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

STREAMS = """window.transferFault = null;
window.transferStats = [];
const originalFetch = window.fetch;
window.fetch = async (...args) => {
  const response = await originalFetch(...args);
  const url = String(args[0]);
  const target = url.includes('/api/generate')
    ? (JSON.parse(args[1].body).format === 'cad' ? 'cad' : 'preview')
    : (url.endsWith('/models/parts_tray.stl') ? 'original' : null);
  const fault = window.transferFault;
  if (!fault || fault.target !== target) return response;
  window.transferFault = null;
  const stats = { target, mode: fault.mode, pulls: 0, cancelled: 0 };
  window.transferStats.push(stats);
  if (fault.mode === 'late-error') {
    const bytes = await response.arrayBuffer();
    window.deferFileBody(response, bytes, () => new Promise(resolve => { window.releaseErrorBody = resolve; }));
    const getReader = response.body.getReader;
    response.body.getReader = () => {
      const reader = getReader();
      return {
        read: () => { stats.pulls++; return reader.read(); },
        cancel: async () => { stats.cancelled++; await reader.cancel(); },
        releaseLock: () => { stats.released = true; reader.releaseLock(); }
      };
    };
    return response;
  }
  const headers = new Headers(response.headers);
  headers.set('Content-Length', '1');
  let bytes, shared, offset = 0;
  if (['chunks', 'reused-chunks', 'empty-prefix'].includes(fault.mode)) {
    bytes = new Uint8Array(await response.arrayBuffer());
    if (fault.mode === 'reused-chunks') shared = new Uint8Array(fault.chunkBytes || 4096);
  }
  else await response.body.cancel();
  const stream = fault.mode === 'missing' ? null : new ReadableStream({
    pull(controller) {
      stats.pulls++;
      if (fault.mode === 'oversize') {
        if (stats.pulls <= 6) controller.enqueue(new Uint8Array(2 * 1024 * 1024));
        else controller.close();
      } else if (fault.mode === 'problem-oversize') {
        if (stats.pulls <= 6) controller.enqueue(new Uint8Array(4096));
        else controller.close();
      } else if (fault.mode === 'interrupted') {
        if (stats.pulls === 1) controller.enqueue(new Uint8Array(4));
        else controller.error(new TypeError('Controlled connection failure'));
      } else if (fault.mode === 'pending') {
        if (stats.pulls === 1) controller.enqueue(new Uint8Array(4));
      } else if (fault.mode === 'empty-prefix' && stats.pulls <= 3) {
        controller.enqueue(new Uint8Array());
      } else if (bytes) {
        if (offset === bytes.length) controller.close();
        else {
          const end = Math.min(offset + (fault.chunkBytes || shared?.length || 16384), bytes.length);
          if (shared) {
            shared.set(bytes.subarray(offset, end));
            controller.enqueue(shared.subarray(0, end - offset));
          } else controller.enqueue(bytes.slice(offset, end));
          offset = end;
        }
      } else controller.close();
    },
    cancel() { stats.cancelled++; if (fault.cancelNeverFinishes) return new Promise(() => {}); }
  }, { highWaterMark: 0 });
  const result = new Response(stream, { status: response.status, headers });
  window.lastFaultResponse = result;
  result.arrayBuffer = () => { throw new Error('The app bypassed the streamed reader'); };
  return result;
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

        def setup(page, open_model=True, response_faults=None):
            page.add_init_script(DEFERRED_BODY + STREAMS)
            problems = {}

            def generate(route):
                payload = route.request.post_data_json
                problem = problems.pop("cad" if payload.get("format") == "cad" else "preview", None)
                if problem is not None:
                    route.fulfill(status=503, body=problem, content_type="application/json")
                    return
                archive, metadata, mesh = custom if payload["parameters"]["length"] == 180.5 else original
                cad = payload.get("format") == "cad"
                if not cad:
                    metadata = {**metadata, "format": "stl", "file_sha256": metadata["mesh_sha256"]}
                override = response_faults.pop(0) if response_faults else {}
                metadata = {**metadata, **override.get("metadata", {})}
                response_headers = headers(metadata, override.get("content_type", "application/zip" if cad else "model/stl"))
                if "raw_metadata" in override:
                    response_headers["X-Model-Metadata"] = override["raw_metadata"]
                route.fulfill(body=archive if cad else mesh, headers=response_headers)

            page.route("**/api/generate", generate)
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            if open_model:
                page.locator('[data-model="parts_tray"]').click()
                ready(page)
            return problems

        def ready(page):
            page.wait_for_function("() => !document.querySelector('#download-cad').disabled")

        def fault(page, target, mode, **options):
            return page.evaluate("value => { const index = window.transferStats.length; window.transferFault = value; return index; }", dict(target=target, mode=mode, **options))

        def build(page, length="180.5"):
            page.locator('[data-parameter="length"]').fill(length)
            page.locator("#rebuild").click()

        def failed(page, text):
            page.wait_for_function("text => { const message = document.querySelector('#form-message'); return message.classList.contains('error') && message.textContent.includes(text); }", arg=text)
            assert page.locator("#rebuild").is_enabled()
            assert page.locator("#stop-build").is_hidden()

        def stats(page):
            return page.evaluate("window.transferStats.at(-1)")

        def download(page, button="download"):
            with page.expect_download() as event:
                page.locator("#" + button).click()
            return Path(event.value.path()).read_bytes()

        def hold_headers(page):
            page.evaluate("""() => {
              const fetchBeforeHold = window.fetch;
              window.fetch = async (...args) => {
                const response = await fetchBeforeHold(...args);
                if (String(args[0]).includes('/api/generate')) {
                  window.fetch = fetchBeforeHold;
                  await new Promise(resolve => { window.releaseHeldHeaders = resolve; });
                }
                return response;
              };
            }""")

        def held(page):
            page.wait_for_function("() => typeof window.releaseHeldHeaders === 'function'")
            return page.evaluate("window.transferStats.length - 1")

        def release_headers(page, index):
            page.evaluate("window.releaseHeldHeaders()")
            page.wait_for_function("index => window.transferStats[index].cancelled === 1", arg=index)
            assert page.evaluate("index => window.transferStats[index].pulls", index) == 0

        def oversized_preview_retains_verified_mesh(page):
            setup(page)
            fault(page, "preview", "oversize")
            build(page)
            failed(page, "8 MiB")
            assert stats(page)["pulls"] == 5 and stats(page)["cancelled"] == 1, stats(page)
            assert page.locator("#model-size").inner_text() == "150 × 100 × 24"
            assert page.locator('[data-parameter="length"]').input_value() == "180.5"
            assert page.locator("#download").is_disabled()
            assert page.locator("#download-cad").is_disabled()
            page.locator('[data-parameter="length"]').fill("150")
            assert download(page) == (CLOUD / "public/models/parts_tray.stl").read_bytes()
            build(page)
            ready(page)
            assert download(page) == custom[2]
            page.screenshot(path=str(ROOT / "review/cloud_transfer_recovery.png"))

        def oversized_cad_allows_retry(page):
            setup(page)
            build(page)
            ready(page)
            fault(page, "cad", "oversize")
            page.locator("#download-cad").click()
            failed(page, "8 MiB")
            assert stats(page)["pulls"] == 5 and stats(page)["cancelled"] == 1, stats(page)
            assert download(page) == custom[2]
            assert download(page, "download-cad") == custom[0]

        def interrupted_preview_allows_retry(page):
            setup(page)
            fault(page, "preview", "interrupted")
            build(page)
            failed(page, "interrupted")
            assert page.locator("#model-size").inner_text() == "150 × 100 × 24"
            assert page.locator("#download").is_disabled()
            build(page)
            ready(page)
            assert download(page) == custom[2]

        def empty_cad_keeps_preview_and_recovers(page):
            setup(page)
            build(page)
            ready(page)
            for mode in ("empty", "missing"):
                fault(page, "cad", mode)
                page.locator("#download-cad").click()
                failed(page, "empty")
                assert download(page) == custom[2]
                assert page.locator("#download-cad").is_enabled()
            assert download(page, "download-cad") == custom[0]

        def oversized_original_blocks_unverified_downloads(page):
            setup(page, open_model=False)
            fault(page, "original", "oversize")
            page.locator('[data-model="parts_tray"]').click()
            failed(page, "8 MiB")
            assert stats(page)["pulls"] == 5 and stats(page)["cancelled"] == 1, stats(page)
            assert page.locator("#download").is_disabled()
            assert page.locator("#download-cad").is_disabled()
            assert page.locator("#fallback-image").is_visible()
            assert page.locator("#mesh-status").inner_text() == "Preview unavailable"
            build(page, "150")
            ready(page)
            assert download(page) == original[2]

        def stop_cancels_pending_stream_and_allows_retry(page):
            setup(page)
            fault(page, "preview", "pending")
            build(page)
            page.wait_for_function("() => window.transferStats.at(-1)?.pulls === 2")
            page.locator("#stop-build").click()
            page.wait_for_function("() => window.transferStats.at(-1).cancelled === 1")
            assert page.locator("#rebuild").is_enabled()
            assert page.locator("#stop-build").is_hidden()
            assert page.locator("#model-size").inner_text() == "150 × 100 × 24"
            assert page.locator('[data-parameter="length"]').input_value() == "180.5"
            assert page.locator("#download").is_disabled()
            build(page)
            ready(page)
            assert download(page) == custom[2]

        def chunked_files_match_verified_cad(page):
            setup(page)
            fault(page, "preview", "chunks")
            build(page)
            ready(page)
            assert stats(page)["pulls"] > 1 and stats(page)["cancelled"] == 0, stats(page)
            assert download(page) == custom[2]
            fault(page, "cad", "chunks")
            assert download(page, "download-cad") == custom[0]
            assert stats(page)["pulls"] > 1 and stats(page)["cancelled"] == 0, stats(page)
            assert page.locator("#model-size").inner_text() == "180.5 × 100 × 24"

        def largest_original_preview_and_stl(page):
            setup(page, open_model=False)
            largest = max((CLOUD / "public/models").glob("*.stl"), key=lambda path: path.stat().st_size)
            assert 4 * 1024 * 1024 < largest.stat().st_size <= 8 * 1024 * 1024
            page.locator(f'[data-model="{largest.stem}"]').click()
            ready(page)
            assert download(page) == largest.read_bytes()

        def malformed_preview_errors_preserve_draft_and_allow_retry(page):
            problems = setup(page)
            downloads = []
            page.on("download", lambda item: downloads.append(item))
            for body in ("null", "[]", "{", "<html>Unavailable</html>", json.dumps({"error": {"message": "Unavailable"}}), json.dumps({"error": "A" * 513})):
                problems["preview"] = body
                build(page)
                failed(page, "The CAD service could not finish this build. Try again.")
                assert page.locator("#model-size").inner_text() == "150 × 100 × 24"
                assert page.locator("#param-length").input_value() == "180.5"
                assert page.locator("#download").is_disabled() and page.locator("#download-cad").is_disabled()
                assert not downloads
            build(page)
            ready(page)
            assert download(page) == custom[2]

        def malformed_cad_errors_preserve_verified_downloads(page):
            problems = setup(page)
            build(page)
            ready(page)
            downloads = []
            page.on("download", lambda item: downloads.append(item))
            for body in ("null", "", "not JSON", json.dumps({"error": 17}), json.dumps({"error": []}), json.dumps({"error": " \n "})):
                problems["cad"] = body
                page.locator("#download-cad").click()
                failed(page, "The CAD download could not be built. Try again.")
                assert page.locator("#model-size").inner_text() == "180.5 × 100 × 24"
                assert page.locator("#param-length").input_value() == "180.5"
                assert page.locator("#download").is_enabled() and page.locator("#download-cad").is_enabled()
                assert not downloads
            assert download(page) == custom[2]
            assert download(page, "download-cad") == custom[0]

        def useful_service_errors_and_split_utf8_remain_readable(page):
            problems = setup(page)
            build(page)
            ready(page)
            detail = "Vérifiez les dimensions du modèle."
            problems["cad"] = json.dumps({"error": f"  {detail}\n"}, ensure_ascii=False)
            fault(page, "cad", "chunks", chunkBytes=1)
            page.locator("#download-cad").click()
            failed(page, detail)
            assert page.locator("#form-message").inner_text() == detail
            assert stats(page)["pulls"] > 1 and stats(page)["cancelled"] == 0
            assert page.evaluate("!window.lastFaultResponse.body.locked")
            problems["preview"] = json.dumps({"error": "Clearance must be positive."})
            build(page)
            failed(page, "Clearance must be positive.")
            assert page.locator("#download").is_enabled()
            assert download(page) == custom[2]
            assert download(page, "download-cad") == custom[0]

        def oversized_error_bodies_cancel_at_small_limit_and_retry(page):
            problems = setup(page)
            build(page)
            ready(page)
            for target, text in (("preview", "The CAD service could not finish this build."), ("cad", "The CAD download could not be built.")):
                problems[target] = json.dumps({"error": "Unavailable"})
                fault(page, target, "problem-oversize", cancelNeverFinishes=True)
                if target == "preview":
                    build(page)
                else:
                    page.locator("#download-cad").click()
                failed(page, text)
                assert stats(page)["pulls"] == 5 and stats(page)["cancelled"] == 1, stats(page)
                assert page.evaluate("!window.lastFaultResponse.body.locked")
                assert page.locator("#model-size").inner_text() == "180.5 × 100 × 24"
                assert download(page) == custom[2]
                if target == "preview":
                    build(page)
                    ready(page)
            assert download(page, "download-cad") == custom[0]

        def interrupted_error_bodies_leave_retry_controls_ready(page):
            problems = setup(page)
            build(page)
            ready(page)
            for target, text in (("preview", "The CAD service could not finish this build."), ("cad", "The CAD download could not be built.")):
                problems[target] = json.dumps({"error": "Unavailable"})
                fault(page, target, "interrupted")
                if target == "preview":
                    build(page)
                else:
                    page.locator("#download-cad").click()
                failed(page, text)
                assert stats(page)["pulls"] == 2 and stats(page)["cancelled"] == 0, stats(page)
                assert page.evaluate("!window.lastFaultResponse.body.locked")
                assert page.locator("#param-length").input_value() == "180.5"
                assert download(page) == custom[2]
                if target == "preview":
                    build(page)
                    ready(page)
            assert download(page, "download-cad") == custom[0]

        def stopped_error_body_keeps_stop_and_rejects_late_bytes(page):
            page.set_viewport_size({"width": 390, "height": 844})
            problems = setup(page)
            build(page)
            ready(page)
            problems["cad"] = json.dumps({"error": "Old service failure"})
            fault(page, "cad", "late-error")
            downloads = []
            page.on("download", lambda item: downloads.append(item))
            page.locator("#download-cad").click()
            page.wait_for_function("() => typeof window.releaseErrorBody === 'function'")
            assert page.locator("#stop-build").is_visible()
            page.locator("#stop-build").focus()
            page.locator("#stop-build").press("Enter")
            assert stats(page)["cancelled"] == 1
            page.wait_for_function("() => window.transferStats.at(-1).released === true")
            assert "Stopped waiting." in page.locator("#form-message").inner_text()
            assert page.locator("#rebuild").is_enabled() and page.locator("#download-cad").is_enabled()
            assert not downloads
            page.locator("#form-message").scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / "review/cloud_error_response_mobile.png"))
            assert download(page, "download-cad") == custom[0]
            before = page.locator("#form-message").inner_text()
            page.evaluate("window.releaseErrorBody()")
            page.wait_for_function("() => window.transferStats.at(-1).released === true")
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            assert page.locator("#form-message").inner_text() == before
            assert page.locator("#stop-build").is_hidden()
            assert len(downloads) == 1
            assert download(page) == custom[2]

        def stalled_error_details_recover_after_five_seconds(page):
            page.clock.install()
            problems = setup(page)
            build(page)
            ready(page)
            for target, text in (("preview", "The CAD service could not finish this build."), ("cad", "The CAD download could not be built.")):
                # Keep browser scheduling delays out of this five-second deadline.
                page.clock.pause_at(page.evaluate("Date.now()") / 1000 + 1)
                try:
                    problems[target] = json.dumps({"error": "Unavailable"})
                    index = fault(page, target, "pending")
                    if target == "preview":
                        build(page)
                    else:
                        page.locator("#download-cad").click()
                    page.wait_for_function("index => window.transferStats[index]?.pulls === 2", arg=index)
                    observed = page.locator("#form-message").inner_text()
                    assert "Reading service details" in observed, (target, observed, stats(page))
                    assert page.locator("#rebuild").is_disabled() and page.locator("#stop-build").is_visible()
                    if target == "cad":
                        assert "Reading service details" in page.locator("#download-cad").inner_text()
                    page.clock.fast_forward(4999)
                    assert page.locator("#rebuild").is_disabled() and stats(page)["cancelled"] == 0
                    page.clock.fast_forward(2)
                    failed(page, text)
                    page.wait_for_function("() => !window.lastFaultResponse.body.locked")
                    assert stats(page)["cancelled"] == 1
                    assert page.locator("#param-length").input_value() == "180.5"
                    before = page.locator("#form-message").inner_text()
                    page.clock.fast_forward(15000)
                    assert page.locator("#form-message").inner_text() == before
                finally:
                    page.clock.resume()
                assert download(page) == custom[2]
                if target == "preview":
                    build(page)
                    ready(page)
            assert download(page, "download-cad") == custom[0]

        def useful_delayed_error_details_arrive_before_the_short_deadline(page):
            page.clock.install()
            problems = setup(page)
            build(page)
            ready(page)
            detail = "Please wait a minute before building more models."
            problems["cad"] = json.dumps({"error": detail})
            fault(page, "cad", "late-error")
            page.locator("#download-cad").click()
            page.wait_for_function("() => typeof window.releaseErrorBody === 'function'")
            assert "Reading service details" in page.locator("#form-message").inner_text()
            page.clock.fast_forward(2000)
            page.evaluate("window.releaseErrorBody()")
            failed(page, detail)
            assert stats(page)["cancelled"] == 0 and stats(page)["released"]
            page.clock.fast_forward(20000)
            assert page.locator("#form-message").inner_text() == detail
            assert download(page, "download-cad") == custom[0]

        def error_deadline_releases_uncooperative_body_and_keeps_new_retry(page):
            page.set_viewport_size({"width": 390, "height": 844})
            page.clock.install()
            problems = setup(page)
            build(page)
            ready(page)
            problems["cad"] = json.dumps({"error": "Old service failure"})
            fault(page, "cad", "late-error")
            page.locator("#download-cad").click()
            page.wait_for_function("() => typeof window.releaseErrorBody === 'function'")
            page.clock.fast_forward(5001)
            failed(page, "The CAD download could not be built. Try again.")
            assert stats(page)["cancelled"] == 1 and stats(page)["released"]
            assert page.locator("#download").is_enabled() and page.locator("#download-cad").is_enabled()
            page.locator("#form-message").scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / "review/cloud_error_wait_mobile.png"))
            downloads = []
            page.on("download", lambda item: downloads.append(item))
            assert download(page, "download-cad") == custom[0]
            before = page.locator("#form-message").inner_text()
            page.evaluate("window.releaseErrorBody()")
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            assert page.locator("#form-message").inner_text() == before
            assert len(downloads) == 1 and page.locator("#stop-build").is_hidden()
            assert download(page) == custom[2]

        def failed_first_preview_reports_details_then_recovers_without_files(page):
            page.clock.install()
            problems = setup(page, open_model=False)
            page.route("**/models/parts_tray.stl", lambda route: route.fulfill(status=503, body="Controlled unavailable original"))
            page.locator('[data-model="parts_tray"]').click()
            page.wait_for_function("() => document.querySelector('#preview-loading').hidden && document.querySelector('#mesh-status').textContent === 'Preview unavailable'")
            problems["preview"] = json.dumps({"error": "Unavailable"})
            fault(page, "preview", "pending")
            build(page)
            page.wait_for_function("() => window.transferStats.at(-1)?.pulls === 2")
            assert page.locator("#preview-loading").is_visible()
            assert page.locator("#preview-loading").inner_text() == "Reading service details…"
            assert "Reading service details" in page.locator("#form-message").inner_text()
            page.clock.fast_forward(5001)
            failed(page, "The CAD service could not finish this build. Try again.")
            assert page.locator("#preview-loading").is_hidden()
            assert page.locator("#fallback-image").is_visible()
            assert page.locator("#download").is_disabled() and page.locator("#download-cad").is_disabled()
            assert page.locator("#param-length").input_value() == "180.5"
            assert stats(page)["cancelled"] == 1
            build(page)
            ready(page)
            assert download(page) == custom[2]

        def invalid_preview_headers_cancel_before_read(page):
            overrides = []
            setup(page, response_faults=overrides)
            for override in (
                {"metadata": {"model": "cable_comb"}},
                {"metadata": {"units": "inch"}},
                {"metadata": {"parameters": {"length": 190.5}}},
                {"metadata": {"bounds_mm": [0, 100, 24]}},
                {"metadata": {"printable": False}},
                {"metadata": {"format": "cad"}},
                {"metadata": {"mesh_sha256": None}},
                {"metadata": {"mesh_sha256": "bad hash"}},
                {"raw_metadata": "not-json"},
                {"content_type": "text/html"},
            ):
                overrides.append(override)
                fault(page, "preview", "pending", cancelNeverFinishes=True)
                build(page)
                failed(page, "")
                assert stats(page)["pulls"] == 0 and stats(page)["cancelled"] == 1, (override, stats(page))
                assert not page.evaluate("window.lastFaultResponse.body.locked")
                assert page.locator("#param-length").input_value() == "180.5"
                assert page.locator("#model-size").inner_text() == "150 × 100 × 24"
                assert page.locator("#download").is_disabled()
            build(page)
            ready(page)
            assert download(page) == custom[2]

        def invalid_cad_headers_cancel_before_read(page):
            overrides = []
            setup(page, response_faults=overrides)
            build(page)
            ready(page)
            for override in (
                {"metadata": {"model": "cable_comb"}},
                {"metadata": {"units": "inch"}},
                {"metadata": {"format": "stl"}},
                {"metadata": {"mesh_sha256": "0" * 64}},
                {"metadata": {"file_sha256": None}},
                {"metadata": {"file_sha256": "bad hash"}},
                {"raw_metadata": "%invalid"},
                {"content_type": "text/html"},
            ):
                overrides.append(override)
                fault(page, "cad", "pending", cancelNeverFinishes=True)
                page.locator("#download-cad").click()
                failed(page, "")
                assert stats(page)["pulls"] == 0 and stats(page)["cancelled"] == 1, (override, stats(page))
                assert not page.evaluate("window.lastFaultResponse.body.locked")
                assert page.locator("#download").is_enabled() and page.locator("#download-cad").is_enabled()
            assert download(page) == custom[2]
            assert download(page, "download-cad") == custom[0]

        def invalid_first_preview_recovers_with_original_retry(page):
            overrides = []
            setup(page, open_model=False, response_faults=overrides)
            fault(page, "original", "pending")
            page.locator('[data-model="parts_tray"]').click()
            page.wait_for_function("() => window.transferStats.at(-1)?.pulls === 2")
            overrides.append({"metadata": {"units": "inch"}})
            fault(page, "preview", "pending", cancelNeverFinishes=True)
            build(page)
            failed(page, "model details")
            assert stats(page)["pulls"] == 0 and stats(page)["cancelled"] == 1
            assert page.locator("#retry-original").is_enabled()
            assert page.locator("#fallback-image").is_visible()
            assert "unavailable" in page.locator(".viewer-help").inner_text()
            page.locator("#retry-original").click()
            page.wait_for_function("() => document.querySelector('#original-recovery').hidden")
            assert page.locator("#param-length").input_value() == "180.5" and page.locator("#download").is_disabled()
            build(page)
            ready(page)
            assert download(page) == custom[2]

        def stopped_preview_discards_late_headers(page):
            setup(page)
            hold_headers(page)
            fault(page, "preview", "pending", cancelNeverFinishes=True)
            build(page)
            index = held(page)
            page.locator("#stop-build").click()
            before = page.locator("#form-message").inner_text()
            release_headers(page, index)
            assert page.locator("#form-message").inner_text() == before
            assert page.locator("#param-length").input_value() == "180.5"
            build(page)
            ready(page)
            assert download(page) == custom[2]

        def stopped_cad_discards_late_service_failure(page):
            problems = setup(page)
            build(page)
            ready(page)
            problems["cad"] = '{"error":"Late service failure"}'
            hold_headers(page)
            fault(page, "cad", "pending", cancelNeverFinishes=True)
            page.locator("#download-cad").click()
            index = held(page)
            page.locator("#stop-build").click()
            before = page.locator("#form-message").inner_text()
            release_headers(page, index)
            assert page.locator("#form-message").inner_text() == before
            assert download(page) == custom[2]
            assert download(page, "download-cad") == custom[0]

        def navigation_discards_late_preview_headers(page):
            setup(page)
            hold_headers(page)
            fault(page, "preview", "pending", cancelNeverFinishes=True)
            build(page)
            index = held(page)
            page.locator("#close-editor").click()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            page.locator('[data-model="cable_comb"]').click()
            ready(page)
            before = page.locator("#form-message").inner_text()
            release_headers(page, index)
            assert page.locator("#form-message").inner_text() == before
            assert download(page) == (CLOUD / "public/models/cable_comb.stl").read_bytes()

        def obsolete_cad_headers_leave_new_retry_waiting(page):
            setup(page)
            build(page)
            ready(page)
            hold_headers(page)
            fault(page, "cad", "pending", cancelNeverFinishes=True)
            page.locator("#download-cad").click()
            index = held(page)
            page.locator("#stop-build").click()
            fault(page, "cad", "pending")
            page.locator("#download-cad").click()
            page.wait_for_function("() => window.transferStats.at(-1)?.pulls === 2")
            before = page.locator("#form-message").inner_text()
            release_headers(page, index)
            assert page.locator("#form-message").inner_text() == before
            assert page.locator("#rebuild").is_disabled() and page.locator("#stop-build").is_visible()
            assert stats(page)["cancelled"] == 0
            page.locator("#stop-build").click()
            assert stats(page)["cancelled"] == 1
            assert download(page, "download-cad") == custom[0]

        def first_preview_failure_keeps_new_invalid_mobile_draft(page):
            page.set_viewport_size({"width": 390, "height": 844})
            overrides = []
            setup(page, open_model=False, response_faults=overrides)
            fault(page, "original", "pending")
            page.locator('[data-model="parts_tray"]').click()
            page.wait_for_function("() => window.transferStats.at(-1)?.pulls === 2")
            overrides.append({"metadata": {"units": "inch"}})
            hold_headers(page)
            fault(page, "preview", "pending", cancelNeverFinishes=True)
            build(page)
            index = held(page)
            page.locator("#param-length").fill("")
            release_headers(page, index)
            failed(page, "model details")
            assert page.locator("#param-length").input_value() == ""
            assert page.locator("#param-length").get_attribute("aria-invalid") == "true"
            assert page.locator("#mesh-status").inner_text() == "Fix invalid dimensions"
            assert page.locator("#download").is_disabled() and page.locator("#download-cad").is_disabled()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator("#form-message").scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / "review/cloud_response_discard_mobile.png"))
            build(page)
            ready(page)
            assert download(page) == custom[2]

        def reused_original_chunks_keep_exact_catalog_mesh(page):
            setup(page, open_model=False)
            fault(page, "original", "reused-chunks", chunkBytes=97)
            page.locator('[data-model="parts_tray"]').click()
            ready(page)
            assert download(page) == (CLOUD / "public/models/parts_tray.stl").read_bytes()
            assert page.locator("#transfer-status").is_hidden()

        def reused_preview_chunks_verify_exact_custom_mesh(page):
            setup(page)
            fault(page, "preview", "reused-chunks", chunkBytes=113)
            build(page)
            ready(page)
            assert download(page) == custom[2]
            assert page.locator("#transfer-status").is_hidden()
            assert not page.locator("#form-message").evaluate("message => message.classList.contains('error')")

        def reused_cad_chunks_deliver_exact_verified_archive(page):
            setup(page)
            build(page)
            ready(page)
            fault(page, "cad", "reused-chunks", chunkBytes=257)
            assert download(page, "download-cad") == custom[0]
            assert page.locator("#transfer-status").is_hidden()

        def reused_error_chunks_keep_split_utf8_details(page):
            problems = setup(page)
            detail = "Controlled café · Ø cable · 漢字 🌿"
            problems["preview"] = json.dumps({"error": detail}, ensure_ascii=False)
            fault(page, "preview", "reused-chunks", chunkBytes=3)
            build(page)
            failed(page, detail)
            assert page.locator("#form-message").inner_text() == detail
            assert page.locator("#param-length").input_value() == "180.5"
            assert page.locator("#transfer-status").is_hidden()
            build(page)
            ready(page)
            assert download(page) == custom[2]

        def empty_chunks_preserve_the_following_verified_file(page):
            setup(page, open_model=False)
            fault(page, "original", "empty-prefix", chunkBytes=4096)
            page.locator('[data-model="parts_tray"]').click()
            ready(page)
            assert download(page) == (CLOUD / "public/models/parts_tray.stl").read_bytes()
            assert page.locator("#transfer-status").is_hidden()

        def misleading_preview_types_cancel_before_read(page):
            overrides = []
            setup(page, response_faults=overrides)
            for kind in ('text/plain; filetype="model/stl"', 'model/stl+json',
                         'application/x-model/stl', 'model/stl, text/html'):
                overrides.append({"content_type": kind})
                fault(page, "preview", "pending", cancelNeverFinishes=True)
                build(page)
                failed(page, "unreadable preview")
                assert stats(page)["pulls"] == 0 and stats(page)["cancelled"] == 1, (kind, stats(page))
                assert not page.evaluate("window.lastFaultResponse.body.locked")
                assert page.locator("#param-length").input_value() == "180.5"
                assert page.locator("#download").is_disabled() and page.locator("#transfer-status").is_hidden()
            build(page)
            ready(page)
            assert download(page) == custom[2]

        def misleading_cad_types_cancel_before_read(page):
            overrides = []
            setup(page, response_faults=overrides)
            build(page)
            ready(page)
            downloads = []
            page.on("download", lambda item: downloads.append(item))
            for kind in ('text/plain; filetype="application/zip"', 'application/zip+json',
                         'application/zip-compressed', 'application/zip, text/html'):
                overrides.append({"content_type": kind})
                fault(page, "cad", "pending", cancelNeverFinishes=True)
                page.locator("#download-cad").click()
                failed(page, "unreadable download")
                assert stats(page)["pulls"] == 0 and stats(page)["cancelled"] == 1, (kind, stats(page))
                assert not page.evaluate("window.lastFaultResponse.body.locked")
                assert page.locator("#download").is_enabled() and page.locator("#download-cad").is_enabled()
                assert page.locator("#transfer-status").is_hidden() and not downloads
            assert download(page) == custom[2]
            assert download(page, "download-cad") == custom[0]

        def preview_type_case_and_parameters_preserve_exact_file(page):
            overrides = []
            setup(page, response_faults=overrides)
            for kind in ('MoDeL/StL', 'MODEL/STL; name="preview.stl"',
                         ' model/stl ; name="with;semicolon.stl" '):
                overrides.append({"content_type": kind})
                fault(page, "preview", "chunks", chunkBytes=1024)
                build(page)
                ready(page)
                assert download(page) == custom[2]
                assert stats(page)["pulls"] > 1 and stats(page)["cancelled"] == 0, (kind, stats(page))
                assert not overrides and page.locator("#transfer-status").is_hidden()

        def cad_type_case_and_parameters_preserve_exact_archive(page):
            overrides = []
            setup(page, response_faults=overrides)
            for kind in ('Application/Zip', 'APPLICATION/ZIP; name="download.zip"',
                         ' application/zip ; name="with;semicolon.zip" '):
                build(page)
                ready(page)
                overrides.append({"content_type": kind})
                fault(page, "cad", "chunks", chunkBytes=1024)
                assert download(page, "download-cad") == custom[0]
                assert stats(page)["pulls"] > 1 and stats(page)["cancelled"] == 0, (kind, stats(page))
                assert not overrides and page.locator("#transfer-status").is_hidden()

        for test in (oversized_preview_retains_verified_mesh, oversized_cad_allows_retry,
                     interrupted_preview_allows_retry, empty_cad_keeps_preview_and_recovers,
                     oversized_original_blocks_unverified_downloads,
                     stop_cancels_pending_stream_and_allows_retry, chunked_files_match_verified_cad,
                     largest_original_preview_and_stl,
                     malformed_preview_errors_preserve_draft_and_allow_retry,
                     malformed_cad_errors_preserve_verified_downloads,
                     useful_service_errors_and_split_utf8_remain_readable,
                     oversized_error_bodies_cancel_at_small_limit_and_retry,
                     interrupted_error_bodies_leave_retry_controls_ready,
                     stopped_error_body_keeps_stop_and_rejects_late_bytes,
                     stalled_error_details_recover_after_five_seconds,
                     useful_delayed_error_details_arrive_before_the_short_deadline,
                     error_deadline_releases_uncooperative_body_and_keeps_new_retry,
                     failed_first_preview_reports_details_then_recovers_without_files,
                     invalid_preview_headers_cancel_before_read,
                     invalid_cad_headers_cancel_before_read,
                     invalid_first_preview_recovers_with_original_retry,
                     stopped_preview_discards_late_headers,
                     stopped_cad_discards_late_service_failure,
                     navigation_discards_late_preview_headers,
                     obsolete_cad_headers_leave_new_retry_waiting,
                     first_preview_failure_keeps_new_invalid_mobile_draft,
                     reused_original_chunks_keep_exact_catalog_mesh,
                     reused_preview_chunks_verify_exact_custom_mesh,
                     reused_cad_chunks_deliver_exact_verified_archive,
                     reused_error_chunks_keep_split_utf8_details,
                     empty_chunks_preserve_the_following_verified_file,
                     misleading_preview_types_cancel_before_read,
                     misleading_cad_types_cancel_before_read,
                     preview_type_case_and_parameters_preserve_exact_file,
                     cad_type_case_and_parameters_preserve_exact_archive):
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            print(f"START {test.__name__}", flush=True)
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
        fixture_archive_sha256=hashlib.sha256(custom[0]).hexdigest(),
        transport="compiled assets and real CAD fixtures with controlled ReadableStreams" if OFFLINE else "local HTTP bridge with controlled ReadableStreams")
    (ROOT / "review/cloud_transfer_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert not failures, report


if __name__ == "__main__":
    main()
