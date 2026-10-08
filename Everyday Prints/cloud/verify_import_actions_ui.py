"""Verify newer Save/Copy actions and deadlines supersede local dimension reads."""
import json
import os
from pathlib import Path
import sys
import time
import traceback
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from verify_dimensions_ui import FILES
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = '--offline' in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5178')
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))

COPY = """window.copies = []; window.holdCopy = false;
Object.defineProperty(navigator, 'clipboard', { value: { writeText: text => {
  window.copies.push(text);
  return window.holdCopy ? new Promise(resolve => { window.releaseCopy = resolve; }) : Promise.resolve();
} } });"""


def main():
    archive, metadata, mesh = fixture('parts_tray')
    preview = {**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1080}, accept_downloads=True)
        context.set_default_timeout(20000)
        if OFFLINE:
            attach_assets(context)

        def setup(page, clock=False, waiting=None):
            page.add_init_script(FILES + COPY)
            if clock:
                page.clock.install()
            jobs = []

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload)
                if waiting is not None:
                    waiting.append(route)
                elif payload.get('format') == 'cad':
                    route.fulfill(body=archive, headers=headers(metadata))
                else:
                    route.fulfill(body=mesh, headers=headers(preview, 'model/stl'))

            page.route('**/api/generate', generate)
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            page.locator('[data-model="parts_tray"]').click()
            expect(page.locator('#download')).to_be_enabled()
            page.locator('.saved-dimensions summary').click()
            return jobs

        def select(page, length, name='parameters.json', model='parts_tray'):
            record = {'model': model, 'units': 'mm', 'parameters': {'length': length} if model == 'parts_tray' else {'depth': length}}
            page.locator('#dimensions-file').set_input_files({'name': name, 'mimeType': 'application/json', 'buffer': json.dumps(record).encode()})

        def pending(page, count=1):
            page.wait_for_function('count => window.pendingDimensionReads.length === count', arg=count)

        def release(page, index=0):
            page.evaluate('index => window.pendingDimensionReads[index]()', index)
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')

        def download(page, button):
            with page.expect_download() as event:
                page.locator('#' + button).click()
            return event.value.suggested_filename, Path(event.value.path()).read_bytes()

        def saved_length(data):
            return json.loads(data)['parameters']['length']

        def clean(page, length):
            assert page.locator('[data-parameter="length"]').input_value() == str(length)
            expect(page.locator('#dimensions-error')).to_be_hidden()
            assert 'could not be loaded' not in page.locator('#form-message').inner_text()
            assert 'Loading saved dimensions' not in page.locator('#form-message').inner_text()

        def keyboard_save_supersedes_late_valid_import(page):
            jobs = setup(page)
            page.locator('[data-parameter="length"]').fill('190.55')
            select(page, 180.5, 'slow-save.json')
            pending(page)
            page.locator('#save-dimensions').focus()
            with page.expect_download() as event:
                page.keyboard.press('Enter')
            assert saved_length(Path(event.value.path()).read_bytes()) == 190.55
            release(page)
            clean(page, 190.55)
            expect(page.locator('#form-message')).to_have_text('Dimensions saved.')
            expect(page.locator('#save-dimensions')).to_be_focused()
            assert page.locator('#download').is_disabled() and not jobs

        def copy_supersedes_cross_model_import_while_clipboard_waits(page):
            jobs = setup(page)
            page.locator('[data-parameter="length"]').fill('190.55')
            select(page, 40, 'slow-other-model.json', 'cable_comb')
            pending(page)
            page.evaluate('window.holdCopy = true')
            page.locator('#share').click()
            page.wait_for_function('() => typeof window.releaseCopy === "function"')
            release(page)
            clean(page, 190.55)
            assert page.locator('#model-title').inner_text() == 'Divided parts tray'
            expect(page.locator('#share-message')).to_contain_text('Copying link')
            expect(page.locator('#share')).to_be_focused()
            copied = page.evaluate('window.copies[0]')
            assert json.loads(parse_qs(urlparse(copied).query)['p'][0])['length'] == 190.55
            assert page.url == copied
            page.evaluate('window.releaseCopy()')
            expect(page.locator('#share-message')).to_contain_text('Link copied')
            assert not jobs

        def newer_actions_discard_late_invalid_file_feedback(page):
            jobs = setup(page)
            for index, action in enumerate(('save-dimensions', 'share')):
                select(page, 251, 'slow-invalid-' + str(index) + '.json')
                pending(page, index + 1)
                if action == 'save-dimensions':
                    assert saved_length(download(page, action)[1]) == 150
                else:
                    page.locator('#share').click()
                    expect(page.locator('#share-message')).to_contain_text('Link copied')
                release(page, index)
                clean(page, 150)
                assert page.locator('#download').is_enabled()
            assert not jobs

        def stalled_read_deadline_keeps_new_selection_and_late_bytes_obsolete(page):
            jobs = setup(page, clock=True)
            try:
                page.clock.pause_at(page.evaluate('Date.now()') + 100)
                select(page, 180.5, 'slow-timeout.json')
                pending(page)
                page.clock.fast_forward(14999)
                expect(page.locator('#form-message')).to_have_text('Loading saved dimensions…')
                page.clock.fast_forward(2)
                expect(page.locator('#dimensions-error')).to_contain_text('took too long')
                assert page.locator('[data-parameter="length"]').input_value() == '150'
                assert page.locator('#download').is_enabled()
                assert page.locator('#load-dimensions').is_enabled()
                page.clock.resume()
                select(page, 170.25)
                expect(page.locator('[data-parameter="length"]')).to_have_value('170.25')
                page.locator('[data-parameter="height"]').focus()
                release(page)
                clean(page, 170.25)
                expect(page.locator('[data-parameter="height"]')).to_be_focused()
                assert page.locator('#download').is_disabled() and not jobs
            finally:
                page.clock.resume()

        def old_deadline_cannot_replace_new_read_or_build_progress(page):
            waiting = []
            jobs = setup(page, clock=True, waiting=waiting)
            try:
                page.clock.pause_at(page.evaluate('Date.now()') + 100)
                select(page, 190.55, 'slow-first.json')
                pending(page)
                page.clock.fast_forward(5000)
                select(page, 180.5, 'slow-second.json')
                pending(page, 2)
                page.clock.fast_forward(10001)
                expect(page.locator('#dimensions-error')).to_be_hidden()
                expect(page.locator('#form-message')).to_have_text('Loading saved dimensions…')
                page.clock.resume()
                release(page, 1)
                clean(page, 180.5)
                page.locator('#rebuild').click()
                page.wait_for_function("() => document.querySelector('#stop-build').hidden === false")
                deadline = time.monotonic() + 10
                while not waiting and time.monotonic() < deadline:
                    page.wait_for_timeout(25)
                assert waiting, 'The current preview request did not start'
                progress = page.locator('#form-message').inner_text()
                page.clock.fast_forward(5001)
                assert page.locator('#form-message').inner_text() == progress
                assert page.locator('#stop-build').is_visible()
                expect(page.locator('#dimensions-error')).to_be_hidden()
                release(page, 0)
                assert page.locator('#form-message').inner_text() == progress
                waiting.pop().fulfill(body=mesh, headers=headers(preview, 'model/stl'))
                expect(page.locator('#download')).to_be_enabled()
                assert download(page, 'download')[1] == mesh and len(jobs) == 1
            finally:
                page.clock.resume()

        def mobile_timeout_preserves_verified_stl_and_cached_cad(page):
            page.set_viewport_size({'width': 390, 'height': 844})
            jobs = setup(page, clock=True)
            try:
                page.locator('[data-parameter="length"]').fill('180.5')
                page.locator('#rebuild').click()
                expect(page.locator('#download')).to_be_enabled()
                assert download(page, 'download-cad')[1] == archive
                page.clock.pause_at(page.evaluate('Date.now()') + 100)
                select(page, 190.55, 'slow-mobile.json')
                pending(page)
                page.clock.fast_forward(15001)
                expect(page.locator('#dimensions-error')).to_contain_text('took too long')
                assert page.locator('#download').is_enabled() and page.locator('#download-cad').is_enabled()
                page.clock.resume()
                page.locator('#dimensions-error').scroll_into_view_if_needed()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(ROOT / 'review/cloud_import_actions_mobile.png'), full_page=False)
                filename, body = download(page, 'download')
                assert '-180.5x100x24mm-' in filename and body == mesh
                assert download(page, 'download-cad')[1] == archive
                release(page)
                assert page.locator('[data-parameter="length"]').input_value() == '180.5'
                assert len(jobs) == 2
            finally:
                page.clock.resume()

        def copy_clears_completed_import_errors_and_keeps_downloads(page):
            jobs = setup(page)
            select(page, 251)
            expect(page.locator('#dimensions-error')).to_be_visible()
            page.locator('#share').focus()
            page.keyboard.press('Enter')
            expect(page.locator('#share-message')).to_contain_text('Link copied')
            clean(page, 150)
            expect(page.locator('#load-dimensions')).to_have_accessible_description('Drop one saved dimensions JSON or CAD/kit ZIP anywhere in this editor, or use Load dimensions.')
            assert page.locator('#download').is_enabled() and not jobs

        for test in (keyboard_save_supersedes_late_valid_import,
                     copy_supersedes_cross_model_import_while_clipboard_waits,
                     newer_actions_discard_late_invalid_file_feedback,
                     stalled_read_deadline_keeps_new_selection_and_late_bytes_obsolete,
                     old_deadline_cannot_replace_new_read_or_build_progress,
                     mobile_timeout_preserves_verified_stl_and_cached_cad,
                     copy_clears_completed_import_errors_and_keeps_downloads):
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
                page.close()
        context.close()
        browser.close()
    report = dict(endpoint=BASE, passed=passed, failures=failures,
                  fixture_mesh_sha256=metadata['mesh_sha256'], read_deadline_ms=15000,
                  transport='compiled assets and real CAD fixtures with controlled file reads' if OFFLINE else 'local HTTP and controlled file reads')
    (ROOT / 'review/cloud_import_actions_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    assert not failures, report


if __name__ == '__main__':
    main()
