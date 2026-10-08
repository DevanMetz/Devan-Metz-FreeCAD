"""Verify named dimension versions, persistent storage and exact preview downloads."""
import json
import os
from pathlib import Path
import sys
import traceback

from playwright.sync_api import expect, sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from verify_dimensions_ui import FILES
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = '--offline' in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5178')
KEY = 'everyday-prints-versions'
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))


def main():
    fixtures = {name: fixture(name) for name in ('parts_tray', 'cable_comb')}
    models = json.loads((CLOUD / 'public/catalog.json').read_text(encoding='utf-8'))['models']
    catalog = {item['name']: item for item in models}
    passed, failures = [], []

    def record(model, name, number=1, parameters=None):
        return dict(id=f'00000000-0000-4000-8000-{number:012x}', name=name,
                    dimensions={'model': model, 'units': 'mm', 'parameters': parameters or catalog[model]['defaults']})

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])

        def setup(page, records=None, model='parts_tray', waiting=None):
            page.add_init_script(FILES)
            if records is not None:
                page.add_init_script('localStorage.setItem(' + json.dumps(KEY) + ',' + json.dumps(json.dumps(records)) + ');')
            jobs = []

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload)
                if waiting is not None:
                    waiting.append(route)
                    return
                archive, metadata, mesh = fixtures[payload['model']]
                assert payload['parameters'] == metadata['parameters'], payload
                if payload.get('format') == 'cad':
                    route.fulfill(body=archive, headers=headers(metadata))
                else:
                    details = {**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}
                    route.fulfill(body=mesh, headers=headers(details, 'model/stl'))

            page.route('**/api/generate', generate)
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            page.locator(f'[data-model="{model}"]').click()
            expect(page.locator('#download-cad')).to_be_enabled()
            page.locator('.saved-dimensions > summary').click()
            return jobs

        def save(page, name, keyboard=False):
            page.locator('#version-name').fill(name)
            if keyboard:
                page.locator('#version-name').press('Enter')
            else:
                page.locator('#save-version').click()

        def stored(page):
            return page.evaluate('key => JSON.parse(localStorage.getItem(key) || "[]")', KEY)

        def open_version(page, name):
            option = page.locator('#version-choice option').filter(has_text=name)
            page.locator('#version-choice').select_option(option.get_attribute('value'))
            page.locator('#load-version').click()

        def download(page, button='download'):
            with page.expect_download() as event:
                page.locator('#' + button).click()
            value = event.value
            return value.suggested_filename, Path(value.path()).read_bytes()

        def build(page):
            page.locator('#rebuild').click()
            expect(page.locator('#download')).to_be_enabled()

        def save_unbuilt_decimals_refresh_open_and_download_exact_files(page):
            jobs = setup(page)
            page.locator('#param-length').fill('180.5')
            save(page, 'Desk drawer', keyboard=True)
            assert stored(page)[0]['dimensions']['parameters']['length'] == 180.5 and not jobs
            assert page.locator('#download').is_disabled()
            page.reload()
            page.locator('.saved-dimensions > summary').click()
            expect(page.locator('#version-choice option')).to_have_count(2)
            page.locator('#param-length').fill('190.55')
            open_version(page, 'Desk drawer')
            expect(page.locator('#param-length')).to_have_value('180.5')
            expect(page.locator('#param-length')).to_be_focused()
            expect(page.locator('#form-message')).to_contain_text('Version “Desk drawer” loaded')
            assert page.locator('#download').is_disabled()
            build(page)
            name, mesh = download(page)
            assert '-180.5x100x24mm-' in name and mesh == fixtures['parts_tray'][2]
            assert download(page, 'download-cad')[1] == fixtures['parts_tray'][0] and len(jobs) == 2

        def matching_version_reuses_preview_and_cached_cad(page):
            jobs = setup(page)
            page.locator('#param-length').fill('180.5')
            save(page, 'Wide tray')
            build(page)
            cad = download(page, 'download-cad')
            page.locator('#param-length').fill('190.55')
            open_version(page, 'Wide tray')
            expect(page.locator('#form-message')).to_contain_text('match the verified preview')
            assert download(page, 'download-cad') == cad and len(jobs) == 2

        def cross_model_lists_keep_order_and_normal_history(page):
            cable_parameters = fixtures['cable_comb'][1]['parameters']
            jobs = setup(page, [record('cable_comb', 'Cable routing', parameters=cable_parameters)])
            save(page, 'Original tray')
            open_version(page, 'Cable routing')
            expect(page.locator('#model-title')).to_have_text(catalog['cable_comb']['title'])
            assert [float(value) for value in page.locator('#param-cable_diameters').input_value().split(',')] == cable_parameters['cable_diameters']
            expect(page.locator('#param-cable_diameters')).to_be_focused()
            assert page.locator('#download').is_disabled() and not jobs
            build(page)
            assert download(page)[1] == fixtures['cable_comb'][2]
            page.go_back()
            expect(page.locator('#model-title')).to_have_text(catalog['parts_tray']['title'])
            expect(page.locator('#download')).to_be_enabled()
            page.go_forward()
            expect(page.locator('#model-title')).to_have_text(catalog['cable_comb']['title'])
            assert download(page)[1] == fixtures['cable_comb'][2] and len(jobs) == 1

        def assembly_versions_use_canonical_inventory_and_component_navigation(page):
            jobs = setup(page, model='soap_dish_assembly')
            save(page, 'Bathroom set')
            saved = stored(page)
            assert saved[0]['dimensions']['kit'] == catalog['soap_dish_assembly']['kit']
            saved[0]['dimensions']['kit'] = [{'model': 'parts_tray', 'quantity': 999}]
            saved[0]['dimensions']['bounds_mm'] = [999, 999, 999]
            page.evaluate('args => localStorage.setItem(...args)', [KEY, json.dumps(saved)])
            page.locator('#param-length').fill('130')
            open_version(page, 'Bathroom set')
            assert page.locator('#download').is_hidden()
            expect(page.locator('#download-cad')).to_be_enabled()
            _, body = download(page, 'save-dimensions')
            assert json.loads(body)['kit'] == catalog['soap_dish_assembly']['kit']
            page.locator('#part-links button').first.click()
            expect(page.locator('#download')).to_be_enabled()
            assert not jobs

        def name_field_validation_duplicates_and_html_labels_preserve_versions(page):
            setup(page)
            save(page, ' ')
            expect(page.locator('#version-name')).to_have_attribute('aria-invalid', 'true')
            expect(page.locator('#version-name')).to_be_focused()
            assert not stored(page)
            name = 'Kitchen <wide> "✓"'
            save(page, name)
            expect(page.locator('#version-choice option').nth(1)).to_contain_text(name)
            original = stored(page)
            save(page, name.upper())
            expect(page.locator('#version-message')).to_contain_text('already has a version')
            assert stored(page) == original
            assert not page.locator('#version-choice wide').count()
            page.locator('#param-length').fill('')
            save(page, 'Invalid size')
            expect(page.locator('#param-length')).to_be_focused()
            assert stored(page) == original

        def version_limit_and_removal_preserve_current_fields_and_files(page):
            records = [record('parts_tray', f'Size {number:02}', number) for number in range(20)]
            jobs = setup(page, records)
            before = download(page)
            save(page, 'Overflow')
            expect(page.locator('#version-message')).to_contain_text('20 saved versions')
            assert stored(page) == records
            page.locator('#version-choice').select_option(records[5]['id'])
            page.locator('#remove-version').click()
            expect(page.locator('#version-choice')).to_be_focused()
            assert page.locator('#param-length').input_value() == '150'
            assert download(page) == before
            save(page, 'Replacement')
            assert len(stored(page)) == 20 and stored(page)[0]['name'] == 'Replacement' and not jobs

        def corrupt_storage_is_preserved_and_portable_dimensions_still_work(page):
            setup(page)
            broken = record('parts_tray', 'Bad dimensions')
            broken['dimensions']['parameters'] = {'length': 180.5}
            for text in ('not JSON', json.dumps([broken]), 'x' * 65537):
                page.evaluate('args => localStorage.setItem(...args)', [KEY, text])
                page.reload()
                page.locator('.saved-dimensions > summary').click()
                expect(page.locator('#version-message')).to_have_class('error')
                expect(page.locator('#download')).to_be_enabled()
                save(page, 'Keep this model')
                assert page.evaluate('key => localStorage.getItem(key)', KEY) == text
                _, body = download(page, 'save-dimensions')
                assert json.loads(body)['parameters'] == catalog['parts_tray']['defaults']

        def quota_failures_and_denied_reads_keep_the_current_preview(page):
            setup(page)
            save(page, 'Original')
            original = stored(page)
            page.evaluate("""key => {
              const original = Storage.prototype.setItem;
              Storage.prototype.setItem = function(name, value) {
                if (this === localStorage && name === key) throw new DOMException('Full', 'QuotaExceededError');
                return original.call(this, name, value);
              };
            }""", KEY)
            save(page, 'New')
            expect(page.locator('#version-message')).to_contain_text('could not be saved')
            page.locator('#remove-version').click()
            expect(page.locator('#version-message')).to_contain_text('could not be removed')
            assert stored(page) == original and page.locator('#download').is_enabled()
            page.add_init_script("""const getItem = Storage.prototype.getItem;
              Storage.prototype.getItem = function(key) {
                if (this === localStorage && key === 'everyday-prints-versions') throw new DOMException('Denied', 'SecurityError');
                return getItem.call(this, key);
              };""")
            page.reload()
            page.locator('.saved-dimensions > summary').click()
            expect(page.locator('#version-message')).to_contain_text('unavailable in this browser')
            expect(page.locator('#download')).to_be_enabled()
            assert json.loads(download(page, 'save-dimensions')[1])['model'] == 'parts_tray'

        def delayed_cross_model_preview_cannot_replace_newer_version_feedback(page):
            page.add_init_script("""window.releaseVersionOriginal = null;
              const realFetch = window.fetch;
              window.fetch = async (...args) => {
                const response = await realFetch(...args);
                if (String(args[0]).endsWith('/models/cable_comb.stl')) await new Promise(resolve => window.releaseVersionOriginal = resolve);
                return response;
              };""")
            jobs = setup(page, [record('cable_comb', 'Cable routing'), record('parts_tray', 'Original tray', 2)])
            open_version(page, 'Cable routing')
            page.wait_for_function('() => window.releaseVersionOriginal !== null')
            expect(page.locator('#form-message')).to_contain_text('Version “Cable routing” loaded')
            expect(page.locator('#param-cable_diameters')).to_be_focused()
            assert page.locator('#download').is_disabled()
            open_version(page, 'Original tray')
            expect(page.locator('#download')).to_be_enabled()
            current = page.locator('#version-message').inner_text()
            page.evaluate('() => window.releaseVersionOriginal()')
            expect(page.locator('#model-title')).to_have_text(catalog['parts_tray']['title'])
            assert page.locator('#version-message').inner_text() == current and not jobs

        def named_actions_supersede_late_local_file_reads(page):
            jobs = setup(page, [record('parts_tray', 'Original tray')])
            page.locator('#param-length').fill('180.5')
            cable = {'model': 'cable_comb', 'parameters': catalog['cable_comb']['defaults'], 'units': 'mm'}
            page.locator('#dimensions-file').set_input_files({'name': 'slow-cable.json', 'mimeType': 'application/json', 'buffer': json.dumps(cable).encode('utf-8')})
            page.wait_for_function('() => window.pendingDimensionReads.length === 1')
            save(page, 'Wide tray')
            page.evaluate('() => window.pendingDimensionReads[0]()')
            expect(page.locator('#param-length')).to_have_value('180.5')
            assert stored(page)[0]['dimensions']['parameters']['length'] == 180.5
            page.locator('#dimensions-file').set_input_files({'name': 'slow-again.json', 'mimeType': 'application/json', 'buffer': json.dumps(cable).encode('utf-8')})
            page.wait_for_function('() => window.pendingDimensionReads.length === 2')
            open_version(page, 'Original tray')
            page.evaluate('() => window.pendingDimensionReads[1]()')
            expect(page.locator('#param-length')).to_have_value('150')
            expect(page.locator('#download')).to_be_enabled()
            expect(page.locator('#form-message')).to_contain_text('Original tray')
            assert not jobs

        def active_build_blocks_named_actions_without_losing_measurements(page):
            waiting = []
            jobs = setup(page, waiting=waiting)
            save(page, 'Original')
            original = stored(page)
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            expect(page.locator('#stop-build')).to_be_visible()
            before = page.locator('#form-message').inner_text()
            for action in ('save-version', 'load-version', 'remove-version'):
                expect(page.locator('#' + action)).to_be_disabled()
                page.locator('#' + action).dispatch_event('click')
            page.locator('#version-name').fill('During build')
            page.locator('#version-name').press('Enter')
            assert stored(page) == original
            assert page.locator('#form-message').inner_text() == before
            assert page.locator('#param-length').input_value() == '180.5'
            while not waiting:
                page.wait_for_timeout(20)
            _, metadata, mesh = fixtures['parts_tray']
            waiting[0].fulfill(body=mesh, headers=headers({**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}, 'model/stl'))
            expect(page.locator('#download')).to_be_enabled()
            expect(page.locator('#version-name')).to_be_focused()
            assert download(page)[1] == mesh and len(jobs) == 1

        def mobile_and_desktop_version_controls_keep_keyboard_downloads(page):
            setup(page)
            save(page, 'Original tray', keyboard=True)
            page.locator('#param-length').fill('180.5')
            build(page)
            save(page, 'Desk drawer · wider tray', keyboard=True)
            page.locator('.named-versions').scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / 'review/cloud_versions_desktop.png'))
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('.named-versions').scroll_into_view_if_needed()
            for control in ('version-name', 'version-choice', 'save-version', 'load-version', 'remove-version'):
                box = page.locator('#' + control).bounding_box()
                assert box and box['height'] >= 44 and box['width'] >= 44, (control, box)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('#editor').evaluate('(el) => el.scrollWidth <= el.clientWidth')
            page.screenshot(path=str(ROOT / 'review/cloud_versions_mobile.png'))
            page.locator('#remove-version').focus()
            page.keyboard.press('Enter')
            expect(page.locator('#version-choice')).to_be_focused()
            expect(page.locator('#download')).to_be_enabled()
            page.locator('#download').focus()
            with page.expect_download() as event:
                page.keyboard.press('Enter')
            assert Path(event.value.path()).read_bytes() == fixtures['parts_tray'][2]

        for test in (save_unbuilt_decimals_refresh_open_and_download_exact_files,
                     matching_version_reuses_preview_and_cached_cad,
                     cross_model_lists_keep_order_and_normal_history,
                     assembly_versions_use_canonical_inventory_and_component_navigation,
                     name_field_validation_duplicates_and_html_labels_preserve_versions,
                     version_limit_and_removal_preserve_current_fields_and_files,
                     corrupt_storage_is_preserved_and_portable_dimensions_still_work,
                     quota_failures_and_denied_reads_keep_the_current_preview,
                     delayed_cross_model_preview_cannot_replace_newer_version_feedback,
                     named_actions_supersede_late_local_file_reads,
                     active_build_blocks_named_actions_without_losing_measurements,
                     mobile_and_desktop_version_controls_keep_keyboard_downloads):
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
    report = dict(endpoint=BASE, passed=passed, failures=failures, max_versions=20, transport='compiled assets and real CAD fixtures' if OFFLINE else 'local HTTP')
    (ROOT / 'review/cloud_versions_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    assert not failures, report


if __name__ == '__main__':
    main()
