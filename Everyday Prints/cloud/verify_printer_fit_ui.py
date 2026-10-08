"""Check printer fit against verified meshes without changing CAD or draft state."""
import json
import os
from pathlib import Path
import sys
import traceback

from playwright.sync_api import expect, sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = '--offline' in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5178')
KEY = 'everydayPrints.printerVolume'
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))


def main():
    archive, metadata, mesh = fixture('parts_tray')
    preview = {**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])

        def setup(page, reply=None, wait=True, model='parts_tray'):
            jobs = []

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload)
                assert payload['model'] == metadata['model'] and payload['parameters'] == metadata['parameters'], payload
                if reply:
                    reply(route, payload)
                elif payload.get('format') == 'cad':
                    route.fulfill(body=archive, headers=headers(metadata))
                else:
                    route.fulfill(body=mesh, headers=headers(preview, 'model/stl'))

            page.route('**/api/generate', generate)
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            page.locator(f'[data-model="{model}"]').click()
            if wait:
                expect(page.locator('#download-cad')).to_be_enabled()
            page.locator('#printer-check summary').click()
            return jobs

        def volume(page, values):
            for axis, value in zip(('width', 'depth', 'height'), values):
                page.locator('#printer-' + axis).fill(str(value))

        def fit(page, kind):
            expect(page.locator('#printer-fit-result')).to_have_attribute('data-fit', kind)

        def build(page):
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            expect(page.locator('#rebuild')).to_be_enabled()

        def download(page, button='download'):
            with page.expect_download() as event:
                page.locator('#' + button).click()
            value = event.value
            return value.suggested_filename, Path(value.path()).read_bytes()

        def exact_axes_rotation_height_and_clear_keep_original_downloads(page):
            jobs = setup(page)
            expect(page.locator('#printer-fit-result')).to_contain_text('Enter a positive')
            original = download(page)
            volume(page, [150, 100, 24])
            fit(page, 'fits')
            expect(page.locator('#printer-mesh-size')).to_contain_text('150 × 100 × 24')
            volume(page, [100, 150, 24])
            fit(page, 'rotate')
            expect(page.locator('#printer-fit-result')).to_contain_text('90° turn on the bed')
            volume(page, [149.99, 100, 24])
            fit(page, 'large')
            volume(page, [200, 200, 23.99])
            fit(page, 'large')
            for invalid in ('0', '-1', ''):
                page.locator('#printer-height').fill(invalid)
                fit(page, '')
                expect(page.locator('#printer-height')).to_have_attribute('aria-invalid', 'true')
            page.locator('#clear-printer').focus()
            page.keyboard.press('Enter')
            expect(page.locator('#printer-width')).to_be_focused()
            assert all(page.locator('#printer-' + axis).input_value() == '' for axis in ('width', 'depth', 'height'))
            assert page.evaluate('(key) => localStorage.getItem(key)', KEY) is None
            assert download(page) == original and not jobs

        def drafts_builds_and_cached_cad_use_the_last_verified_mesh(page):
            jobs = setup(page)
            volume(page, [160, 110, 30])
            page.locator('#param-length').fill('180.5')
            fit(page, 'fits')
            expect(page.locator('#printer-preview-note')).to_be_visible()
            assert page.locator('#download').is_disabled()
            build(page)
            fit(page, 'large')
            expect(page.locator('#printer-preview-note')).to_be_hidden()
            expect(page.locator('#printer-mesh-size')).to_contain_text('180.5 × 100 × 24')
            filename, data = download(page)
            assert '-180.5x100x24mm-' in filename and data == mesh
            cached = download(page, 'download-cad')
            assert cached[1] == archive
            page.locator('#param-length').fill('')
            expect(page.locator('#printer-preview-note')).to_be_visible()
            fit(page, 'large')
            volume(page, [185, 110, 30])
            fit(page, 'fits')
            expect(page.locator('#param-length')).to_have_attribute('aria-invalid', 'true')
            assert page.locator('#download-cad').is_disabled()
            page.locator('#revert-parameters').click()
            expect(page.locator('#printer-preview-note')).to_be_hidden()
            assert download(page, 'download-cad') == cached
            assert len(jobs) == 2

        def measured_stl_extents_take_precedence_over_rounded_cad_bounds(page):
            def reply(route, payload):
                details = {**preview, 'bounds_mm': [180.54, 100, 24]}
                route.fulfill(body=mesh, headers=headers(details, 'model/stl'))
            jobs = setup(page, reply)
            volume(page, [180.51, 100, 24])
            build(page)
            fit(page, 'fits')
            expect(page.locator('#model-size')).to_have_text('180.54 × 100 × 24')
            expect(page.locator('#printer-mesh-size')).to_contain_text('180.5 × 100 × 24')
            page.locator('#printer-width').fill('180.49')
            fit(page, 'large')
            assert len(jobs) == 1

        def unavailable_and_rejected_previews_never_claim_a_fit(page):
            page.route('**/models/parts_tray.stl', lambda route: route.abort())
            bad = True
            def reply(route, payload):
                details = {**preview, 'bounds_mm': [190.5, 100, 24]} if bad else preview
                route.fulfill(body=mesh, headers=headers(details, 'model/stl'))
            jobs = setup(page, reply, wait=False)
            volume(page, [200, 200, 200])
            fit(page, '')
            expect(page.locator('#printer-fit-result')).to_contain_text('Waiting for a verified STL')
            build(page)
            expect(page.locator('#form-message')).to_contain_text('mesh dimensions do not match')
            fit(page, '')
            expect(page.locator('#printer-mesh-size')).to_be_hidden()
            bad = False
            build(page)
            fit(page, 'fits')
            assert download(page)[1] == mesh and len(jobs) == 2

        def graphics_failure_keeps_fit_and_exact_custom_files_available(page):
            page.add_init_script("""const getContext = HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                return type.startsWith('webgl') ? null : getContext.call(this, type, ...args);
              };""")
            jobs = setup(page)
            volume(page, [100, 185, 24])
            build(page)
            fit(page, 'rotate')
            expect(page.locator('#fallback-image')).to_be_visible()
            assert download(page)[1] == mesh
            assert download(page, 'download-cad')[1] == archive and len(jobs) == 2

        def assemblies_direct_checks_to_printable_components(page):
            jobs = setup(page, model='soap_dish_assembly')
            volume(page, [300, 300, 300])
            fit(page, '')
            expect(page.locator('#printer-fit-result')).to_contain_text('Reference assembly')
            expect(page.locator('#printer-mesh-size')).to_be_hidden()
            assert page.locator('#download').is_hidden()
            page.locator('#part-links button').first.click()
            expect(page.locator('#printer-fit-result')).to_have_attribute('data-fit', 'fits')
            expect(page.locator('#printer-mesh-size')).to_be_visible()
            assert page.locator('#printer-width').input_value() == '300' and not jobs

        def printer_settings_survive_history_refresh_and_keep_drafts_separate(page):
            jobs = setup(page)
            volume(page, [160.25, 110.5, 30])
            page.locator('#param-length').fill('180.5')
            page.reload()
            expect(page.locator('#download-cad')).to_be_disabled()
            expect(page.locator('#param-length')).to_have_value('180.5')
            page.locator('#printer-check summary').click()
            expect(page.locator('#printer-fit-result')).to_have_attribute('data-fit', 'fits')
            expect(page.locator('#printer-preview-note')).to_be_visible()
            assert page.locator('#printer-width').input_value() == '160.25'
            catalog = json.loads((CLOUD / 'public/catalog.json').read_text(encoding='utf-8'))
            cable = next(item for item in catalog['models'] if item['name'] == 'cable_comb')
            record = {'model': cable['name'], 'parameters': cable['defaults'], 'units': 'mm'}
            page.locator('#dimensions-file').set_input_files({'name': 'cable.json', 'mimeType': 'application/json', 'buffer': json.dumps(record).encode('utf-8')})
            expect(page.locator('#download-cad')).to_be_enabled()
            fit(page, 'fits')
            page.go_back()
            expect(page.locator('#param-length')).to_have_value('180.5')
            fit(page, 'fits')
            expect(page.locator('#printer-preview-note')).to_be_visible()
            assert page.locator('#printer-depth').input_value() == '110.5' and not jobs
            page.go_forward()
            expect(page.locator('#model-title')).to_have_text(cable['title'])
            fit(page, 'fits')
            page.go_back()
            expect(page.locator('#param-length')).to_have_value('180.5')
            page.locator('#printer-height').fill('')
            expect(page.locator('#printer-profile-note')).to_contain_text('Complete a positive')
            assert json.loads(page.evaluate('(key) => localStorage.getItem(key)', KEY)) == [160.25, 110.5, 30]
            page.reload()
            page.locator('#printer-check summary').click()
            for axis, value in zip(('width', 'depth', 'height'), ('160.25', '110.5', '30')):
                expect(page.locator('#printer-' + axis)).to_have_value(value)
            fit(page, 'fits')
            expect(page.locator('#param-length')).to_have_value('180.5')
            assert page.locator('#download').is_disabled() and not jobs

        def malformed_records_and_denied_storage_keep_checks_usable(page):
            setup(page)
            for record in ('broken', '[200,200]', '[200,200,0]', '["200",200,200]', '[200,200,1e400]', 'x' * 257):
                page.evaluate('args => localStorage.setItem(...args)', [KEY, record])
                page.reload()
                page.locator('#printer-check summary').click()
                expect(page.locator('#download-cad')).to_be_enabled()
                assert page.locator('#printer-width').input_value() == ''
                fit(page, '')
            page.add_init_script("""for (const name of ['getItem', 'setItem', 'removeItem']) {
              const original = Storage.prototype[name];
              Storage.prototype[name] = function(...args) {
                if (this === localStorage) throw new DOMException('Blocked storage', 'SecurityError');
                return original.apply(this, args);
              };
            }""")
            page.reload()
            page.locator('#printer-check summary').click()
            expect(page.locator('#download-cad')).to_be_enabled()
            volume(page, [200, 200, 200])
            fit(page, 'fits')
            expect(page.locator('#printer-profile-note')).to_contain_text('while this page is open')
            assert page.locator('#download').is_enabled()
            page.locator('#clear-printer').click()
            fit(page, '')

        def profile_edits_preserve_pending_build_progress_and_stop_controls(page):
            page.add_init_script("""window.fitWait = null; window.holdFit = true;
              const realFetch = window.fetch;
              window.fetch = async (...args) => {
                const response = await realFetch(...args);
                if (String(args[0]).includes('/api/generate') && window.holdFit) {
                  await new Promise(resolve => window.fitWait = resolve);
                }
                return response;
              };""")
            jobs = setup(page)
            volume(page, [160, 110, 30])
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            page.wait_for_function('() => window.fitWait !== null')
            before = page.locator('#form-message').inner_text()
            volume(page, [185, 110, 30])
            assert page.locator('#form-message').inner_text() == before
            expect(page.locator('#stop-build')).to_be_visible()
            assert page.locator('#rebuild').is_disabled()
            fit(page, 'fits')
            expect(page.locator('#printer-preview-note')).to_be_visible()
            page.evaluate('() => window.fitWait()')
            expect(page.locator('#download')).to_be_enabled()
            fit(page, 'fits')
            expect(page.locator('#printer-preview-note')).to_be_hidden()
            assert len(jobs) == 1 and download(page)[1] == mesh

        def mobile_and_desktop_controls_are_accessible_without_overflow(page):
            setup(page)
            volume(page, [100, 185, 24])
            build(page)
            fit(page, 'rotate')
            page.locator('#printer-check').scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / 'review/cloud_printer_fit_desktop.png'))
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('#printer-check').scroll_into_view_if_needed()
            for axis in ('width', 'depth', 'height'):
                control = page.locator('#printer-' + axis)
                box = control.bounding_box()
                assert box and box['height'] >= 44 and box['width'] >= 44, box
                assert control.get_attribute('aria-describedby') == 'printer-profile-note printer-fit-result printer-sync-message'
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('#editor').evaluate('(el) => el.scrollWidth <= el.clientWidth')
            page.screenshot(path=str(ROOT / 'review/cloud_printer_fit_mobile.png'))
            page.locator('#download').focus()
            with page.expect_download() as event:
                page.keyboard.press('Enter')
            assert Path(event.value.path()).read_bytes() == mesh
            expect(page.locator('#download')).to_be_focused()

        for test in (exact_axes_rotation_height_and_clear_keep_original_downloads,
                     drafts_builds_and_cached_cad_use_the_last_verified_mesh,
                     measured_stl_extents_take_precedence_over_rounded_cad_bounds,
                     unavailable_and_rejected_previews_never_claim_a_fit,
                     graphics_failure_keeps_fit_and_exact_custom_files_available,
                     assemblies_direct_checks_to_printable_components,
                     printer_settings_survive_history_refresh_and_keep_drafts_separate,
                     malformed_records_and_denied_storage_keep_checks_usable,
                     profile_edits_preserve_pending_build_progress_and_stop_controls,
                     mobile_and_desktop_controls_are_accessible_without_overflow):
            context = browser.new_context(viewport={'width': 1440, 'height': 1080}, accept_downloads=True)
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
    report = dict(endpoint=BASE, passed=passed, failures=failures, fixture_mesh_sha256=metadata['mesh_sha256'],
                  transport='compiled assets and real CAD fixtures' if OFFLINE else 'local HTTP')
    (ROOT / 'review/cloud_printer_fit_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    assert not failures, report


if __name__ == '__main__':
    main()
