"""Verify tab draft recovery without trusting cached geometry or stored input values."""
import json
import os
from pathlib import Path
import sys
import traceback
from urllib.parse import urlencode

from playwright.sync_api import expect, sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from browser_transfers import DEFERRED_BODY
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = '--offline' in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5178')
KEY = 'everyday-prints-draft'
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))


def main():
    original, custom = fixture('parts_tray_original'), fixture('parts_tray')
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1080}, accept_downloads=True)
        context.set_default_timeout(20000)
        if OFFLINE:
            attach_assets(context)

        def settled(page):
            page.wait_for_function("() => document.querySelector('#editor').open && document.querySelector('#preview-loading').hidden")

        def setup(page, model='parts_tray', library=False):
            page.add_init_script(DEFERRED_BODY)
            jobs = []

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload)
                assert payload['model'] == 'parts_tray', payload
                archive, metadata, mesh = custom if payload['parameters']['length'] == 180.5 else original
                assert payload['parameters'] == metadata['parameters'], payload
                if payload.get('format') == 'cad':
                    route.fulfill(body=archive, headers=headers(metadata))
                else:
                    value = {**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}
                    route.fulfill(body=mesh, headers=headers(value, 'model/stl'))

            page.route('**/api/generate', generate)
            page.goto(BASE if library else BASE + '?model=' + model)
            if library:
                page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            else:
                settled(page)
            return jobs

        def refresh(page):
            identity = page.evaluate('history.state.everydayPrints.id')
            page.reload()
            settled(page)
            assert page.evaluate('history.state.everydayPrints.id') == identity

        def download(page, button='download'):
            with page.expect_download() as event:
                page.locator('#' + button).click()
            return Path(event.value.path()).read_bytes()

        def build(page):
            page.locator('#rebuild').click()
            expect(page.locator('#download')).to_be_enabled()

        def load(page, record):
            if not page.locator('.saved-dimensions').evaluate('element => element.open'):
                page.locator('.saved-dimensions > summary').click()
            with page.expect_file_chooser() as event:
                page.locator('#load-dimensions').click()
            event.value.set_files({'name': 'parameters.json', 'mimeType': 'application/json',
                                  'buffer': json.dumps(record).encode('utf-8')})

        def refresh_restores_unbuilt_decimal_draft_on_mobile(page):
            page.set_viewport_size({'width': 390, 'height': 844})
            jobs = setup(page)
            page.locator('#param-length').fill('180.55')
            refresh(page)
            assert page.locator('#param-length').input_value() == '180.55'
            assert page.locator('#download').is_disabled() and page.locator('#download-cad').is_disabled()
            expect(page.locator('#form-message')).to_contain_text('measurements were restored')
            expect(page.locator('#draft-note')).to_contain_text('Save dimensions to keep a file')
            page.locator('#param-length').focus()
            assert page.locator('#param-length').evaluate('element => element === document.activeElement')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.locator('#draft-note').scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / 'review/cloud_draft_recovery_mobile.png'))
            assert not jobs

        def refresh_keeps_blank_number_and_validation_gates(page):
            jobs = setup(page)
            page.locator('#param-length').fill('')
            refresh(page)
            assert page.locator('#param-length').input_value() == ''
            expect(page.locator('#param-length')).to_have_attribute('aria-invalid', 'true')
            expect(page.locator('#error-length')).to_contain_text('enter a number')
            assert page.locator('#download').is_disabled() and page.locator('#download-cad').is_disabled()
            page.locator('.saved-dimensions > summary').click()
            page.locator('#save-dimensions').click()
            expect(page.locator('#param-length')).to_be_focused()
            assert not jobs

        def refresh_preserves_numeric_list_text_and_order(page):
            jobs = setup(page, 'cable_comb')
            field = page.locator('#param-cable_diameters')
            field.fill('[9, 2.5, 3.7]')
            refresh(page)
            assert field.input_value() == '[9, 2.5, 3.7]'
            parameters = page.evaluate("JSON.parse(new URL(location.href).searchParams.get('p'))")
            assert parameters['cable_diameters'] == [9, 2.5, 3.7]
            assert page.locator('#download').is_disabled()
            field.fill('9, 2.5, broken')
            refresh(page)
            assert field.input_value() == '9, 2.5, broken'
            expect(field).to_have_attribute('aria-invalid', 'true')
            assert page.locator('#download').is_disabled() and not jobs

        def refresh_keeps_edits_made_during_pending_build(page):
            jobs = setup(page)
            page.evaluate("""() => {
                const fetchBeforePause = window.fetch;
                window.fetch = async (...args) => {
                    const response = await fetchBeforePause(...args);
                    if (String(args[0]).includes('/api/generate')) {
                        const bytes = await response.arrayBuffer();
                        window.deferFileBody(response, bytes, () => new Promise(() => {}));
                        window.draftBodyPending = true;
                    }
                    return response;
                };
            }""")
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            page.wait_for_function('() => window.draftBodyPending === true')
            page.locator('#param-length').fill('201.35')
            refresh(page)
            assert page.locator('#param-length').input_value() == '201.35'
            assert page.locator('#rebuild').is_enabled() and page.locator('#stop-build').is_hidden()
            assert page.locator('#download').is_disabled() and page.locator('#download-cad').is_disabled()
            assert len(jobs) == 1

        def recovered_draft_builds_exact_stl_and_cad(page):
            jobs = setup(page)
            page.locator('#param-length').fill('180.5')
            refresh(page)
            assert not jobs and page.locator('#download').is_disabled()
            build(page)
            assert download(page) == custom[2]
            assert download(page, 'download-cad') == custom[0]
            assert len(jobs) == 2
            assert all(job['parameters'] == custom[1]['parameters'] for job in jobs)
            page.locator('#param-length').fill('201.35')
            refresh(page)
            assert page.locator('#param-length').input_value() == '201.35'
            expect(page.locator('#form-message')).to_contain_text('measurements were restored')
            assert page.locator('#download').is_disabled() and len(jobs) == 2

        def reset_and_revert_replace_the_saved_draft(page):
            setup(page)
            page.locator('#param-length').fill('180.5')
            build(page)
            page.locator('#param-length').fill('')
            page.locator('#revert-parameters').click()
            refresh(page)
            assert page.locator('#param-length').input_value() == '180.5'
            assert page.locator('#download').is_disabled()
            page.locator('#reset-parameters').click()
            refresh(page)
            assert page.locator('#param-length').input_value() == '150'
            assert download(page) == (CLOUD / 'public/models/parts_tray.stl').read_bytes()

        def imported_dimensions_survive_refresh_and_model_switch(page):
            jobs = setup(page)
            load(page, {'model': 'parts_tray', 'parameters': {'length': 180.5}, 'units': 'mm'})
            expect(page.locator('#param-length')).to_have_value('180.5')
            refresh(page)
            assert page.locator('#param-length').input_value() == '180.5'
            assert page.locator('#download').is_disabled()
            load(page, {'model': 'cable_comb', 'parameters': {'cable_diameters': [9, 2.5, 3.7]}, 'units': 'mm'})
            expect(page.locator('#param-cable_diameters')).to_have_value('9, 2.5, 3.7')
            settled(page)
            refresh(page)
            assert page.locator('#param-cable_diameters').input_value() == '9, 2.5, 3.7'
            assert not jobs

        def history_traversal_saves_the_current_view_before_refresh(page):
            setup(page, library=True)
            page.locator('[data-model="soap_dish_assembly"]').click()
            settled(page)
            page.locator('#param-length').fill('')
            page.locator('[data-part="soap_dish_tray"]').click()
            settled(page)
            page.locator('#param-length').fill('201.35')
            page.go_back()
            settled(page)
            assert page.locator('#param-length').input_value() == ''
            refresh(page)
            assert page.locator('#param-length').input_value() == ''
            assert page.locator('#download-cad').is_disabled()

        def fresh_views_and_shared_links_ignore_another_draft(page):
            setup(page)
            page.locator('#param-length').fill('201.35')
            shared = {'model': 'parts_tray', 'p': json.dumps(custom[1]['parameters'])}
            page.goto(BASE + '?' + urlencode(shared))
            settled(page)
            assert page.locator('#param-length').input_value() == '180.5'
            expect(page.locator('#form-message')).to_contain_text('Shared dimensions loaded')
            page.locator('#close-editor').click()
            expect(page.locator('#editor')).to_be_hidden()
            page.locator('[data-model="parts_tray"]').click()
            settled(page)
            assert page.locator('#param-length').input_value() == '150'
            other = context.new_page()
            try:
                setup(other)
                assert other.locator('#param-length').input_value() == '150'
            finally:
                other.close()

        def corrupt_or_incompatible_drafts_keep_the_route_working(page):
            setup(page)
            record = page.evaluate('key => JSON.parse(sessionStorage.getItem(key))', KEY)
            candidates = ['not-json', 'null', json.dumps({**record, 'id': 'another-view'}),
                          json.dumps({**record, 'model': 'cable_comb'}),
                          json.dumps({**record, 'values': []}),
                          json.dumps({**record, 'values': {'length': '180.5'}}),
                          json.dumps({**record, 'values': {**record['values'], 'length': 180.5}}),
                          json.dumps({**record, 'values': {**record['values'], 'unknown': '1'}}),
                          json.dumps({**record, 'values': {**record['values'], 'length': '🌿' * 5000}})]
            for raw in candidates:
                page.evaluate('value => sessionStorage.setItem(value.key, value.raw)', {'key': KEY, 'raw': raw})
                refresh(page)
                assert page.locator('#param-length').input_value() == '150'
                assert page.locator('#download').is_enabled()

        def unavailable_storage_keeps_editing_and_files_working(page):
            page.add_init_script("""Object.defineProperty(window, 'sessionStorage', {
                configurable: true,
                get() { throw new DOMException('Controlled storage denial', 'SecurityError'); }
            });""")
            jobs = setup(page)
            expect(page.locator('#draft-note')).to_contain_text('Draft recovery is unavailable')
            page.locator('#param-length').fill('180.5')
            build(page)
            assert download(page) == custom[2]
            assert download(page, 'download-cad') == custom[0]
            page.locator('.saved-dimensions > summary').click()
            record = json.loads(download(page, 'save-dimensions'))
            assert record['parameters'] == custom[1]['parameters'] and len(jobs) == 2

        def oversized_or_failed_writes_clear_older_snapshots(page):
            setup(page, 'cable_comb')
            field = page.locator('#param-cable_diameters')
            field.fill('9, 2.5, 3.7')
            assert page.evaluate('key => sessionStorage.getItem(key) !== null', KEY)
            field.fill('🌿' * 5000)
            assert page.evaluate('key => sessionStorage.getItem(key) === null', KEY)
            expect(page.locator('#draft-note')).to_contain_text('Draft recovery is unavailable')
            refresh(page)
            assert field.input_value() == '3, 4, 5, 6, 8'
            field.fill('9, 2.5, 3.7')
            page.evaluate("() => { Storage.prototype.setItem = () => { throw new DOMException('Controlled quota failure', 'QuotaExceededError'); }; }")
            field.fill('9, 3.5, 4.7')
            assert page.evaluate('key => sessionStorage.getItem(key) === null', KEY)
            expect(page.locator('#draft-note')).to_contain_text('Save valid dimensions')
            refresh(page)
            assert field.input_value() == '3, 4, 5, 6, 8'
            assert page.locator('#download').is_enabled()

        for check in (
            refresh_restores_unbuilt_decimal_draft_on_mobile,
            refresh_keeps_blank_number_and_validation_gates,
            refresh_preserves_numeric_list_text_and_order,
            refresh_keeps_edits_made_during_pending_build,
            recovered_draft_builds_exact_stl_and_cad,
            reset_and_revert_replace_the_saved_draft,
            imported_dimensions_survive_refresh_and_model_switch,
            history_traversal_saves_the_current_view_before_refresh,
            fresh_views_and_shared_links_ignore_another_draft,
            corrupt_or_incompatible_drafts_keep_the_route_working,
            unavailable_storage_keeps_editing_and_files_working,
            oversized_or_failed_writes_clear_older_snapshots,
        ):
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
              'transport': 'compiled assets, actual tab storage and real CAD fixtures'}
    (ROOT / 'review/cloud_draft_recovery_validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    sys.exit(bool(failures))


if __name__ == '__main__':
    main()
