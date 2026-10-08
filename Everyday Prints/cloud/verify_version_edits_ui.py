"""Verify in-place named-version edits without changing preview correspondence."""
import copy
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
    catalog = {item['name']: item for item in json.loads((CLOUD / 'public/catalog.json').read_text(encoding='utf-8'))['models']}
    passed, failures = [], []

    def record(model='parts_tray', name='Original', number=1, parameters=None):
        return dict(id=f'00000000-0000-4000-8000-{number:012x}', name=name,
                    dimensions=dict(model=model, units='mm', parameters=copy.deepcopy(parameters or catalog[model]['defaults'])))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])

        def setup(page, rows=None, model='parts_tray', waiting=None):
            page.add_init_script(FILES)
            page.add_init_script('localStorage.setItem(' + json.dumps(KEY) + ',' + json.dumps(json.dumps(rows if rows is not None else [record()])) + ');')
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
                    route.fulfill(body=mesh, headers=headers({**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}, 'model/stl'))

            page.route('**/api/generate', generate)
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            page.locator(f'[data-model="{model}"]').click()
            expect(page.locator('#download-cad')).to_be_enabled()
            page.locator('.saved-dimensions summary').click()
            page.locator('#version-choice').select_option((rows or [record()])[0]['id'])
            return jobs

        def stored(page):
            return page.evaluate('key => JSON.parse(localStorage.getItem(key) || "[]")', KEY)

        def rename(page, name, keyboard=False):
            page.locator('#version-name').fill(name)
            page.locator('#rename-version').focus()
            page.keyboard.press('Enter') if keyboard else page.locator('#rename-version').click()

        def replace(page, keyboard=False):
            page.locator('#replace-version').focus()
            page.keyboard.press('Enter') if keyboard else page.locator('#replace-version').click()

        def download(page, button='download'):
            with page.expect_download() as event:
                page.locator('#' + button).click()
            return event.value.suggested_filename, Path(event.value.path()).read_bytes()

        def build(page):
            page.locator('#rebuild').click()
            expect(page.locator('#download')).to_be_enabled(timeout=90000)

        def release(page, number):
            page.evaluate('n => window.pendingDimensionReads[n]()', number)
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')

        def file(page, control, body, name):
            page.locator('#' + control).set_input_files(dict(name=name, mimeType='application/json', buffer=json.dumps(body).encode('utf-8')))

        def rename_keeps_invalid_drafts_preview_and_cached_cad(page):
            jobs = setup(page)
            page.locator('#param-length').fill('180.5')
            build(page)
            cad = download(page, 'download-cad')
            page.locator('#param-length').fill('')
            before = page.locator('#form-message').inner_text()
            old = stored(page)
            rename(page, 'Shelf <wide> 🧰')
            assert stored(page) == [{**old[0], 'name': 'Shelf <wide> 🧰'}]
            expect(page.locator('#version-name')).to_have_value('')
            expect(page.locator('#param-length')).to_have_value('')
            assert page.locator('#form-message').inner_text() == before
            assert page.locator('#download').is_disabled()
            assert page.locator('#version-choice option').filter(has_text='Shelf <wide> 🧰').count() == 1
            page.locator('#param-length').fill('180.5')
            assert download(page, 'download-cad') == cad and len(jobs) == 2
            assert download(page)[1] == fixtures['parts_tray'][2]

        def replacement_in_full_library_keeps_identity_and_builds_exact_decimal_files(page):
            rows = [record(name=f'Tray {n}', number=n + 1) for n in range(20)]
            jobs = setup(page, rows)
            page.locator('#param-length').fill('180.5')
            replace(page)
            updated = stored(page)
            assert updated[0]['dimensions']['parameters']['length'] == 180.5
            assert updated[0]['name'] == rows[0]['name'] and updated[0]['id'] == rows[0]['id']
            assert updated[1:] == rows[1:] and not jobs
            assert page.locator('#download').is_disabled()
            page.locator('#param-length').fill('190.55')
            page.locator('#load-version').click()
            expect(page.locator('#param-length')).to_have_value('180.5')
            build(page)
            name, mesh = download(page)
            assert '-180.5x100x24mm-' in name and mesh == fixtures['parts_tray'][2]
            assert download(page, 'download-cad')[1] == fixtures['parts_tray'][0] and len(jobs) == 2

        def ordered_lists_and_renamed_backup_keep_precise_values(page):
            jobs = setup(page, [record('cable_comb', 'Routing')], model='cable_comb')
            parameters = fixtures['cable_comb'][1]['parameters']
            for key, value in parameters.items():
                page.locator('#param-' + key).fill(', '.join(map(str, value)) if isinstance(value, list) else str(value))
            replace(page)
            rename(page, 'Bench routing')
            payload = json.loads(download(page, 'export-versions')[1])
            assert payload['versions'][0]['name'] == 'Bench routing'
            assert payload['versions'][0]['dimensions']['parameters'] == parameters
            assert 'id' not in payload['versions'][0] and not jobs
            page.locator('#load-version').click()
            build(page)
            assert download(page)[1] == fixtures['cable_comb'][2]

        def invalid_names_duplicates_and_invalid_fields_leave_records_untouched(page):
            rows = [record(), record(name='Second', number=2)]
            setup(page, rows)
            rename(page, ' ')
            expect(page.locator('#version-name')).to_be_focused()
            expect(page.locator('#version-name')).to_have_attribute('aria-invalid', 'true')
            rename(page, ' SECOND ')
            expect(page.locator('#version-message')).to_contain_text('already has')
            page.locator('#param-columns').fill('1.5')
            replace(page)
            expect(page.locator('#param-columns')).to_be_focused()
            expect(page.locator('#param-columns')).to_have_attribute('aria-invalid', 'true')
            assert stored(page) == rows
            rename(page, 'Correction')
            expect(page.locator('#param-columns')).to_have_value('1.5')
            expect(page.locator('#param-columns')).to_have_attribute('aria-invalid', 'true')
            assert stored(page)[0]['name'] == 'Correction'

        def cross_model_selection_can_be_renamed_but_cannot_replace_measurements(page):
            rows = [record('cable_comb', 'Routing'), record(name='Desk', number=2)]
            jobs = setup(page, rows)
            expect(page.locator('#replace-version')).to_be_disabled()
            page.locator('#replace-version').dispatch_event('click')
            expect(page.locator('#version-message')).to_contain_text('Open this version')
            assert stored(page) == rows
            rename(page, 'Desk')
            assert stored(page)[0]['name'] == 'Desk' and not jobs
            expect(page.locator('#model-title')).to_have_text(catalog['parts_tray']['title'])
            expect(page.locator('#param-length')).to_have_value('150')
            page.locator('#load-version').click()
            expect(page.locator('#model-title')).to_have_text(catalog['cable_comb']['title'])
            expect(page.locator('#replace-version')).to_be_enabled()

        def fresh_records_and_removed_selections_are_respected(page):
            setup(page)
            newest = [record(name='Saved elsewhere', number=2), record()]
            page.evaluate('args => localStorage.setItem(...args)', [KEY, json.dumps(newest)])
            rename(page, 'Renamed')
            assert stored(page)[0] == newest[0] and stored(page)[1]['name'] == 'Renamed'
            page.locator('#param-length').fill('180.555')
            replace(page)
            assert stored(page)[0] == newest[0] and stored(page)[1]['dimensions']['parameters']['length'] == 180.555
            page.evaluate('args => localStorage.setItem(...args)', [KEY, json.dumps([newest[0]])])
            rename(page, 'Missing')
            expect(page.locator('#version-message')).to_contain_text('no longer saved')
            replace(page)
            expect(page.locator('#version-message')).to_contain_text('no longer saved')
            assert stored(page) == [newest[0]]

        def denied_writes_and_unchanged_actions_preserve_records_and_downloads(page):
            setup(page)
            original = stored(page)
            page.evaluate("""key => {
              const write = Storage.prototype.setItem;
              Storage.prototype.setItem = function(name, value) {
                if (this === localStorage && name === key) throw new DOMException('Full', 'QuotaExceededError');
                return write.call(this, name, value);
              };
            }""", KEY)
            rename(page, 'Original')
            expect(page.locator('#version-message')).to_contain_text('renamed')
            replace(page)
            expect(page.locator('#version-message')).to_contain_text('Dimensions replaced')
            rename(page, 'Changed')
            expect(page.locator('#version-message')).to_contain_text('could not be renamed')
            page.locator('#param-length').fill('180.5')
            replace(page)
            expect(page.locator('#version-message')).to_contain_text('could not be replaced')
            assert stored(page) == original
            page.locator('#param-length').fill('150')
            assert download(page)[0] == 'parts_tray.stl'
            page.evaluate("""key => {
              const read = Storage.prototype.getItem;
              Storage.prototype.getItem = function(name) {
                if (this === localStorage && name === key) throw new DOMException('Denied', 'SecurityError');
                return read.call(this, name);
              };
            }""", KEY)
            rename(page, 'Changed')
            expect(page.locator('#version-message')).to_contain_text('storage is unavailable')
            replace(page)
            expect(page.locator('#version-message')).to_contain_text('storage is unavailable')
            expect(page.locator('#download')).to_be_enabled()

        def corrupt_storage_is_kept_and_portable_dimensions_remain_available(page):
            setup(page)
            for bad in ('broken', '{}'):
                page.evaluate('args => localStorage.setItem(...args)', [KEY, bad])
                rename(page, 'Changed')
                expect(page.locator('#version-message')).to_contain_text('could not be read')
                replace(page)
                expect(page.locator('#version-message')).to_contain_text('could not be read')
                assert page.evaluate('key => localStorage.getItem(key)', KEY) == bad
            assert json.loads(download(page, 'save-dimensions')[1])['parameters'] == catalog['parts_tray']['defaults']

        def assembly_replacement_derives_canonical_inventory_without_geometry_claims(page):
            row = record('soap_dish_assembly', 'Bathroom set')
            row['dimensions']['kit'] = [{'model': 'parts_tray', 'quantity': 999}]
            row['dimensions']['bounds_mm'] = [999, 999, 999]
            jobs = setup(page, [row], model='soap_dish_assembly')
            page.locator('#param-length').fill('130')
            replace(page)
            updated = stored(page)[0]
            assert updated['id'] == row['id'] and updated['name'] == row['name']
            assert updated['dimensions']['kit'] == catalog['soap_dish_assembly']['kit']
            assert 'bounds_mm' not in updated['dimensions'] and not jobs
            assert page.locator('#download').is_hidden()
            assert page.locator('#download-cad').is_disabled()
            assert json.loads(download(page, 'save-dimensions')[1])['kit'] == catalog['soap_dish_assembly']['kit']

        def new_edits_supersede_pending_backups_without_late_merges(page):
            setup(page)
            body = dict(format='everyday-prints-versions', version=1, versions=[record('cable_comb', 'Late routing')])
            for number, action in enumerate(('rename', 'replace')):
                file(page, 'versions-file', body, f'slow-backup-{number}.json')
                page.wait_for_function('n => window.pendingDimensionReads.length === n', arg=number + 1)
                rename(page, 'Changed') if action == 'rename' else replace(page)
                original = stored(page)
                expect(page.locator('#version-backup-message')).to_contain_text('stopped')
                release(page, number)
                assert stored(page) == original
                expect(page.locator('#version-backup-message')).to_contain_text('stopped')

        def replacement_cancels_pending_dimensions_while_rename_keeps_independent_file_feedback(page):
            setup(page)
            file(page, 'dimensions-file', dict(model='parts_tray', units='mm', parameters={'length': 190.55}), 'slow-dimensions.json')
            page.wait_for_function('() => window.pendingDimensionReads.length === 1')
            replace(page)
            release(page, 0)
            expect(page.locator('#param-length')).to_have_value('150')
            file(page, 'dimensions-file', dict(model='parts_tray', units='mm', parameters={'length': 180.5}), 'slow-after-rename.json')
            page.wait_for_function('() => window.pendingDimensionReads.length === 2')
            rename(page, 'Renamed')
            release(page, 1)
            expect(page.locator('#param-length')).to_have_value('180.5')
            expect(page.locator('#form-message')).to_contain_text('Saved dimensions loaded')
            assert stored(page)[0]['name'] == 'Renamed' and stored(page)[0]['dimensions']['parameters']['length'] == 150

        def active_cad_work_guards_edits_and_keeps_retry_focus(page):
            waiting = []
            jobs = setup(page, waiting=waiting)
            original = stored(page)
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            for action in ('rename-version', 'replace-version'):
                expect(page.locator('#' + action)).to_be_disabled()
                page.locator('#' + action).dispatch_event('click')
            assert stored(page) == original
            page.wait_for_function('() => document.querySelector("#stop-build").hidden === false')
            while not waiting:
                page.wait_for_timeout(20)
            page.locator('#stop-build').click()
            expect(page.locator('#rename-version')).to_be_enabled()
            expect(page.locator('#replace-version')).to_be_enabled()
            rename(page, 'After Stop')
            assert stored(page)[0]['name'] == 'After Stop' and len(jobs) == 1
            _, metadata, mesh = fixtures['parts_tray']
            waiting[0].fulfill(body=mesh, headers=headers({**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}, 'model/stl'))
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            assert stored(page)[0]['name'] == 'After Stop'
            expect(page.locator('#param-length')).to_have_value('180.5')
            assert page.locator('#download').is_disabled()

        def late_original_preview_uses_the_renamed_open_version(page):
            page.add_init_script("""window.releaseVersionOriginal = null;
              const realFetch = window.fetch;
              window.fetch = async (...args) => {
                const response = await realFetch(...args);
                if (String(args[0]).endsWith('/models/cable_comb.stl')) await new Promise(resolve => window.releaseVersionOriginal = resolve);
                return response;
              };""")
            jobs = setup(page, [record('cable_comb', 'Routing')])
            page.locator('#load-version').click()
            page.wait_for_function('() => window.releaseVersionOriginal !== null')
            rename(page, 'Bench routing')
            page.evaluate('() => window.releaseVersionOriginal()')
            expect(page.locator('#download')).to_be_enabled()
            expect(page.locator('#form-message')).to_contain_text('Version “Bench routing” loaded')
            expect(page.locator('#version-message')).to_contain_text('renamed to “Bench routing”')
            assert stored(page)[0]['name'] == 'Bench routing' and not jobs

        def mobile_keyboard_edits_keep_reachable_controls_and_exact_downloads(page):
            jobs = setup(page)
            page.locator('#param-length').fill('180.5')
            build(page)
            cad = download(page, 'download-cad')
            rename(page, 'Desk drawer · measured', keyboard=True)
            expect(page.locator('#rename-version')).to_be_focused()
            replace(page, keyboard=True)
            expect(page.locator('#replace-version')).to_be_focused()
            page.locator('.named-versions').scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / 'review/cloud_version_edits_desktop.png'))
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('.version-actions').scroll_into_view_if_needed()
            for control in ('rename-version', 'replace-version', 'load-version', 'remove-version', 'version-name', 'version-choice'):
                box = page.locator('#' + control).bounding_box()
                assert box and box['width'] >= 44 and box['height'] >= 44, (control, box)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('#editor').evaluate('(el) => el.scrollWidth <= el.clientWidth')
            page.screenshot(path=str(ROOT / 'review/cloud_version_edits_mobile.png'))
            rename(page, 'Mobile dimensions', keyboard=True)
            replace(page, keyboard=True)
            assert download(page, 'download-cad') == cad and len(jobs) == 2
            assert download(page)[1] == fixtures['parts_tray'][2]

        tests = (rename_keeps_invalid_drafts_preview_and_cached_cad,
                 replacement_in_full_library_keeps_identity_and_builds_exact_decimal_files,
                 ordered_lists_and_renamed_backup_keep_precise_values,
                 invalid_names_duplicates_and_invalid_fields_leave_records_untouched,
                 cross_model_selection_can_be_renamed_but_cannot_replace_measurements,
                 fresh_records_and_removed_selections_are_respected,
                 denied_writes_and_unchanged_actions_preserve_records_and_downloads,
                 corrupt_storage_is_kept_and_portable_dimensions_remain_available,
                 assembly_replacement_derives_canonical_inventory_without_geometry_claims,
                 new_edits_supersede_pending_backups_without_late_merges,
                 replacement_cancels_pending_dimensions_while_rename_keeps_independent_file_feedback,
                 active_cad_work_guards_edits_and_keeps_retry_focus,
                 late_original_preview_uses_the_renamed_open_version,
                 mobile_keyboard_edits_keep_reachable_controls_and_exact_downloads)
        for test in tests:
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
    report = dict(endpoint=BASE, passed=passed, failures=failures,
                  transport='compiled assets and real CAD fixtures' if OFFLINE else 'local HTTP')
    (ROOT / 'review/cloud_version_edits_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    assert not failures, report


if __name__ == '__main__':
    main()
