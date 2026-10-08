"""Browser checks for delayed catalogs, malformed responses, and retry recovery."""
import json
import os
from pathlib import Path
import sys
import time
import traceback
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = "--offline" in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5178")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT.parent / ".cad-cache/browsers"))
CATALOG_LIMIT = 2 * 1024 * 1024


def main():
    passed, failures = [], []
    catalog = json.loads((CLOUD / "public/catalog.json").read_text(encoding="utf-8"))
    expected_categories = len({model["category"] for model in catalog["models"]}) + 1
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1080})
        context.set_default_timeout(10000)
        if OFFLINE:
            attach_assets(context)

        def pending_route(page, waiting):
            deadline = time.monotonic() + 10
            while not waiting and time.monotonic() < deadline:
                page.wait_for_timeout(50)
            assert waiting, "Catalog request was not intercepted"
            return waiting.pop(0)

        def controlled_catalog(page, mode):
            script = """(() => {
              const originalFetch = window.fetch.bind(window);
              const catalog = __CATALOG__;
              window.catalogTransfer = { next: '__MODE__', attempts: [] };
              function response(mode, stats) {
                const copy = structuredClone(catalog);
                if (mode === 'unicode') copy.models[0].title = 'Café – 工具';
                if (mode === 'invalid-utf8') copy.models[0].title = 'BAD_UTF8';
                let data = new TextEncoder().encode(JSON.stringify(copy));
                if (mode === 'invalid-utf8') {
                  const offset = new TextDecoder().decode(data).indexOf('BAD_UTF8');
                  data[offset] = 255;
                }
                if (mode === 'oversized' || mode === 'exact') {
                  const padded = new Uint8Array(2 * 1024 * 1024 + (mode === 'oversized' ? 1 : 0));
                  padded.fill(32); padded.set(data); data = padded;
                  if (mode === 'exact') { data.set([239, 187, 191]); data.set(new TextEncoder().encode(JSON.stringify(copy)), 3); }
                }
                stats.bytes = data.byteLength;
                let offset = 0;
                const borrowed = new Uint8Array(8192);
                const unicodeSplit = new TextEncoder().encode(JSON.stringify(copy).split('é')[0]).byteLength + 1;
                const stream = new ReadableStream({
                  start(controller) {
                    if (mode === 'stalled-body') {
                      controller.enqueue(data.subarray(0, 64)); offset = 64;
                    }
                  },
                  pull(controller) {
                    if (mode === 'stalled-body') {
                      stats.pendingBody = true;
                      return new Promise(resolve => {
                        stats.releaseBody = () => { controller.enqueue(data.subarray(offset)); controller.close(); resolve(); };
                      });
                    }
                    if (offset === data.byteLength) { controller.close(); return; }
                    if (mode === 'unicode') {
                      const count = Math.min(8192, data.byteLength - offset, offset === 0 ? unicodeSplit : Infinity);
                      borrowed.set(data.subarray(offset, offset + count)); offset += count;
                      controller.enqueue(borrowed.subarray(0, count));
                      return new Promise(resolve => setTimeout(resolve, 0));
                    }
                    controller.enqueue(data); offset = data.byteLength;
                  },
                });
                const result = new Response(stream, { headers: { 'Content-Type': 'application/json', 'Content-Length': '1' } });
                const getReader = stream.getReader.bind(stream);
                stream.getReader = () => {
                  const reader = getReader();
                  return {
                    read() { stats.reads++; return reader.read(); },
                    cancel() {
                      stats.cancelled++;
                      return mode === 'stalled-body' ? new Promise(() => {}) : reader.cancel();
                    },
                    releaseLock() { stats.released++; reader.releaseLock(); },
                  };
                };
                const cancel = stream.cancel.bind(stream);
                stream.cancel = () => { stats.unusedCancelled++; return mode === 'late-headers' ? new Promise(() => {}) : cancel(); };
                return result;
              }
              window.fetch = (input, options) => {
                if (input !== '/catalog.json') return originalFetch(input, options);
                const mode = window.catalogTransfer.next;
                const stats = { mode, reads: 0, cancelled: 0, released: 0, unusedCancelled: 0 };
                window.catalogTransfer.attempts.push(stats);
                if (mode === 'late-headers' || mode === 'held-headers') return new Promise(resolve => {
                  stats.releaseHeaders = () => resolve(response(mode, stats));
                });
                return Promise.resolve(response(mode, stats));
              };
            })();"""
            page.add_init_script(script.replace('__CATALOG__', json.dumps(catalog)).replace('__MODE__', mode))

        def failed_transfer(page):
            assert page.locator('#catalog-failure').is_visible()
            assert page.locator('#retry-catalog').is_enabled()
            assert page.locator('#catalog').get_attribute('aria-busy') == 'false'
            assert page.locator('.card').count() == 0

        def retry_controlled(page):
            page.evaluate("window.catalogTransfer.next = 'normal'")
            page.locator('#retry-catalog').click()
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")

        def delayed_search(page, errors):
            waiting = []
            page.route("**/catalog.json", lambda route: waiting.append(route))
            page.goto(BASE)
            route = pending_route(page, waiting)
            try:
                page.locator("#search").fill("phone stand")
                page.locator('[data-kind="print"]').click()
                assert not errors, errors
                assert page.locator("#catalog").get_attribute("aria-busy") == "true"
                assert page.locator("#catalog-loading").is_visible()
                assert page.locator("#empty").is_hidden()
            finally:
                route.fulfill(json=catalog)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 1")
            assert page.locator(".card").get_attribute("data-model") == "phone_stand"
            assert page.locator("#result-count").inner_text() == "1 model"
            assert page.locator("#catalog").get_attribute("aria-busy") == "false"
            assert page.locator("#catalog-loading").is_hidden()

        def retry_retains_filters(page, errors):
            attempts = []

            def respond(route):
                attempts.append(route.request.url)
                if len(attempts) == 1:
                    route.fulfill(status=503, json={"error": "Unavailable"})
                else:
                    route.fulfill(json=catalog)

            page.route("**/catalog.json", respond)
            page.goto(BASE)
            page.locator("#catalog-error").wait_for(state="visible")
            page.locator("#search").fill("soap")
            page.locator('[data-kind="assembly"]').click()
            assert not errors, errors
            page.locator("#retry-catalog").click()
            page.wait_for_function("() => document.querySelectorAll('.card').length === 1")
            assert page.locator(".card").get_attribute("data-model") == "soap_dish_assembly"
            assert page.locator("#search").input_value() == "soap"
            assert page.locator('[data-kind="assembly"]').get_attribute("aria-pressed") == "true"
            assert page.locator("#category option").count() == expected_categories
            assert page.locator("#catalog-error").is_hidden()
            assert page.locator("#retry-catalog").is_hidden()
            assert len(attempts) == 2
            page.screenshot(path=str(ROOT / "review/cloud_catalog_retry.png"), full_page=False)

        def interrupted_connection(page, errors):
            attempts = []

            def respond(route):
                attempts.append(route.request.url)
                if len(attempts) == 1:
                    route.abort("connectionfailed")
                else:
                    route.fulfill(json=catalog)

            page.route("**/catalog.json", respond)
            page.goto(BASE)
            page.locator("#catalog-error").wait_for(state="visible")
            assert page.locator("#catalog-error").inner_text() == "The library could not be loaded. Try again."
            assert page.locator("#empty").is_hidden()
            page.locator("#retry-catalog").click()
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            assert len(attempts) == 2

        def malformed_responses(page, errors):
            wrong_bounds = json.loads(json.dumps(catalog))
            wrong_bounds["models"][0]["bounds_mm"] = [150, None, 24]
            missing_part = json.loads(json.dumps(catalog))
            next(model for model in missing_part["models"] if model["kind"] == "assembly")["parts"] = ["missing_part"]
            replies = [
                "<!doctype html><title>Unavailable</title>",
                {"models": None},
                wrong_bounds,
                missing_part,
                catalog,
            ]
            attempts = []

            def respond(route):
                attempts.append(route.request.url)
                reply = replies.pop(0)
                if isinstance(reply, str):
                    route.fulfill(body=reply, content_type="text/html")
                else:
                    route.fulfill(json=reply)

            page.route("**/catalog.json", respond)
            page.goto(BASE)
            for _ in range(4):
                page.locator("#catalog-error").wait_for(state="visible")
                assert page.locator("#catalog-error").inner_text() == "The library could not be loaded. Try again."
                assert page.locator(".card").count() == 0, "Partial catalog became searchable"
                assert page.locator("#catalog").get_attribute("aria-busy") == "false"
                page.locator("#retry-catalog").click()
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            assert page.locator("#category option").count() == expected_categories
            assert len(attempts) == 5

        def shared_link_recovery(page, errors):
            attempts = []

            def respond(route):
                attempts.append(route.request.url)
                route.fulfill(status=503, json={}) if len(attempts) == 1 else route.fulfill(json=catalog)

            page.route("**/catalog.json", respond)
            url = BASE + "/?" + urlencode({"model": "parts_tray", "p": json.dumps({"length": 180})})
            page.goto(url)
            page.locator("#retry-catalog").click()
            page.wait_for_function("() => document.querySelector('#editor').open && document.querySelector('#preview-loading').hidden")
            assert page.locator('[data-parameter="length"]').input_value() == "180"
            assert page.locator("#download").is_disabled()
            assert "Shared dimensions loaded" in page.locator("#form-message").inner_text()

        def mobile_failure_and_recovery(page, errors):
            page.set_viewport_size({"width": 390, "height": 844})
            attempts = []

            def respond(route):
                attempts.append(route.request.url)
                route.fulfill(status=503, json={}) if len(attempts) == 1 else route.fulfill(json=catalog)

            page.route("**/catalog.json", respond)
            page.goto(BASE)
            page.locator("#catalog-error").wait_for(state="visible")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(ROOT / "review/cloud_catalog_failure_mobile.png"), full_page=True)
            page.locator("#retry-catalog").click()
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator('[data-kind="assembly"]').click()
            assert page.locator(".card").count() == 6

        def dynamic_counts(page, errors):
            subset = json.loads(json.dumps(catalog))
            subset["models"] = [model for model in subset["models"] if model["name"] in ("soap_dish_assembly", "soap_dish_tray", "soap_dish_insert")]
            page.route("**/catalog.json", lambda route: route.fulfill(json=subset))
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 3")
            assert page.locator("#result-count").inner_text() == "3 models"
            assert page.locator('[data-count="print"]').all_text_contents() == ["2", "2"]
            assert page.locator('[data-count="assembly"]').all_text_contents() == ["1", "1"]
            page.locator('[data-kind="assembly"]').click()
            assert page.locator(".card").count() == 1

        def stalled_request_timeout(page, errors):
            waiting = []
            page.route("**/catalog.json", lambda route: waiting.append(route))
            page.goto(BASE)
            route = pending_route(page, waiting)
            page.locator("#catalog-error").wait_for(state="visible", timeout=20000)
            assert page.locator("#catalog-loading").is_hidden()
            assert page.locator("#catalog").get_attribute("aria-busy") == "false"
            assert page.locator("#retry-catalog").is_enabled()
            route.fulfill(json=catalog)
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            assert page.locator(".card").count() == 0, "Timed-out catalog became visible after cancellation"
            page.unroute("**/catalog.json")
            page.locator("#retry-catalog").click()
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")

        def stalled_body_deadline_keeps_filters_and_new_retry(page, errors):
            controlled_catalog(page, 'stalled-body')
            page.clock.install()
            page.goto(BASE)
            page.wait_for_function('() => window.catalogTransfer.attempts[0]?.pendingBody')
            page.locator('#search').fill('phone')
            page.locator('[data-kind="print"]').click()
            page.clock.fast_forward(15001)
            failed_transfer(page)
            stats = page.evaluate('window.catalogTransfer.attempts[0]')
            assert stats['cancelled'] == stats['released'] == 1, stats
            page.evaluate("window.catalogTransfer.next = 'held-headers'")
            page.locator('#retry-catalog').click()
            page.wait_for_function('() => window.catalogTransfer.attempts.length === 2')
            page.evaluate('window.catalogTransfer.attempts[0].releaseBody()')
            page.evaluate('() => new Promise(resolve => setTimeout(resolve, 20))')
            assert page.locator('#catalog').get_attribute('aria-busy') == 'true'
            assert page.locator('#retry-catalog').is_disabled()
            assert page.locator('.card').count() == 0
            page.evaluate('window.catalogTransfer.attempts[1].releaseHeaders()')
            page.wait_for_function("() => document.querySelectorAll('.card').length === 1")
            assert page.locator('.card').get_attribute('data-model') == 'phone_stand'
            assert page.locator('#search').input_value() == 'phone'
            page.locator('.card').click()
            page.wait_for_function("() => !document.querySelector('#download').disabled")

        def late_headers_release_body_without_unlocking_retry(page, errors):
            controlled_catalog(page, 'late-headers')
            page.clock.install()
            page.goto(BASE)
            page.wait_for_function('() => window.catalogTransfer.attempts.length === 1')
            page.clock.fast_forward(15001)
            failed_transfer(page)
            page.evaluate("window.catalogTransfer.next = 'held-headers'")
            page.locator('#retry-catalog').click()
            page.wait_for_function('() => window.catalogTransfer.attempts.length === 2')
            page.evaluate('window.catalogTransfer.attempts[0].releaseHeaders()')
            page.wait_for_function('() => window.catalogTransfer.attempts[0].unusedCancelled === 1')
            assert page.evaluate('window.catalogTransfer.attempts[0].reads') == 0
            assert page.locator('#catalog').get_attribute('aria-busy') == 'true'
            assert page.locator('#retry-catalog').is_disabled()
            page.evaluate('window.catalogTransfer.attempts[1].releaseHeaders()')
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            assert len(page.evaluate('window.catalogTransfer.attempts')) == 2

        def oversized_body_keeps_shared_link_for_mobile_retry(page, errors):
            page.set_viewport_size({'width': 390, 'height': 844})
            controlled_catalog(page, 'oversized')
            url = BASE + '/?' + urlencode({'model': 'parts_tray', 'p': json.dumps({'length': 180.5}), 'from': 'saved'}) + '#library'
            page.goto(url)
            page.wait_for_function("() => document.querySelector('#catalog-loading').hidden")
            failed_transfer(page)
            assert page.url == url
            stats = page.evaluate('window.catalogTransfer.attempts[0]')
            assert stats['bytes'] == CATALOG_LIMIT + 1 and stats['reads'] == 1 and stats['cancelled'] == 1, stats
            assert not page.locator('#editor').evaluate('element => element.open')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(ROOT / 'review/cloud_catalog_transfer_mobile.png'), full_page=False)
            page.evaluate("window.catalogTransfer.next = 'normal'")
            page.locator('#retry-catalog').focus()
            page.keyboard.press('Enter')
            page.wait_for_function("() => document.querySelector('#editor').open && document.querySelector('#preview-loading').hidden")
            assert page.locator('[data-parameter="length"]').input_value() == '180.5'
            assert page.locator('#download').is_disabled()
            assert 'Shared dimensions loaded' in page.locator('#form-message').inner_text()

        def exact_limit_and_bom_catalog_load_completely(page, errors):
            controlled_catalog(page, 'exact')
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            assert page.evaluate('window.catalogTransfer.attempts[0].bytes') == CATALOG_LIMIT
            assert page.locator('#category option').count() == expected_categories
            assert page.locator('#catalog-failure').is_hidden()
            page.locator('[data-model="parts_tray"]').click()
            page.wait_for_function("() => !document.querySelector('#download').disabled")

        def borrowed_chunks_keep_split_utf8_catalog_text(page, errors):
            controlled_catalog(page, 'unicode')
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53", timeout=90000)
            first = catalog['models'][0]['name']
            assert page.locator(f'[data-model="{first}"] h3').text_content() == 'Café – 工具'
            page.locator('#search').fill('Café')
            assert page.locator('.card').count() == 1
            page.locator('.card').click()
            page.wait_for_function("() => !document.querySelector('#download').disabled")

        def invalid_utf8_cannot_publish_partial_catalog(page, errors):
            controlled_catalog(page, 'invalid-utf8')
            page.goto(BASE)
            page.wait_for_function("() => document.querySelector('#catalog-loading').hidden")
            failed_transfer(page)
            retry_controlled(page)
            assert page.locator('#category option').count() == expected_categories

        for test in (delayed_search, retry_retains_filters, interrupted_connection,
                     malformed_responses, shared_link_recovery, mobile_failure_and_recovery,
                     dynamic_counts, stalled_request_timeout,
                     stalled_body_deadline_keeps_filters_and_new_retry,
                     late_headers_release_body_without_unlocking_retry,
                     oversized_body_keeps_shared_link_for_mobile_retry,
                     exact_limit_and_bom_catalog_load_completely,
                     borrowed_chunks_keep_split_utf8_catalog_text,
                     invalid_utf8_cannot_publish_partial_catalog):
            errors = []
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                print(f"START {test.__name__}", flush=True)
                test(page, errors)
                assert not errors, errors
                passed.append(test.__name__)
                print(f"PASS {test.__name__}", flush=True)
            except Exception as error:
                details = traceback.format_exc()
                state = page.evaluate("""() => ({url:location.href, cards:document.querySelectorAll('.card').length,
                  count:document.querySelector('#result-count')?.textContent, search:document.querySelector('#search')?.value,
                  busy:document.querySelector('#catalog')?.getAttribute('aria-busy'),
                  failure:document.querySelector('#catalog-error')?.textContent})""")
                failures.append(dict(test=test.__name__, error=str(error), traceback=details, browser_errors=errors, state=state))
                print(f"FAIL {test.__name__}: {details}\n{json.dumps(state)}", flush=True)
            finally:
                page.close()
        context.close()
        browser.close()
    report = dict(endpoint=BASE, passed=passed, failures=failures,
                  catalog_models=len(catalog["models"]), category_options=expected_categories,
                  transport="compiled assets through Playwright routes" if OFFLINE else "local HTTP bridge")
    (ROOT / "review/cloud_catalog_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert not failures, report


if __name__ == "__main__":
    main()
