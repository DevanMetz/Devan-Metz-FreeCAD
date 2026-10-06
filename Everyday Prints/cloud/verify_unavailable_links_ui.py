"""Verify unavailable model links recover to a usable library and browser history."""
import json
import os
from pathlib import Path
import sys
import time
import traceback
from urllib.parse import parse_qs, urlencode, urlparse

from playwright.sync_api import expect, sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from browser_transfers import DEFERRED_BODY
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = '--offline' in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5178')
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))


def main():
    catalog = json.loads((CLOUD / 'public/catalog.json').read_text(encoding='utf-8'))
    custom = fixture('parts_tray')
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1080}, accept_downloads=True)
        context.set_default_timeout(20000)
        if OFFLINE:
            attach_assets(context)

        def missing_url(name='retired_part', parameters='{"length":201.35}'):
            return BASE + '?' + urlencode({'model': name, 'p': parameters, 'campaign': 'measure'}) + '#fit'

        def library(page):
            page.wait_for_function("() => document.querySelectorAll('.card').length > 0 && document.querySelector('#catalog-loading').hidden")

        def recovered(page):
            expect(page.locator('#link-notice')).to_be_visible()
            expect(page.locator('#link-notice')).to_contain_text('not in the library')
            assert not page.locator('#editor').evaluate('element => element.open')
            query = parse_qs(urlparse(page.url).query)
            assert 'model' not in query and 'p' not in query, page.url
            assert query['campaign'] == ['measure'] and urlparse(page.url).fragment == 'fit'
            assert page.evaluate('history.state.everydayPrints.model === null && history.state.everydayPrints.depth === 0')

        def no_jobs(page):
            jobs = []

            def reject(route):
                jobs.append(route.request.post_data_json)
                route.abort()

            page.route('**/api/generate', reject)
            return jobs

        def unavailable_deep_link_explains_and_replaces_the_route(page):
            jobs = no_jobs(page)
            page.goto(missing_url())
            library(page)
            recovered(page)
            assert page.locator('.card').count() == 53 and not jobs
            expect(page.locator('#link-notice')).to_have_attribute('role', 'status')
            identity, count = page.evaluate('[history.state.everydayPrints.id, history.length]')
            page.reload()
            library(page)
            expect(page.locator('#link-notice')).to_be_hidden()
            assert page.evaluate('[history.state.everydayPrints.id, history.length]') == [identity, count]

        def empty_malformed_and_long_identifiers_use_the_same_recovery(page):
            jobs = no_jobs(page)
            for name in ('', '../../missing', '__proto__', '<svg onload=alert(1)>', 'x' * 12000):
                page.goto(missing_url(name, '{broken'))
                library(page)
                recovered(page)
                assert page.locator('#link-notice img, #link-notice svg').count() == 0
                assert len(page.locator('#link-notice').inner_text()) < 100
            assert not jobs

        def replacement_model_uses_normal_filtered_library_history(page):
            jobs = no_jobs(page)
            page.goto(missing_url())
            library(page)
            recovered(page)
            before = page.evaluate('history.length')
            page.locator('#search').fill('phone')
            page.locator('[data-model="phone_stand"]').click()
            expect(page.locator('#download')).to_be_enabled()
            expect(page.locator('#link-notice')).to_be_hidden()
            assert page.locator('#param-width').input_value() == '65'
            page.locator('#param-width').fill('77')
            page.locator('#close-editor').click()
            page.wait_for_function("() => !document.querySelector('#editor').open && !new URL(location.href).searchParams.has('model')")
            assert page.evaluate('history.length') == before + 1
            assert page.locator('#search').input_value() == 'phone' and page.locator('.card').count() == 1
            page.go_forward()
            expect(page.locator('#param-width')).to_have_value('77')
            expect(page.locator('#download')).to_be_disabled()
            page.go_back()
            expect(page.locator('[data-model="phone_stand"]')).to_be_focused()
            assert page.locator('#search').input_value() == 'phone' and not jobs

        def failed_catalog_waits_for_validation_and_keeps_search_focus(page):
            waiting, attempts = [], []

            def catalog_reply(route):
                attempts.append(route)
                if len(attempts) == 1:
                    route.fulfill(status=503, json={})
                else:
                    waiting.append(route)

            page.route('**/catalog.json', catalog_reply)
            page.goto(missing_url())
            expect(page.locator('#catalog-error')).to_be_visible()
            expect(page.locator('#link-notice')).to_be_hidden()
            assert parse_qs(urlparse(page.url).query)['model'] == ['retired_part']
            page.locator('#search').fill('phone')
            page.locator('#retry-catalog').click()
            deadline = time.monotonic() + 10
            while not waiting and time.monotonic() < deadline:
                page.wait_for_timeout(25)
            assert len(waiting) == 1
            page.locator('#search').focus()
            waiting.pop().fulfill(json=catalog)
            library(page)
            recovered(page)
            assert page.locator('.card').count() == 1
            expect(page.locator('#search')).to_be_focused()

        def valid_custom_links_and_plain_library_keep_their_routes(page):
            jobs = no_jobs(page)
            page.goto(BASE + '?' + urlencode({'model': 'parts_tray', 'p': '{"length":180.5}'}))
            expect(page.locator('#param-length')).to_have_value('180.5')
            page.wait_for_function("() => document.querySelector('#preview-loading').hidden")
            expect(page.locator('#link-notice')).to_be_hidden()
            expect(page.locator('#download')).to_be_disabled()
            assert parse_qs(urlparse(page.url).query)['model'] == ['parts_tray']
            page.goto(BASE)
            library(page)
            expect(page.locator('#link-notice')).to_be_hidden()
            assert not jobs

        def old_unavailable_history_entry_discards_a_late_build(page):
            page.add_init_script(DEFERRED_BODY + """
              const linkFetch = window.fetch;
              window.fetch = async (...args) => {
                const response = await linkFetch(...args);
                if (String(args[0]).includes('/api/generate')) {
                  const bytes = await response.arrayBuffer();
                  window.deferFileBody(response, bytes, () => new Promise(resolve => { window.releaseLinkBuild = resolve; }));
                }
                return response;
              };
            """)
            jobs = []

            def generate(route):
                jobs.append(route.request.post_data_json)
                metadata = {**custom[1], 'format': 'stl', 'file_sha256': custom[1]['mesh_sha256']}
                route.fulfill(body=custom[2], headers=headers(metadata, 'model/stl'))

            page.route('**/api/generate', generate)
            page.goto(BASE)
            library(page)
            # Represent an entry created by an older tab before link recovery existed.
            page.evaluate('url => history.replaceState(history.state, "", url)', missing_url())
            page.locator('[data-model="parts_tray"]').click()
            expect(page.locator('#download')).to_be_enabled()
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            page.wait_for_function('() => typeof window.releaseLinkBuild === "function"')
            page.go_back()
            recovered(page)
            expect(page.locator('[data-model="parts_tray"]')).to_be_focused()
            page.evaluate('() => window.releaseLinkBuild()')
            page.locator('[data-model="cable_comb"]').click()
            expect(page.locator('#download')).to_be_enabled()
            assert page.locator('#model-size').inner_text() == '59 × 32 × 4'
            expect(page.locator('#link-notice')).to_be_hidden()
            assert len(jobs) == 1

        def mobile_notice_and_keyboard_replacement_fit_the_viewport(page):
            page.set_viewport_size({'width': 390, 'height': 844})
            page.goto(missing_url())
            library(page)
            recovered(page)
            page.locator('#link-notice').scroll_into_view_if_needed()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(ROOT / 'review/cloud_unavailable_link_mobile.png'))
            page.locator('#search').fill('phone')
            page.locator('[data-model="phone_stand"]').focus()
            page.keyboard.press('Enter')
            expect(page.locator('#download')).to_be_enabled()
            expect(page.locator('#link-notice')).to_be_hidden()
            with page.expect_download() as event:
                page.locator('#download').focus()
                page.keyboard.press('Enter')
            assert event.value.suggested_filename == 'phone_stand.stl'

        for check in (unavailable_deep_link_explains_and_replaces_the_route,
                      empty_malformed_and_long_identifiers_use_the_same_recovery,
                      replacement_model_uses_normal_filtered_library_history,
                      failed_catalog_waits_for_validation_and_keeps_search_focus,
                      valid_custom_links_and_plain_library_keep_their_routes,
                      old_unavailable_history_entry_discards_a_late_build,
                      mobile_notice_and_keyboard_replacement_fit_the_viewport):
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                check(page)
                assert not errors, errors
                passed.append(check.__name__)
                print('PASS', check.__name__, flush=True)
            except Exception:
                failures.append({'check': check.__name__, 'error': traceback.format_exc(), 'browser_errors': errors})
                print('FAIL', check.__name__, failures[-1]['error'], flush=True)
            finally:
                page.close()
        browser.close()
    report = {'base': BASE, 'passed': passed, 'failures': failures,
              'transport': 'compiled assets, browser history and real STL fixtures'}
    (ROOT / 'review/cloud_unavailable_link_validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    sys.exit(bool(failures))


if __name__ == '__main__':
    main()
