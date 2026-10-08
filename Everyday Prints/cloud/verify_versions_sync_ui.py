"""Verify saved-version changes from a second real browser tab."""
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
BASELINE = '--baseline' in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5178')
KEY = 'everyday-prints-versions'
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))
EVENTS = """window.versionStorageEvents = 0;
addEventListener('storage', event => {
  if (event.storageArea === localStorage && (event.key === 'everyday-prints-versions' || event.key === null)) window.versionStorageEvents++;
});"""


def main():
    fixtures = {name: fixture(name) for name in ('parts_tray', 'cable_comb')}
    catalog = {item['name']: item for item in json.loads((CLOUD / 'public/catalog.json').read_text(encoding='utf-8'))['models']}
    passed, failures = [], []

    def record(model='parts_tray', name='Original', number=1, parameters=None):
        return dict(id=f'00000000-0000-4000-8000-{number:012x}', name=name,
                    dimensions=dict(model=model, units='mm', parameters=copy.deepcopy(parameters or catalog[model]['defaults'])))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])

        def setup(page, rows=None, waiting=None):
            rows = [record()] if rows is None else rows
            peer = page.context.new_page()
            peer.add_init_script('localStorage.setItem(' + json.dumps(KEY) + ',' + json.dumps(json.dumps(rows)) + ');')
            peer.goto(BASE)
            peer.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            peer.locator('[data-model="parts_tray"]').click()
            expect(peer.locator('#download-cad')).to_be_enabled()
            peer.locator('.saved-dimensions > summary').click()
            page.add_init_script(FILES + EVENTS)
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
            expect(page.locator('#download-cad')).to_be_enabled()
            page.locator('.saved-dimensions > summary').click()
            if rows:
                page.locator('#version-choice').select_option(rows[0]['id'])
            return peer, jobs

        def settle(page, count):
            page.wait_for_function('n => window.versionStorageEvents >= n', arg=count)
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')

        def update(peer, rows):
            peer.evaluate('args => localStorage.setItem(...args)', [KEY, json.dumps(rows)])

        def stored(page):
            return page.evaluate('key => JSON.parse(localStorage.getItem(key) || "[]")', KEY)

        def download(page, button='download'):
            with page.expect_download() as event:
                page.locator('#' + button).click()
            return event.value.suggested_filename, Path(event.value.path()).read_bytes()

        def build(page):
            page.locator('#rebuild').click()
            expect(page.locator('#download')).to_be_enabled(timeout=90000)

        if BASELINE:
            context = browser.new_context(accept_downloads=True)
            if OFFLINE:
                attach_assets(context)
            page = context.new_page()
            peer, _ = setup(page)
            update(peer, [record(name='Renamed elsewhere')])
            settle(page, 1)
            stale_name = page.locator('#version-choice option').filter(has_text='Original').count() == 1
            peer.evaluate('key => localStorage.removeItem(key)', KEY)
            settle(page, 2)
            stale_actions = page.locator('#load-version').is_enabled() and page.locator('#export-versions').is_enabled()
            report = dict(real_cross_tab_events=page.evaluate('window.versionStorageEvents'), renamed_entry_stays_stale=stale_name,
                          removed_entries_keep_actions_enabled=stale_actions, current_length=page.locator('#param-length').input_value())
            assert stale_name and stale_actions, report
            (ROOT / 'review/cloud_versions_sync_baseline.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps(report), flush=True)
            context.close()
            browser.close()
            return

        def real_ui_saves_renames_and_removes_refresh_the_other_tab(page):
            peer, jobs = setup(page)
            peer.locator('#version-name').fill('Other tab')
            peer.locator('#save-version').click()
            settle(page, 1)
            expect(page.locator('#version-choice option')).to_have_count(3)
            expect(page.locator('#version-choice')).to_have_value(record()['id'])
            peer.locator('#version-name').fill('Renamed <shelf> 🧰')
            peer.locator('#rename-version').click()
            settle(page, 2)
            assert page.locator('#version-choice option').filter(has_text='Renamed <shelf> 🧰').count() == 1
            peer.locator('#remove-version').click()
            settle(page, 3)
            expect(page.locator('#version-choice option')).to_have_count(2)
            expect(page.locator('#versions-sync-message')).to_contain_text('another tab')
            assert not jobs

        def selected_replacement_keeps_dirty_fields_history_preview_and_cached_cad(page):
            peer, jobs = setup(page)
            page.locator('#param-length').fill('180.5')
            build(page)
            cad = download(page, 'download-cad')
            page.locator('#param-length').fill('')
            page.locator('#version-name').fill('Unsaved name')
            before = (page.url, page.locator('#form-message').inner_text(), page.locator('#model-size').inner_text())
            update(peer, [record(name='New measurements', parameters={**catalog['parts_tray']['defaults'], 'length': 190.55})])
            settle(page, 1)
            expect(page.locator('#param-length')).to_have_value('')
            expect(page.locator('#version-name')).to_have_value('Unsaved name')
            expect(page.locator('#version-choice')).to_have_value(record()['id'])
            assert before == (page.url, page.locator('#form-message').inner_text(), page.locator('#model-size').inner_text())
            assert page.locator('#download').is_disabled()
            page.locator('#param-length').fill('180.5')
            assert download(page, 'download-cad') == cad and len(jobs) == 2
            assert download(page)[1] == fixtures['parts_tray'][2]

        def removal_and_clear_recover_keyboard_focus_without_changing_dimensions(page):
            peer, jobs = setup(page)
            page.locator('#rename-version').focus()
            peer.evaluate('key => localStorage.removeItem(key)', KEY)
            settle(page, 1)
            expect(page.locator('#version-choice')).to_be_focused()
            for control in ('load-version', 'remove-version', 'rename-version', 'replace-version', 'export-versions'):
                expect(page.locator('#' + control)).to_be_disabled()
            update(peer, [record()])
            settle(page, 2)
            page.locator('#export-versions').focus()
            peer.evaluate('localStorage.clear()')
            settle(page, 3)
            expect(page.locator('#version-choice')).to_be_focused()
            expect(page.locator('#version-choice option')).to_have_count(1)
            expect(page.locator('#param-length')).to_have_value('150')
            assert download(page)[0] == 'parts_tray.stl' and not jobs

        def unchanged_or_unrelated_storage_events_do_not_dismiss_feedback_or_focus(page):
            peer, _ = setup(page)
            page.locator('#version-name').fill('')
            page.locator('#rename-version').click()
            before = page.locator('#version-message').inner_text()
            page.locator('#param-length').focus()
            peer.evaluate("localStorage.setItem('unrelated-setting', 'changed')")
            page.evaluate("""key => {
              dispatchEvent(new StorageEvent('storage', { key, storageArea: sessionStorage, newValue: 'broken' }));
              dispatchEvent(new StorageEvent('storage', { key, storageArea: localStorage, newValue: 'obsolete' }));
            }""", KEY)
            settle(page, 1)
            expect(page.locator('#versions-sync-message')).to_be_hidden()
            expect(page.locator('#param-length')).to_be_focused()
            assert page.locator('#version-message').inner_text() == before
            expect(page.locator('#version-name')).to_have_attribute('aria-invalid', 'true')

        def queued_events_read_latest_storage_without_trusting_event_values(page):
            peer, _ = setup(page)
            peer.evaluate("""args => {
              localStorage.setItem(args[0], args[1]);
              localStorage.setItem(args[0], args[2]);
            }""", [KEY, json.dumps([record(name='Older')]), json.dumps([record(name='Latest')])])
            settle(page, 2)
            assert page.locator('#version-choice option').filter(has_text='Latest').count() == 1
            assert page.locator('#version-choice option').filter(has_text='Older').count() == 0
            page.locator('#load-version').click()
            expect(page.locator('#form-message')).to_contain_text('Latest')
            expect(page.locator('#versions-sync-message')).to_be_hidden()

        def corrupt_and_denied_reads_keep_storage_and_editor_then_recover(page):
            peer, _ = setup(page)
            page.locator('#param-length').focus()
            peer.evaluate('args => localStorage.setItem(...args)', [KEY, 'broken'])
            settle(page, 1)
            expect(page.locator('#versions-sync-message')).to_have_class('error')
            expect(page.locator('#load-version')).to_be_disabled()
            assert peer.evaluate('key => localStorage.getItem(key)', KEY) == 'broken'
            expect(page.locator('#param-length')).to_be_focused()
            update(peer, [])
            settle(page, 2)
            expect(page.locator('#versions-sync-message')).to_contain_text('available again')
            page.evaluate("""key => {
              const read = Storage.prototype.getItem;
              window.restoreVersionsRead = () => { Storage.prototype.getItem = read; };
              Storage.prototype.getItem = function(name) {
                if (this === localStorage && name === key) throw new DOMException('Denied', 'SecurityError');
                return read.call(this, name);
              };
            }""", KEY)
            update(peer, [record(name='While denied')])
            settle(page, 3)
            expect(page.locator('#versions-sync-message')).to_contain_text('unavailable')
            expect(page.locator('#download')).to_be_enabled()
            page.evaluate('window.restoreVersionsRead()')
            update(peer, [record(name='Recovered')])
            settle(page, 4)
            expect(page.locator('#versions-sync-message')).not_to_have_class('error')
            assert page.locator('#version-choice option').filter(has_text='Recovered').count() == 1

        def pending_backup_import_merges_fresh_external_records(page):
            peer, _ = setup(page)
            body = dict(format='everyday-prints-versions', version=1, versions=[record('cable_comb', 'Routing', 3)])
            page.locator('#versions-file').set_input_files(dict(name='slow-backup.json', mimeType='application/json', buffer=json.dumps(body).encode()))
            page.wait_for_function('() => window.pendingDimensionReads.length === 1')
            update(peer, [record(name='Added elsewhere', number=2), record()])
            settle(page, 1)
            expect(page.locator('#version-backup-message')).to_contain_text('Reading')
            page.evaluate('window.pendingDimensionReads[0]()')
            expect(page.locator('#version-backup-message')).to_contain_text('Imported 1 version')
            assert [row['name'] for row in stored(page)] == ['Routing', 'Added elsewhere', 'Original']
            expect(page.locator('#versions-sync-message')).to_be_hidden()
            expect(page.locator('#param-length')).to_have_value('150')

        def capacity_and_dimension_file_reads_stay_independent_of_sync(page):
            peer, _ = setup(page)
            body = dict(format='everyday-prints-versions', version=1, versions=[record('cable_comb', 'Routing')])
            page.locator('#versions-file').set_input_files(dict(name='slow-full.json', mimeType='application/json', buffer=json.dumps(body).encode()))
            page.wait_for_function('() => window.pendingDimensionReads.length === 1')
            rows = [record(name=f'Size {n}', number=n + 1) for n in range(20)]
            update(peer, rows)
            settle(page, 1)
            page.evaluate('window.pendingDimensionReads[0]()')
            expect(page.locator('#version-backup-message')).to_contain_text('exceed 20')
            assert stored(page) == rows
            dimensions = dict(model='parts_tray', units='mm', parameters={'length': 180.5})
            page.locator('#dimensions-file').set_input_files(dict(name='slow-dimensions.json', mimeType='application/json', buffer=json.dumps(dimensions).encode()))
            page.wait_for_function('() => window.pendingDimensionReads.length === 2')
            update(peer, [record(name='New library')])
            settle(page, 2)
            expect(page.locator('#form-message')).to_contain_text('Loading saved dimensions')
            page.evaluate('window.pendingDimensionReads[1]()')
            expect(page.locator('#param-length')).to_have_value('180.5')
            expect(page.locator('#form-message')).to_contain_text('Saved dimensions loaded')

        def active_cad_work_keeps_progress_stop_focus_and_exact_files(page):
            waiting = []
            peer, jobs = setup(page, waiting=waiting)
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').focus()
            page.keyboard.press('Enter')
            expect(page.locator('#stop-build')).to_be_focused()
            before = page.locator('#form-message').inner_text()
            update(peer, [])
            settle(page, 1)
            expect(page.locator('#stop-build')).to_be_focused()
            assert page.locator('#form-message').inner_text() == before
            for control in ('save-version', 'load-version', 'rename-version', 'replace-version', 'export-versions', 'import-versions'):
                expect(page.locator('#' + control)).to_be_disabled()
            while not waiting:
                page.wait_for_timeout(20)
            _, metadata, mesh = fixtures['parts_tray']
            waiting[0].fulfill(body=mesh, headers=headers({**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}, 'model/stl'))
            expect(page.locator('#download')).to_be_enabled()
            expect(page.locator('#rebuild')).to_be_focused()
            assert download(page)[1] == mesh and len(jobs) == 1
            expect(page.locator('#version-choice option')).to_have_count(1)

        def late_original_preview_uses_external_rename_without_loading_new_measurements(page):
            page.add_init_script("""window.releaseVersionOriginal = null;
              const realFetch = window.fetch;
              window.fetch = async (...args) => {
                const response = await realFetch(...args);
                if (String(args[0]).endsWith('/models/cable_comb.stl')) await new Promise(resolve => window.releaseVersionOriginal = resolve);
                return response;
              };""")
            peer, jobs = setup(page, [record('cable_comb', 'Routing')])
            page.locator('#load-version').click()
            page.wait_for_function('() => window.releaseVersionOriginal !== null')
            update(peer, [record('cable_comb', 'Bench routing', parameters=fixtures['cable_comb'][1]['parameters'])])
            settle(page, 1)
            page.evaluate('window.releaseVersionOriginal()')
            expect(page.locator('#download')).to_be_enabled()
            expect(page.locator('#form-message')).to_contain_text('Version “Bench routing” loaded')
            assert [float(n) for n in page.locator('#param-cable_diameters').input_value().split(',')] == catalog['cable_comb']['defaults']['cable_diameters']
            assert not jobs

        def closed_editor_and_early_catalog_events_use_current_library(page):
            page.add_init_script(EVENTS)
            waiting = []
            page.route('**/catalog.json', lambda route: waiting.append(route))
            page.goto(BASE)
            while not waiting:
                page.wait_for_timeout(20)
            peer = page.context.new_page()
            peer.goto(BASE + '/favicon.svg')
            update(peer, [record(name='Before catalog')])
            settle(page, 1)
            waiting[0].fulfill(path=str(CLOUD / '.cloudflare/output/v0/workers/default/assets/catalog.json'), content_type='application/json')
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            page.locator('[data-model="parts_tray"]').click()
            expect(page.locator('#download')).to_be_enabled()
            page.locator('.saved-dimensions > summary').click()
            assert page.locator('#version-choice option').filter(has_text='Before catalog').count() == 1
            page.locator('#close-editor').click()
            page.locator('#search').focus()
            update(peer, [record(name='While closed')])
            settle(page, 2)
            expect(page.locator('#search')).to_be_focused()
            page.locator('[data-model="parts_tray"]').click()
            assert page.locator('#version-choice option').filter(has_text='While closed').count() == 1

        def mobile_keyboard_sync_keeps_long_names_bounded_and_downloads_exact(page):
            peer, jobs = setup(page)
            page.set_viewport_size(dict(width=390, height=844))
            page.locator('#version-name').focus()
            update(peer, [record(name='Storage shelves <wide> · ' + '🧰' * 20)])
            settle(page, 1)
            expect(page.locator('#version-name')).to_be_focused()
            expect(page.locator('#versions-sync-message')).to_be_visible()
            page.locator('.named-versions').scroll_into_view_if_needed()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('#editor').evaluate('(el) => el.scrollWidth <= el.clientWidth')
            page.screenshot(path=str(ROOT / 'review/cloud_versions_sync_mobile.png'))
            page.set_viewport_size(dict(width=1440, height=1080))
            page.locator('.named-versions').scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / 'review/cloud_versions_sync_desktop.png'))
            page.locator('#load-version').focus()
            page.keyboard.press('Enter')
            expect(page.locator('#param-length')).to_be_focused()
            assert download(page)[0] == 'parts_tray.stl' and not jobs

        tests = (real_ui_saves_renames_and_removes_refresh_the_other_tab,
                 selected_replacement_keeps_dirty_fields_history_preview_and_cached_cad,
                 removal_and_clear_recover_keyboard_focus_without_changing_dimensions,
                 unchanged_or_unrelated_storage_events_do_not_dismiss_feedback_or_focus,
                 queued_events_read_latest_storage_without_trusting_event_values,
                 corrupt_and_denied_reads_keep_storage_and_editor_then_recover,
                 pending_backup_import_merges_fresh_external_records,
                 capacity_and_dimension_file_reads_stay_independent_of_sync,
                 active_cad_work_keeps_progress_stop_focus_and_exact_files,
                 late_original_preview_uses_external_rename_without_loading_new_measurements,
                 closed_editor_and_early_catalog_events_use_current_library,
                 mobile_keyboard_sync_keeps_long_names_bounded_and_downloads_exact)
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
    report = dict(endpoint=BASE, passed=passed, failures=failures,
                  transport='real shared-context browser tabs, compiled assets and real CAD fixtures' if OFFLINE else 'local HTTP')
    (ROOT / 'review/cloud_versions_sync_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    assert not failures, report


if __name__ == '__main__':
    main()
