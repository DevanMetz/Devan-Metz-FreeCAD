"""Verify one-step saved-library undo and protection of newer stored records."""
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
SNAPSHOT_BASELINE = '--snapshot-baseline' in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5178')
KEY = 'everyday-prints-versions'
sys.stdout.reconfigure(encoding='utf-8')
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
            rows = [record()] if rows is None else rows
            page.add_init_script(FILES)
            page.add_init_script('if (localStorage.getItem(' + json.dumps(KEY) + ') === null) localStorage.setItem(' + json.dumps(KEY) + ',' + json.dumps(json.dumps(rows)) + ');')
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
            expect(page.locator('#undo-version')).to_be_hidden()
            if rows:
                page.locator('#version-choice').select_option(rows[0]['id'])
            return jobs

        def stored(page):
            return page.evaluate('key => JSON.parse(localStorage.getItem(key) || "[]")', KEY)

        def undo(page, keyboard=False):
            expect(page.locator('#undo-version')).to_be_enabled()
            page.locator('#undo-version').focus()
            page.keyboard.press('Enter') if keyboard else page.locator('#undo-version').click()

        def rename(page, name):
            page.locator('#version-name').fill(name)
            page.locator('#rename-version').click()

        def download(page, button='download'):
            with page.expect_download() as event:
                page.locator('#' + button).click()
            return event.value.suggested_filename, Path(event.value.path()).read_bytes()

        def build(page):
            page.locator('#rebuild').click()
            expect(page.locator('#download')).to_be_enabled(timeout=90000)

        def file(page, control, body, name):
            page.locator('#' + control).set_input_files(dict(name=name, mimeType='application/json', buffer=json.dumps(body).encode('utf-8')))

        def release(page, number):
            page.evaluate('n => window.pendingDimensionReads[n]()', number)
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')

        def snapshot_matches_the_state_read_by_the_mutation(page, baseline=False):
            setup(page)
            newer = record(name='Intervening version', number=2)
            page.evaluate("""args => {
              const read = Storage.prototype.getItem, write = Storage.prototype.setItem;
              window.historyReads = 0; window.historyBeforeWrite = null;
              Storage.prototype.getItem = function(name) {
                if (this === localStorage && name === args[0] && !window.historyBeforeWrite && ++window.historyReads === 2) {
                  write.call(this, name, JSON.stringify([...JSON.parse(read.call(this, name)), args[1]]));
                }
                return read.call(this, name);
              };
              Storage.prototype.setItem = function(name, value) {
                if (this === localStorage && name === args[0] && !window.historyBeforeWrite) window.historyBeforeWrite = JSON.parse(read.call(this, name));
                return write.call(this, name, value);
              };
            }""", [KEY, newer])
            rename(page, 'Changed')
            expected = page.evaluate('window.historyBeforeWrite')
            undo(page)
            restored = stored(page)
            if baseline:
                report = dict(storage_reads_before_mutation=page.evaluate('window.historyReads'), library_used_by_mutation=expected,
                              restored_library=restored, lost_intervening_version=restored != expected)
                assert report['lost_intervening_version'] and len(expected) == 2 and len(restored) == 1, report
                (ROOT / 'review/cloud_versions_undo_snapshot_baseline.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                print(json.dumps(report), flush=True)
            else:
                assert restored == expected, (restored, expected)
                expect(page.locator('#param-length')).to_have_value('150')

        if SNAPSHOT_BASELINE:
            context = browser.new_context(accept_downloads=True)
            if OFFLINE:
                attach_assets(context)
            page = context.new_page()
            snapshot_matches_the_state_read_by_the_mutation(page, baseline=True)
            context.close()
            browser.close()
            return

        def removal_restores_full_library_order_identity_and_selection(page):
            rows = [record(name=f'Tray {n}', number=n + 1, parameters={**catalog['parts_tray']['defaults'], 'length': 150 + n / 10}) for n in range(20)]
            jobs = setup(page, rows)
            page.locator('#version-choice').select_option(rows[8]['id'])
            page.locator('#param-length').fill('')
            page.locator('#version-name').fill('Unsaved name')
            before = (page.url, page.locator('#form-message').inner_text(), page.locator('#model-size').inner_text())
            page.locator('#remove-version').click()
            assert len(stored(page)) == 19
            undo(page)
            assert stored(page) == rows and not jobs
            expect(page.locator('#version-choice')).to_have_value(rows[8]['id'])
            expect(page.locator('#version-choice')).to_be_focused()
            expect(page.locator('#undo-version')).to_be_hidden()
            expect(page.locator('#param-length')).to_have_value('')
            expect(page.locator('#version-name')).to_have_value('Unsaved name')
            assert before == (page.url, page.locator('#form-message').inner_text(), page.locator('#model-size').inner_text())
            assert page.locator('#download').is_disabled()

        def undo_replacement_keeps_verified_custom_files_and_cached_cad(page):
            jobs = setup(page)
            original = stored(page)
            page.locator('#param-length').fill('180.5')
            build(page)
            cad = download(page, 'download-cad')
            page.locator('#replace-version').click()
            assert stored(page)[0]['dimensions']['parameters']['length'] == 180.5
            undo(page)
            assert stored(page) == original
            expect(page.locator('#param-length')).to_have_value('180.5')
            assert download(page, 'download-cad') == cad
            assert download(page)[1] == fixtures['parts_tray'][2] and len(jobs) == 2
            page.locator('#load-version').click()
            expect(page.locator('#param-length')).to_have_value('150')
            assert page.locator('#download').is_disabled()
            page.locator('#revert-parameters').click()
            assert download(page, 'download-cad') == cad and len(jobs) == 2

        def rename_undo_keeps_invalid_fields_and_new_name_draft(page):
            setup(page)
            original = stored(page)
            page.locator('#param-columns').fill('1.5')
            before = page.locator('#form-message').inner_text()
            rename(page, 'Renamed <tray> 🧰')
            page.locator('#version-name').fill('Next name')
            undo(page)
            assert stored(page) == original
            expect(page.locator('#version-name')).to_have_value('Next name')
            expect(page.locator('#param-columns')).to_have_value('1.5')
            expect(page.locator('#param-columns')).to_have_attribute('aria-invalid', 'true')
            assert page.locator('#form-message').inner_text() == before

        def only_the_latest_successful_save_can_be_undone(page):
            setup(page)
            original = stored(page)
            for name in ('First save', 'Latest save'):
                page.locator('#version-name').fill(name)
                page.locator('#save-version').click()
            before = stored(page)
            undo(page)
            assert stored(page) == before[1:]
            assert [row['name'] for row in stored(page)] == ['First save', 'Original']
            expect(page.locator('#version-choice')).to_have_value(before[1]['id'])
            expect(page.locator('#undo-version')).to_be_hidden()
            page.locator('#undo-version').dispatch_event('click')
            assert stored(page) == before[1:] and stored(page)[-1] == original[0]

        def multi_model_backup_import_undo_restores_the_prior_library_atomically(page):
            setup(page)
            original = stored(page)
            incoming = [record('cable_comb', 'Routing', 2, fixtures['cable_comb'][1]['parameters']), record(name='Wide tray', number=3, parameters=fixtures['parts_tray'][1]['parameters'])]
            file(page, 'versions-file', dict(format='everyday-prints-versions', version=1, versions=incoming), 'versions.json')
            expect(page.locator('#version-backup-message')).to_contain_text('Imported 2 versions')
            assert len(stored(page)) == 3
            undo(page)
            assert stored(page) == original
            exported = json.loads(download(page, 'export-versions')[1])
            assert [row['name'] for row in exported['versions']] == ['Original']
            expect(page.locator('#param-length')).to_have_value('150')

        def unchanged_actions_and_failed_mutations_keep_the_last_real_undo(page):
            setup(page)
            original = stored(page)
            rename(page, 'Changed')
            changed = stored(page)
            rename(page, 'Changed')
            page.locator('#replace-version').click()
            file(page, 'versions-file', dict(format='everyday-prints-versions', version=1, versions=changed), 'repeat.json')
            expect(page.locator('#version-backup-message')).to_contain_text('already saved')
            rename(page, ' ')
            expect(page.locator('#version-name')).to_have_attribute('aria-invalid', 'true')
            page.locator('#param-length').fill('')
            page.locator('#replace-version').click()
            assert stored(page) == changed
            undo(page)
            assert stored(page) == original
            expect(page.locator('#param-length')).to_have_value('')
            expect(page.locator('#version-name')).to_have_attribute('aria-invalid', 'true')

        def quota_denied_and_corrupt_storage_preserve_records_and_allow_retry(page):
            setup(page)
            original = stored(page)
            page.locator('#remove-version').click()
            page.evaluate("""key => {
              const read = Storage.prototype.getItem, write = Storage.prototype.setItem;
              window.denyUndoRead = false; window.denyUndoWrite = true;
              Storage.prototype.getItem = function(name) {
                if (this === localStorage && name === key && window.denyUndoRead) throw new DOMException('Denied', 'SecurityError');
                return read.call(this, name);
              };
              Storage.prototype.setItem = function(name, value) {
                if (this === localStorage && name === key && window.denyUndoWrite) throw new DOMException('Full', 'QuotaExceededError');
                return write.call(this, name, value);
              };
            }""", KEY)
            undo(page)
            expect(page.locator('#version-message')).to_contain_text('Undo could not be saved')
            assert stored(page) == []
            expect(page.locator('#undo-version')).to_be_enabled()
            page.evaluate('window.denyUndoRead = true; window.denyUndoWrite = false')
            undo(page)
            expect(page.locator('#version-message')).to_contain_text('storage is unavailable')
            page.evaluate('window.denyUndoRead = false')
            page.evaluate('args => localStorage.setItem(...args)', [KEY, 'broken'])
            undo(page)
            expect(page.locator('#version-message')).to_contain_text('could not be read')
            assert page.evaluate('key => localStorage.getItem(key)', KEY) == 'broken'
            page.evaluate('args => localStorage.setItem(...args)', [KEY, '[]'])
            undo(page)
            assert stored(page) == original
            expect(page.locator('#download')).to_be_enabled()

        def external_changes_clear_undo_but_unchanged_events_keep_it(page):
            setup(page)
            rename(page, 'Changed')
            peer = page.context.new_page()
            peer.goto(BASE + '/favicon.svg')
            page.locator('#undo-version').focus()
            peer.evaluate("localStorage.setItem('unrelated', 'changed')")
            page.evaluate("""key => dispatchEvent(new StorageEvent('storage', { key, storageArea: localStorage, newValue: 'obsolete' }))""", KEY)
            expect(page.locator('#undo-version')).to_be_focused()
            expect(page.locator('#undo-version')).to_be_enabled()
            latest = [record(name='Newer tab')]
            peer.evaluate('args => localStorage.setItem(...args)', [KEY, json.dumps(latest)])
            expect(page.locator('#undo-version')).to_be_hidden()
            expect(page.locator('#version-choice')).to_be_focused()
            assert stored(page) == latest
            page.locator('#undo-version').dispatch_event('click')
            assert stored(page) == latest

        def unseen_newer_records_block_undo_and_refresh_the_list(page):
            setup(page)
            rename(page, 'Changed')
            latest = [record(name='Unseen newer', parameters={**catalog['parts_tray']['defaults'], 'length': 190.55})]
            page.evaluate("""args => {
              localStorage.setItem(...args);
              document.querySelector('#undo-version').click();
            }""", [KEY, json.dumps(latest)])
            expect(page.locator('#version-message')).to_contain_text('cannot replace newer versions')
            expect(page.locator('#undo-version')).to_be_hidden()
            assert page.locator('#version-choice option').filter(has_text='Unseen newer').count() == 1
            assert stored(page) == latest
            expect(page.locator('#param-length')).to_have_value('150')

        def undo_supersedes_backups_and_keeps_independent_dimension_file_feedback(page):
            setup(page)
            original = stored(page)
            rename(page, 'Changed')
            body = dict(format='everyday-prints-versions', version=1, versions=[record('cable_comb', 'Late')])
            file(page, 'versions-file', body, 'slow-backup.json')
            page.wait_for_function('() => window.pendingDimensionReads.length === 1')
            file(page, 'dimensions-file', dict(model='parts_tray', units='mm', parameters={'length': 180.5}), 'slow-dimensions.json')
            page.wait_for_function('() => window.pendingDimensionReads.length === 2')
            undo(page)
            expect(page.locator('#version-backup-message')).to_contain_text('stopped')
            expect(page.locator('#form-message')).to_contain_text('Loading saved dimensions')
            release(page, 0)
            assert stored(page) == original
            release(page, 1)
            expect(page.locator('#param-length')).to_have_value('180.5')
            expect(page.locator('#form-message')).to_contain_text('Saved dimensions loaded')
            assert stored(page) == original

        def assembly_undo_and_editor_navigation_keep_canonical_inventory(page):
            jobs = setup(page, [record('soap_dish_assembly', 'Bathroom')], model='soap_dish_assembly')
            page.locator('#param-length').fill('130')
            page.locator('#replace-version').click()
            page.locator('#part-links button').first.click()
            expect(page.locator('#mesh-status')).to_have_text('Update preview to apply edits')
            expect(page.locator('#param-length')).to_have_value('130')
            expect(page.locator('#download')).to_be_disabled()
            title = page.locator('#model-title').inner_text()
            if not page.locator('.saved-dimensions').evaluate('(el) => el.open'):
                page.locator('.saved-dimensions summary').click()
            undo(page)
            restored = stored(page)[0]
            assert restored['dimensions']['parameters'] == catalog['soap_dish_assembly']['defaults']
            assert restored['dimensions']['kit'] == catalog['soap_dish_assembly']['kit']
            assert page.locator('#model-title').inner_text() == title and not jobs
            expect(page.locator('#param-length')).to_have_value('130')
            expect(page.locator('#download')).to_be_disabled()

        def mobile_keyboard_busy_guard_and_refresh_keep_exact_downloads(page):
            waiting = []
            jobs = setup(page, waiting=waiting)
            rename(page, 'Changed')
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            expect(page.locator('#undo-version')).to_be_disabled()
            page.locator('#undo-version').dispatch_event('click')
            assert stored(page)[0]['name'] == 'Changed'
            while not waiting:
                page.wait_for_timeout(20)
            _, metadata, mesh = fixtures['parts_tray']
            waiting[0].fulfill(body=mesh, headers=headers({**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}, 'model/stl'))
            expect(page.locator('#download')).to_be_enabled()
            page.set_viewport_size(dict(width=390, height=844))
            page.locator('#undo-version').scroll_into_view_if_needed()
            box = page.locator('#undo-version').bounding_box()
            assert box and box['height'] >= 44 and box['width'] >= 44
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('#editor').evaluate('(el) => el.scrollWidth <= el.clientWidth')
            page.screenshot(path=str(ROOT / 'review/cloud_versions_undo_mobile.png'))
            page.set_viewport_size(dict(width=1440, height=1080))
            page.locator('.named-versions').scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / 'review/cloud_versions_undo_desktop.png'))
            undo(page, keyboard=True)
            expect(page.locator('#version-choice')).to_be_focused()
            assert download(page)[1] == mesh and len(jobs) == 1
            rename(page, 'Before refresh')
            latest = stored(page)
            page.reload()
            expect(page.locator('#download')).to_be_disabled()
            expect(page.locator('#undo-version')).to_be_hidden()
            assert stored(page) == latest

        tests = (removal_restores_full_library_order_identity_and_selection,
                 snapshot_matches_the_state_read_by_the_mutation,
                 undo_replacement_keeps_verified_custom_files_and_cached_cad,
                 rename_undo_keeps_invalid_fields_and_new_name_draft,
                 only_the_latest_successful_save_can_be_undone,
                 multi_model_backup_import_undo_restores_the_prior_library_atomically,
                 unchanged_actions_and_failed_mutations_keep_the_last_real_undo,
                 quota_denied_and_corrupt_storage_preserve_records_and_allow_retry,
                 external_changes_clear_undo_but_unchanged_events_keep_it,
                 unseen_newer_records_block_undo_and_refresh_the_list,
                 undo_supersedes_backups_and_keeps_independent_dimension_file_feedback,
                 assembly_undo_and_editor_navigation_keep_canonical_inventory,
                 mobile_keyboard_busy_guard_and_refresh_keep_exact_downloads)
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
    report = dict(endpoint=BASE, passed=passed, failures=failures, undo_depth=1,
                  transport='compiled assets and real CAD fixtures' if OFFLINE else 'local HTTP')
    (ROOT / 'review/cloud_versions_undo_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    assert not failures, report


if __name__ == '__main__':
    main()
