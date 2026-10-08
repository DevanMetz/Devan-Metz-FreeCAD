"""Verify inactivity recovery for original previews while retaining editor work."""
import json
import os
from pathlib import Path
import sys
import traceback
from urllib.parse import urlencode

from playwright.sync_api import expect, sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from verify_export_ui import fixture, headers
from verify_original_retry_ui import FAULTS

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = '--offline' in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5178')
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))
sys.stdout.reconfigure(encoding='utf-8')
CHUNKS = """window.originalChunks = [];
window.deferFileBody = (response, bytes, wait) => {
  let offset = 0;
  Object.defineProperty(response, 'body', { value: { getReader: () => ({
    read: async () => {
      if (offset === bytes.byteLength) return { done: true };
      await wait();
      const amount = window.originalChunks.shift() ?? bytes.byteLength;
      const value = new Uint8Array(bytes.slice(offset, offset + amount));
      offset += value.byteLength;
      return { done: false, value };
    }, cancel: async () => {}, releaseLock: () => {}
  }) } });
};"""
API_HOLD = """window.originalIdleAPIRelease = null; window.originalIdleAPIHold = false;
const originalIdleFetch = window.fetch;
window.fetch = async (...args) => {
  const response = await originalIdleFetch(...args);
  if (String(args[0]).includes('/api/generate') && window.originalIdleAPIHold)
    await new Promise(resolve => window.originalIdleAPIRelease = resolve);
  return response;
};"""


def main():
    fixtures = {name: fixture(name) for name in ('parts_tray', 'parts_tray_original')}
    original = (CLOUD / 'public/models/parts_tray.stl').read_bytes()
    catalog = {item['name']: item for item in json.loads((CLOUD / 'public/catalog.json').read_text(encoding='utf-8'))['models']}
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])

        def setup(page, mode='headers', model='parts_tray', parameters=None, raw_parameters=None):
            page.clock.install()
            page.clock.pause_at(page.evaluate('Date.now()') / 1000 + 60)
            page.add_init_script(FAULTS + CHUNKS + API_HOLD)
            page.add_init_script('window.originalFaults.push(' + json.dumps(dict(mode=mode, neverCancel=True)) + ');')
            jobs = []

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload)
                assert payload['model'] == 'parts_tray', payload
                archive, metadata, mesh = fixtures['parts_tray' if payload['parameters']['length'] == 180.5 else 'parts_tray_original']
                if payload.get('format') == 'cad':
                    route.fulfill(body=archive, headers=headers(metadata))
                else:
                    route.fulfill(body=mesh, headers=headers({**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}, 'model/stl'))

            page.route('**/api/generate', generate)
            query = dict(model=model)
            if parameters is not None or raw_parameters is not None:
                query['p'] = raw_parameters if raw_parameters is not None else json.dumps(parameters)
            page.goto(BASE + '/?' + urlencode(query))
            held(page, 0)
            return jobs

        def held(page, index):
            page.wait_for_function("index => typeof window.originalTransfers[index]?.release === 'function'", arg=index)

        def expire(page):
            page.clock.fast_forward(15001)
            page.clock.resume()
            expect(page.locator('#preview-loading')).to_be_hidden()
            expect(page.locator('#retry-original')).to_be_enabled()
            expect(page.locator('#transfer-status')).to_be_hidden()

        def release(page, index=0):
            page.evaluate('index => window.originalTransfers[index].release()', index)

        def ready(page):
            expect(page.locator('#preview-loading')).to_be_hidden()
            expect(page.locator('#original-recovery')).to_be_hidden()

        def snapshot(page):
            return page.evaluate("""() => ({url: location.href, history: history.state,
              fields: [...document.querySelectorAll('#parameter-fields input')].map(el => [el.id, el.value, el.getAttribute('aria-invalid')]),
              dimensions: document.getElementById('dimensions-error').textContent,
              versionName: document.getElementById('version-name').value,
              versions: localStorage.getItem('everyday-prints-versions')})""")

        def download(page, button='download'):
            with page.expect_download() as event:
                page.locator('#' + button).click()
            return event.value.suggested_filename, Path(event.value.path()).read_bytes()

        def stalled_headers_recover_retry_and_ignore_expired_files(page):
            jobs = setup(page)
            before = snapshot(page)
            expire(page)
            expect(page.locator('#form-message')).to_contain_text('original preview stopped responding')
            expect(page.locator('#mesh-status')).to_have_text('Preview unavailable')
            assert snapshot(page) == before and page.locator('#download').is_disabled()
            release(page)
            page.wait_for_function('() => window.originalTransfers[0].cancelled === 1')
            assert page.evaluate('window.originalTransfers[0].pulls') == 0
            expect(page.locator('#download')).to_be_disabled()
            page.locator('#retry-original').click()
            ready(page)
            assert download(page) == ('parts_tray.stl', original) and not jobs
            assert page.evaluate('window.originalRequests.at(-1).cache') == 'reload'

        def stalled_bodies_release_uncancellable_readers_and_late_bytes_stay_expired(page):
            jobs = setup(page, 'body')
            before = snapshot(page)
            expect(page.locator('#transfer-status')).to_contain_text('0 B received')
            expire(page)
            stats = page.evaluate('window.originalTransfers[0]')
            assert stats['cancelled'] == 1 and stats['released'] and stats['pulls'] == 1, stats
            release(page)
            expect(page.locator('#download')).to_be_disabled()
            assert snapshot(page) == before
            page.locator('#retry-original').click()
            ready(page)
            assert download(page)[1] == original and not jobs

        def positive_progress_keeps_slow_exact_transfers_alive_beyond_the_initial_deadline(page):
            jobs = setup(page, 'body')
            page.evaluate('window.originalChunks = [84, 50]')
            release(page)
            page.clock.run_for(20)
            page.wait_for_function('() => window.originalTransfers[0].pulls === 2')
            for count in (3, 4):
                page.clock.fast_forward(14000)
                expect(page.locator('#preview-loading')).to_be_visible()
                release(page)
                if count == 3:
                    page.clock.run_for(20)
                    page.wait_for_function('() => window.originalTransfers[0].pulls === 3')
            page.clock.resume()
            ready(page)
            assert download(page)[1] == original and not jobs
            assert page.evaluate('window.originalTransfers[0].cancelled') == 0

        def empty_chunks_cannot_extend_inactivity_and_partial_data_never_becomes_downloadable(page):
            jobs = setup(page, 'body')
            page.evaluate('window.originalChunks = [84, 0]')
            release(page)
            page.clock.run_for(20)
            page.wait_for_function('() => window.originalTransfers[0].pulls === 2')
            page.clock.fast_forward(10000)
            release(page)
            page.clock.run_for(20)
            page.wait_for_function('() => window.originalTransfers[0].pulls === 3')
            page.clock.fast_forward(5001)
            page.clock.resume()
            expect(page.locator('#preview-loading')).to_be_hidden()
            expect(page.locator('#form-message')).to_contain_text('stopped responding')
            expect(page.locator('#download')).to_be_disabled()
            assert page.evaluate('window.originalTransfers[0].cancelled') == 1 and not jobs

        def timeout_preserves_blank_and_ordered_list_drafts_name_errors_and_focus(page):
            jobs = setup(page, 'body', model='cable_comb')
            page.locator('#param-cable_diameters').fill('4.2, bad, 2.5')
            page.locator('.saved-dimensions summary').click()
            page.locator('#version-name').fill('Unsaved routing')
            page.locator('#param-cable_diameters').focus()
            before = snapshot(page)
            feedback = page.locator('#form-message').inner_text()
            expire(page)
            assert snapshot(page) == before and page.locator('#form-message').inner_text() == feedback
            expect(page.locator('#param-cable_diameters')).to_be_focused()
            expect(page.locator('#param-cable_diameters')).to_have_attribute('aria-invalid', 'true')
            expect(page.locator('#mesh-status')).to_have_text('Fix invalid dimensions')
            page.locator('#retry-original').click()
            ready(page)
            assert snapshot(page) == before and page.locator('#download').is_disabled() and not jobs

        def accepted_dimensions_and_rejected_file_feedback_survive_background_timeouts(page):
            jobs = setup(page, 'headers')
            page.locator('.saved-dimensions summary').click()
            record = dict(model='parts_tray', units='mm', parameters={'length': 180.5})
            page.locator('#dimensions-file').set_input_files(dict(name='tray.json', mimeType='application/json', buffer=json.dumps(record).encode()))
            expect(page.locator('#param-length')).to_have_value('180.5')
            before = snapshot(page)
            expire(page)
            assert snapshot(page) == before
            expect(page.locator('#form-message')).to_contain_text('Saved dimensions loaded')
            expect(page.locator('#form-message')).to_contain_text('stopped responding')
            page.evaluate("window.originalFaults.push({mode:'body', neverCancel:true})")
            page.clock.pause_at(page.evaluate('Date.now()') / 1000 + 60)
            page.locator('#retry-original').click()
            held(page, 1)
            page.locator('#dimensions-file').set_input_files(dict(name='broken.json', mimeType='application/json', buffer=b'{bad'))
            expect(page.locator('#dimensions-error')).to_be_visible()
            before = snapshot(page)
            feedback = page.locator('#form-message').inner_text()
            expire(page)
            assert snapshot(page) == before and page.locator('#form-message').inner_text() == feedback
            assert page.locator('#download').is_disabled() and not jobs

        def newer_retries_keep_their_own_deadline_and_old_headers_cannot_replace_them(page):
            jobs = setup(page)
            page.clock.fast_forward(6000)
            page.evaluate("window.originalFaults.push({mode:'headers'})")
            page.locator('#retry-original').click()
            held(page, 1)
            page.clock.fast_forward(8000)
            expect(page.locator('#preview-loading')).to_be_visible()
            assert page.evaluate('window.originalTransfers[1].cancelled') == 0
            release(page, 0)
            page.clock.run_for(20)
            page.wait_for_function('() => window.originalTransfers[0].cancelled === 1')
            expect(page.locator('#preview-loading')).to_be_visible()
            release(page, 1)
            page.clock.resume()
            ready(page)
            page.clock.fast_forward(16000)
            assert download(page)[1] == original and not jobs

        def cad_builds_supersede_original_deadlines_and_keep_stop_focus_and_exact_files(page):
            jobs = setup(page)
            page.locator('#param-length').fill('180.5')
            page.evaluate('window.originalIdleAPIHold = true')
            page.locator('#rebuild').focus()
            page.keyboard.press('Enter')
            page.wait_for_function('() => window.originalIdleAPIRelease !== null')
            page.clock.fast_forward(16000)
            expect(page.locator('#stop-build')).to_be_focused()
            expect(page.locator('#form-message')).to_contain_text('Still building')
            expect(page.locator('#rebuild')).to_be_disabled()
            release(page, 0)
            page.clock.run_for(20)
            expect(page.locator('#stop-build')).to_be_focused()
            page.evaluate('() => { window.originalIdleAPIHold = false; window.originalIdleAPIRelease(); }')
            page.clock.resume()
            expect(page.locator('#download')).to_be_enabled()
            stl, cad = download(page), download(page, 'download-cad')
            assert stl[1] == fixtures['parts_tray'][2] and '-180.5x100x24mm-' in stl[0]
            assert cad[1] == fixtures['parts_tray'][0] and '-180.5x100x24mm-' in cad[0] and len(jobs) == 2

        def navigation_and_cached_history_discard_old_timers_and_late_original_meshes(page):
            jobs = setup(page, 'body')
            page.clock.resume()
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            expect(page.locator('#download')).to_be_enabled()
            custom = download(page)
            page.locator('.saved-dimensions summary').click()
            record = dict(model='cable_comb', units='mm', parameters=catalog['cable_comb']['defaults'])
            page.locator('#dimensions-file').set_input_files(dict(name='cable.json', mimeType='application/json', buffer=json.dumps(record).encode()))
            expect(page.locator('#download')).to_be_enabled()
            cable = download(page)
            release(page, 0)
            page.clock.fast_forward(16000)
            assert download(page) == cable
            page.go_back()
            expect(page.locator('#param-length')).to_have_value('180.5')
            assert download(page) == custom and len(jobs) == 1
            assert len(page.evaluate('window.originalRequests')) == 2

        def assembly_timeouts_retry_components_and_graphics_failure_keep_verified_files(page):
            page.add_init_script("""const getContext = HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                return type.startsWith('webgl') ? null : getContext.call(this, type, ...args);
              };""")
            jobs = setup(page, 'body', model='soap_dish_assembly')
            expire(page)
            expect(page.locator('#reference-note')).to_be_visible()
            expect(page.locator('#download')).to_be_hidden()
            page.locator('#retry-original').click()
            ready(page)
            expect(page.locator('#download-cad')).to_be_enabled()
            expect(page.locator('#fallback-image')).to_be_visible()
            page.locator('#part-links button').first.click()
            expect(page.locator('#download')).to_be_enabled()
            assert download(page)[1] and not jobs

        def mobile_keyboard_timeout_retry_keeps_reachable_controls_and_exact_files(page):
            page.set_viewport_size(dict(width=390, height=844))
            jobs = setup(page, 'body')
            page.locator('#param-length').fill('')
            page.locator('#param-length').focus()
            before = snapshot(page)
            expire(page)
            expect(page.locator('#param-length')).to_be_focused()
            assert snapshot(page) == before
            for control in ('retry-original', 'rebuild'):
                box = page.locator('#' + control).bounding_box()
                assert box and box['height'] >= 44, (control, box)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('#editor').evaluate('(el) => el.scrollWidth <= el.clientWidth')
            page.locator('#original-recovery').scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / 'review/cloud_original_idle_mobile.png'))
            page.set_viewport_size(dict(width=1440, height=1080))
            page.locator('#original-recovery').scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / 'review/cloud_original_idle_desktop.png'))
            page.set_viewport_size(dict(width=390, height=844))
            page.locator('#retry-original').focus()
            page.keyboard.press('Enter')
            ready(page)
            expect(page.locator('#param-length')).to_be_focused()
            expect(page.locator('#param-length')).to_have_value('')
            page.locator('#param-length').fill('150')
            assert download(page) == ('parts_tray.stl', original) and not jobs

        tests = (stalled_headers_recover_retry_and_ignore_expired_files,
                 stalled_bodies_release_uncancellable_readers_and_late_bytes_stay_expired,
                 positive_progress_keeps_slow_exact_transfers_alive_beyond_the_initial_deadline,
                 empty_chunks_cannot_extend_inactivity_and_partial_data_never_becomes_downloadable,
                 timeout_preserves_blank_and_ordered_list_drafts_name_errors_and_focus,
                 accepted_dimensions_and_rejected_file_feedback_survive_background_timeouts,
                 newer_retries_keep_their_own_deadline_and_old_headers_cannot_replace_them,
                 cad_builds_supersede_original_deadlines_and_keep_stop_focus_and_exact_files,
                 navigation_and_cached_history_discard_old_timers_and_late_original_meshes,
                 assembly_timeouts_retry_components_and_graphics_failure_keep_verified_files,
                 mobile_keyboard_timeout_retry_keeps_reachable_controls_and_exact_files)
        for test in tests:
            context = browser.new_context(viewport=dict(width=1440, height=1080), accept_downloads=True)
            context.set_default_timeout(20000)
            if OFFLINE:
                attach_assets(context)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                print('START ' + test.__name__, flush=True)
                test(page)
                assert not errors, errors
                passed.append(test.__name__)
                print('PASS ' + test.__name__, flush=True)
            except Exception as error:
                failures.append(dict(test=test.__name__, error=str(error), traceback=traceback.format_exc(), browser_errors=errors))
                print('FAIL ' + test.__name__ + ': ' + traceback.format_exc(), flush=True)
            finally:
                context.close()
        browser.close()
    report = dict(endpoint=BASE, passed=passed, failures=failures, inactivity_ms=15000,
                  transport='compiled assets and real CAD fixtures, controlled browser time and transfers' if OFFLINE else 'local HTTP')
    (ROOT / 'review/cloud_original_idle_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    assert not failures, report


if __name__ == '__main__':
    main()
