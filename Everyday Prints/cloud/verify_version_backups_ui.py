"""Verify portable named-version backups and stale file-read recovery in-browser."""
import json
import copy
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

    def record(model, name, number=1, parameters=None):
        return dict(id=f'00000000-0000-4000-8000-{number:012x}', name=name,
                    dimensions={'model': model, 'units': 'mm', 'parameters': copy.deepcopy(parameters or catalog[model]['defaults'])})

    def backup(records):
        return json.dumps(dict(format='everyday-prints-versions', version=1,
                              versions=[{'name': row['name'], 'dimensions': row['dimensions']} for row in records]), ensure_ascii=False).encode('utf-8')

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])

        def setup(page, records=None, waiting=None):
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
                    route.fulfill(body=mesh, headers=headers({**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}, 'model/stl'))

            page.route('**/api/generate', generate)
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            page.locator('[data-model="parts_tray"]').click()
            expect(page.locator('#download')).to_be_enabled()
            page.locator('.saved-dimensions summary').click()
            return jobs

        def stored(page):
            return page.evaluate('key => JSON.parse(localStorage.getItem(key) || "[]")', KEY)

        def select(page, body, name='versions.json'):
            page.locator('#versions-file').set_input_files({'name': name, 'mimeType': 'application/json', 'buffer': body})

        def imported(page):
            expect(page.locator('#version-backup-message')).to_contain_text('Imported')

        def download(page, button='export-versions', keyboard=False):
            with page.expect_download() as event:
                if keyboard:
                    page.locator('#' + button).focus()
                    page.keyboard.press('Enter')
                else:
                    page.locator('#' + button).click()
            value = event.value
            return value.suggested_filename, Path(value.path()).read_bytes()

        def open_version(page, name):
            option = page.locator('#version-choice option').filter(has_text=name)
            page.locator('#version-choice').select_option(option.get_attribute('value'))
            page.locator('#load-version').click()

        def export_preserves_names_exact_values_and_canonical_inventory(page):
            rows = [record('parts_tray', 'Étagère <wide> ✓', parameters=fixtures['parts_tray'][1]['parameters']),
                    record('cable_comb', 'Cable routing', 2, fixtures['cable_comb'][1]['parameters']),
                    record('soap_dish_assembly', 'Bathroom set', 3)]
            rows[2]['dimensions']['kit'] = [{'model': 'parts_tray', 'quantity': 999}]
            rows[0]['dimensions']['bounds_mm'] = [999, 999, 999]
            jobs = setup(page, rows)
            name, body = download(page)
            assert name == 'everyday-prints-versions.json' and body.endswith(b'\n')
            exported = json.loads(body)
            assert exported['format'] == 'everyday-prints-versions' and exported['version'] == 1
            assert exported['versions'][0]['name'] == rows[0]['name']
            assert exported['versions'][1]['dimensions']['parameters'] == rows[1]['dimensions']['parameters']
            assert exported['versions'][2]['dimensions']['kit'] == catalog['soap_dish_assembly']['kit']
            assert all('id' not in row and 'bounds_mm' not in row['dimensions'] for row in exported['versions'])
            assert page.locator('#param-length').input_value() == '150' and not jobs

        def imports_keep_dirty_fields_preview_and_cached_cad(page):
            original = record('parts_tray', 'Original tray')
            jobs = setup(page, [original])
            page.locator('#version-choice').select_option(original['id'])
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            expect(page.locator('#download')).to_be_enabled()
            cad = download(page, 'download-cad')
            page.locator('#param-length').fill('190.55')
            before = page.locator('#form-message').inner_text()
            select(page, backup([record('cable_comb', 'Cable routing')]))
            imported(page)
            assert page.locator('#version-choice').input_value() == original['id']
            assert page.locator('#param-length').input_value() == '190.55'
            assert page.locator('#form-message').inner_text() == before
            assert page.locator('#download').is_disabled()
            page.locator('#revert-parameters').click()
            assert download(page, 'download-cad') == cad and len(jobs) == 2

        def exported_file_restores_in_another_browser_and_builds_exact_list_mesh(page):
            setup(page, [record('cable_comb', 'Cable routing', parameters=fixtures['cable_comb'][1]['parameters'])])
            _, body = download(page)
            context = browser.new_context(viewport={'width': 1440, 'height': 1080}, accept_downloads=True)
            context.set_default_timeout(20000)
            if OFFLINE:
                attach_assets(context)
            other = context.new_page()
            try:
                jobs = setup(other)
                expect(other.locator('#export-versions')).to_be_disabled()
                select(other, body)
                imported(other)
                open_version(other, 'Cable routing')
                expect(other.locator('#model-title')).to_have_text(catalog['cable_comb']['title'])
                values = [float(value) for value in other.locator('#param-cable_diameters').input_value().split(',')]
                assert values == fixtures['cable_comb'][1]['parameters']['cable_diameters']
                assert other.locator('#download').is_disabled()
                other.locator('#rebuild').click()
                expect(other.locator('#download')).to_be_enabled()
                assert download(other, 'download')[1] == fixtures['cable_comb'][2] and len(jobs) == 1
            finally:
                context.close()

        def conflicting_names_are_numbered_and_repeated_imports_do_not_write(page):
            old = record('parts_tray', 'Desk drawer')
            setup(page, [old])
            body = backup([record('parts_tray', 'DESK DRAWER', parameters=fixtures['parts_tray'][1]['parameters'])])
            select(page, body)
            imported(page)
            saved = stored(page)
            assert saved[0]['name'] == 'DESK DRAWER (2)' and saved[1] == old
            assert saved[0]['dimensions']['parameters']['length'] == 180.5
            page.evaluate("""key => { const original = Storage.prototype.setItem;
              Storage.prototype.setItem = function(name, value) {
                if (this === localStorage && name === key) throw new DOMException('Full', 'QuotaExceededError');
                return original.call(this, name, value);
              }; }""", KEY)
            select(page, body)
            expect(page.locator('#version-backup-message')).to_contain_text('already saved')
            assert stored(page) == saved

        def malformed_or_mixed_backups_reject_atomically(page):
            old = record('parts_tray', 'Original')
            jobs = setup(page, [old])
            valid = json.loads(backup([record('parts_tray', 'New')]))
            invalid = record('cable_comb', 'Invalid')
            invalid['dimensions']['parameters']['thickness'] = '4'
            cases = [b'broken', b'{}', json.dumps({**valid, 'version': 2}).encode(),
                     json.dumps({**valid, 'versions': []}).encode(),
                     json.dumps({**valid, 'versions': [valid['versions'][0], invalid]}).encode()]
            before = page.locator('#form-message').inner_text()
            for body in cases:
                select(page, body)
                expect(page.locator('#version-backup-message')).to_have_class('error')
                assert stored(page) == [old] and page.locator('#form-message').inner_text() == before
                assert page.locator('#download').is_enabled() and not jobs

        def capacity_failure_keeps_all_records_then_removal_allows_import(page):
            rows = [record('parts_tray', f'Existing {number}', number) for number in range(20)]
            setup(page, rows)
            body = backup([record('parts_tray', 'Incoming')])
            select(page, body)
            expect(page.locator('#version-backup-message')).to_contain_text('exceed 20')
            assert stored(page) == rows
            page.locator('#version-choice').select_option(rows[0]['id'])
            page.locator('#remove-version').click()
            select(page, body)
            imported(page)
            assert len(stored(page)) == 20 and stored(page)[0]['name'] == 'Incoming'

        def exact_byte_boundary_bom_and_oversize_keep_the_reader_bounded(page):
            setup(page)
            text = b'\xef\xbb\xbf' + backup([record('parts_tray', 'Étagère ✓')])
            boundary = text + b' ' * (65536 - len(text))
            select(page, boundary, 'boundary.json')
            imported(page)
            saved = stored(page)
            reads = page.evaluate('window.fileReads')
            select(page, boundary + 'é'.encode('utf-8'), 'oversized.json')
            expect(page.locator('#version-backup-message')).to_contain_text('exceeds 64 KiB')
            assert page.evaluate('window.fileReads') == reads and stored(page) == saved

        def unreadable_and_stalled_reads_recover_without_late_storage_changes(page):
            page.clock.install()
            try:
                setup(page)
                body = backup([record('parts_tray', 'Late version')])
                select(page, body, 'unreadable.json')
                expect(page.locator('#version-backup-message')).to_contain_text('could not be read')
                page.clock.pause_at(page.evaluate('Date.now()') + 100)
                select(page, body, 'slow-backup.json')
                page.wait_for_function('() => window.pendingDimensionReads.length === 1')
                page.clock.fast_forward(15001)
                expect(page.locator('#version-backup-message')).to_contain_text('took too long')
                assert not stored(page) and page.locator('#download').is_enabled()
                select(page, backup([record('parts_tray', 'Newer version')]))
                imported(page)
                saved = stored(page)
                page.evaluate('() => window.pendingDimensionReads[0]()')
                assert stored(page) == saved
            finally:
                page.clock.resume()

        def newer_named_actions_supersede_a_pending_backup(page):
            rows = [record('parts_tray', 'Original'), record('parts_tray', 'Keep', 2)]
            setup(page, rows)
            for number, action in enumerate(('save', 'remove', 'open', 'export')):
                select(page, backup([record('cable_comb', 'Late routing')]), f'slow-{number}.json')
                page.wait_for_function('n => window.pendingDimensionReads.length === n', arg=number + 1)
                if action == 'save':
                    page.locator('#version-name').fill('New save')
                    page.locator('#save-version').click()
                elif action == 'remove':
                    option = page.locator('#version-choice option').filter(has_text='New save')
                    page.locator('#version-choice').select_option(option.get_attribute('value'))
                    page.locator('#remove-version').click()
                elif action == 'open':
                    open_version(page, 'Original')
                else:
                    download(page)
                expected = stored(page)
                message = page.locator('#version-backup-message').inner_text()
                page.evaluate('n => window.pendingDimensionReads[n]()', number)
                assert stored(page) == expected and page.locator('#version-backup-message').inner_text() == message

        def active_build_cancels_import_and_keeps_backup_controls_guarded(page):
            waiting = []
            jobs = setup(page, [record('parts_tray', 'Original')], waiting=waiting)
            select(page, backup([record('cable_comb', 'Late routing')]), 'slow-build.json')
            page.wait_for_function('() => window.pendingDimensionReads.length === 1')
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            expect(page.locator('#stop-build')).to_be_visible()
            for action in ('export-versions', 'import-versions'):
                expect(page.locator('#' + action)).to_be_disabled()
                page.locator('#' + action).dispatch_event('click')
            page.evaluate('() => window.pendingDimensionReads[0]()')
            expect(page.locator('#version-backup-message')).to_contain_text('import stopped')
            assert len(stored(page)) == 1
            while not waiting:
                page.wait_for_timeout(20)
            _, metadata, mesh = fixtures['parts_tray']
            waiting[0].fulfill(body=mesh, headers=headers({**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}, 'model/stl'))
            expect(page.locator('#download')).to_be_enabled()
            assert download(page, 'download')[1] == mesh and len(jobs) == 1

        def field_edits_and_dimension_file_reads_stay_independent_of_library_imports(page):
            setup(page)
            select(page, backup([record('cable_comb', 'Routing')]), 'slow-library.json')
            page.wait_for_function('() => window.pendingDimensionReads.length === 1')
            page.locator('#param-length').fill('190.55')
            dimensions = {'model': 'parts_tray', 'units': 'mm', 'parameters': fixtures['parts_tray'][1]['parameters']}
            page.locator('#dimensions-file').set_input_files({'name': 'dimensions.json', 'mimeType': 'application/json', 'buffer': json.dumps(dimensions).encode()})
            expect(page.locator('#param-length')).to_have_value('180.5')
            before = page.locator('#form-message').inner_text()
            page.evaluate('() => window.pendingDimensionReads[0]()')
            imported(page)
            assert page.locator('#param-length').input_value() == '180.5'
            assert page.locator('#form-message').inner_text() == before and page.locator('#download').is_disabled()

        def model_navigation_and_close_discard_late_backup_reads(page):
            setup(page, [record('cable_comb', 'Routing')])
            body = backup([record('parts_tray', 'Late tray')])
            select(page, body, 'slow-navigation.json')
            page.wait_for_function('() => window.pendingDimensionReads.length === 1')
            open_version(page, 'Routing')
            expect(page.locator('#download')).to_be_enabled()
            page.evaluate('() => window.pendingDimensionReads[0]()')
            assert len(stored(page)) == 1
            select(page, body, 'slow-close.json')
            page.wait_for_function('() => window.pendingDimensionReads.length === 2')
            page.locator('#close-editor').click()
            expect(page.locator('#editor')).not_to_be_visible()
            page.evaluate('() => window.pendingDimensionReads[1]()')
            assert len(stored(page)) == 1

        def quota_denial_and_fresh_export_reads_preserve_existing_records(page):
            setup(page, [record('parts_tray', 'Original')])
            page.evaluate("""key => { const original = Storage.prototype.setItem;
              Storage.prototype.setItem = function(name, value) {
                if (this === localStorage && name === key) throw new DOMException('Full', 'QuotaExceededError');
                return original.call(this, name, value);
              }; }""", KEY)
            before = stored(page)
            select(page, backup([record('cable_comb', 'Incoming')]))
            expect(page.locator('#version-backup-message')).to_contain_text('storage is unavailable')
            assert stored(page) == before
            assert json.loads(download(page)[1])['versions'][0]['name'] == 'Original'
            page.evaluate("""key => { const original = Storage.prototype.getItem;
              Storage.prototype.getItem = function(name) {
                if (this === localStorage && name === key) throw new DOMException('Denied', 'SecurityError');
                return original.call(this, name);
              }; }""", KEY)
            page.locator('#export-versions').click()
            expect(page.locator('#version-backup-message')).to_contain_text('unavailable in this browser')
            assert page.locator('#download').is_enabled()

        def mobile_keyboard_backup_and_file_chooser_keep_verified_downloads(page):
            setup(page, [record('parts_tray', 'Desk drawer')])
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            expect(page.locator('#download')).to_be_enabled()
            _, body = download(page, keyboard=True)
            page.locator('#import-versions').focus()
            with page.expect_file_chooser() as event:
                page.keyboard.press('Enter')
            event.value.set_files({'name': 'backup.json', 'mimeType': 'application/json', 'buffer': body})
            expect(page.locator('#version-backup-message')).to_contain_text('already saved')
            expect(page.locator('#import-versions')).to_be_focused()
            expect(page.locator('#download')).to_be_enabled()
            page.locator('.named-versions').scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / 'review/cloud_version_backups_desktop.png'))
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('.version-backups').scroll_into_view_if_needed()
            for control in ('export-versions', 'import-versions'):
                box = page.locator('#' + control).bounding_box()
                assert box and box['height'] >= 44 and box['width'] >= 44, (control, box)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('#editor').evaluate('(el) => el.scrollWidth <= el.clientWidth')
            page.screenshot(path=str(ROOT / 'review/cloud_version_backups_mobile.png'))
            assert download(page, 'download', keyboard=True)[1] == fixtures['parts_tray'][2]

        for test in (export_preserves_names_exact_values_and_canonical_inventory,
                     imports_keep_dirty_fields_preview_and_cached_cad,
                     exported_file_restores_in_another_browser_and_builds_exact_list_mesh,
                     conflicting_names_are_numbered_and_repeated_imports_do_not_write,
                     malformed_or_mixed_backups_reject_atomically,
                     capacity_failure_keeps_all_records_then_removal_allows_import,
                     exact_byte_boundary_bom_and_oversize_keep_the_reader_bounded,
                     unreadable_and_stalled_reads_recover_without_late_storage_changes,
                     newer_named_actions_supersede_a_pending_backup,
                     active_build_cancels_import_and_keeps_backup_controls_guarded,
                     field_edits_and_dimension_file_reads_stay_independent_of_library_imports,
                     model_navigation_and_close_discard_late_backup_reads,
                     quota_denial_and_fresh_export_reads_preserve_existing_records,
                     mobile_keyboard_backup_and_file_chooser_keep_verified_downloads):
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
    report = dict(endpoint=BASE, passed=passed, failures=failures, max_file_bytes=65536, read_deadline_ms=15000,
                  transport='compiled assets and real CAD fixtures' if OFFLINE else 'local HTTP')
    (ROOT / 'review/cloud_version_backups_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    assert not failures, report


if __name__ == '__main__':
    main()
