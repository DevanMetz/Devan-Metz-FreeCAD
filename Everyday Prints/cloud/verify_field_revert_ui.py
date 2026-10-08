"""Verify individual measurement restoration against the last verified preview."""
import copy
import json
import os
import re
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
sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))


def text(value):
    if isinstance(value, list):
        return ', '.join(text(number) for number in value)
    return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)


def main():
    fixtures = {name: fixture(name) for name in ('parts_tray', 'cable_comb')}
    catalog = {row['name']: row for row in json.loads((CLOUD / 'public/catalog.json').read_text(encoding='utf-8'))['models']}
    passed, failures = [], []

    def record(model='parts_tray', name='Original'):
        return dict(id='00000000-0000-4000-8000-000000000001', name=name,
                    dimensions=dict(model=model, units='mm', parameters=copy.deepcopy(catalog[model]['defaults'])))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])

        def setup(page, model='parts_tray', waiting=None, ready=True):
            page.add_init_script(FILES)
            page.add_init_script("window.copies = []; Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: async value => window.copies.push(value)}});")
            page.add_init_script('if (localStorage.getItem(' + json.dumps(KEY) + ') === null) localStorage.setItem(' + json.dumps(KEY) + ',' + json.dumps(json.dumps([record()])) + ');')
            jobs = []

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload)
                archive, metadata, mesh = fixtures[payload['model']]
                assert payload['parameters'] == metadata['parameters'], payload
                if waiting is not None:
                    waiting.append(route)
                else:
                    respond(route)

            page.route('**/api/generate', generate)
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            page.locator(f'[data-model="{model}"]').click()
            if ready:
                expect(page.locator('#download-cad')).to_be_enabled()
            page.locator('.saved-dimensions summary').click()
            return jobs

        def respond(route, mismatch=False):
            payload = route.request.post_data_json
            archive, metadata, mesh = fixtures[payload['model']]
            metadata = copy.deepcopy(metadata)
            if mismatch:
                metadata['bounds_mm'][0] += 10
            if payload.get('format') == 'cad':
                route.fulfill(body=archive, headers=headers(metadata))
            else:
                route.fulfill(body=mesh, headers=headers({**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}, 'model/stl'))

        def pending_route(page, waiting, index):
            for _ in range(500):
                if len(waiting) > index:
                    return waiting[index]
                page.wait_for_timeout(20)
            raise AssertionError(f'Expected held generation request {index}')

        def edit_custom(page, model='parts_tray'):
            for key, value in fixtures[model][1]['parameters'].items():
                page.locator('#param-' + key).fill(text(value))

        def build(page):
            page.locator('#rebuild').click()
            expect(page.locator('#download')).to_be_enabled()

        def values(page):
            return page.locator('#parameter-fields').evaluate("el => Object.fromEntries([...el.querySelectorAll('input')].map(input => [input.dataset.parameter, input.value]))")

        def restore(page, key, keyboard=False):
            button = page.locator('#revert-field-' + key)
            expect(button).to_be_enabled()
            if keyboard:
                button.focus()
                page.keyboard.press('Enter')
            else:
                button.click()
            expect(page.locator('#param-' + key)).to_be_focused()
            expect(button).to_be_hidden()

        def preview(page, key, expected):
            expect(page.locator('#preview-field-' + key)).to_have_text(expected)
            expect(page.locator('#revert-field-' + key)).to_have_accessible_description(expected)
            expect(page.locator('#param-' + key)).to_have_accessible_description(re.compile(re.escape(expected)))

        def download(page, control='download'):
            with page.expect_download() as event:
                page.locator('#' + control).click()
            return event.value.suggested_filename, Path(event.value.path()).read_bytes()

        def original_mesh(model):
            return (CLOUD / 'public' / catalog[model]['mesh'].lstrip('/')).read_bytes()

        def choose(page, control, body, name):
            page.locator('#' + control).set_input_files(dict(name=name, mimeType='application/json', buffer=json.dumps(body).encode('utf-8')))

        def release_file(page, number):
            page.evaluate('n => window.pendingDimensionReads[n]()', number)
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')

        if BASELINE:
            context = browser.new_context(accept_downloads=True)
            if OFFLINE:
                attach_assets(context)
            page = context.new_page()
            setup(page)
            page.locator('#param-length').fill('190.55')
            page.locator('#param-width').fill('110.5')
            before = values(page)
            actions = page.locator('[data-revert-parameter]').count()
            page.locator('#revert-parameters').click()
            after = values(page)
            report = dict(individual_actions=actions, edited_fields=before, after_full_revert=after,
                          only_all_fields_revert=actions == 0 and after['length'] == '150' and after['width'] == '100')
            assert report['only_all_fields_revert'], report
            (ROOT / 'review/cloud_field_revert_baseline.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps(report), flush=True)
            context.close()
            browser.close()
            return

        def one_field_restore_keeps_other_edits_and_exact_original_file(page):
            jobs = setup(page)
            page.locator('#param-length').fill('190.55')
            page.locator('#param-width').fill('110.5')
            before = values(page)
            preview(page, 'length', 'Preview: 150 mm')
            preview(page, 'width', 'Preview: 100 mm')
            page.evaluate("window.keptInput = document.querySelector('#param-width')")
            restore(page, 'width')
            assert values(page) == {**before, 'width': '100'}
            assert page.evaluate("window.keptInput === document.querySelector('#param-width')")
            expect(page.locator('#download')).to_be_disabled()
            expect(page.locator('#revert-parameters')).to_be_visible()
            restore(page, 'length')
            expect(page.locator('#revert-parameters')).to_be_hidden()
            assert download(page) == ('parts_tray.stl', original_mesh('parts_tray')) and not jobs

        def semantic_numbers_lists_counts_and_invalid_drafts_have_exact_preview_values(page):
            setup(page)
            page.locator('#param-length').fill('150.00')
            page.locator('#param-columns').fill('3.0')
            expect(page.locator('#revert-field-length')).to_be_hidden()
            expect(page.locator('#revert-field-columns')).to_be_hidden()
            page.locator('#param-columns').fill('3.5')
            preview(page, 'columns', 'Preview: 3')
            restore(page, 'columns')
            jobs = setup(page, model='cable_comb')
            page.locator('#param-cable_diameters').fill('[3, 4.0, 5, 6, 8]')
            expect(page.locator('#revert-field-cable_diameters')).to_be_hidden()
            page.locator('#param-cable_diameters').fill('8, 6, 5, 4, 3')
            preview(page, 'cable_diameters', 'Preview: 3, 4, 5, 6, 8 mm')
            page.locator('#param-clearance').fill('2')
            page.locator('#param-cable_diameters').fill('3,,5')
            restore(page, 'cable_diameters')
            expect(page.locator('#param-clearance')).to_have_value('2')
            expect(page.locator('#param-clearance')).to_have_attribute('aria-invalid', 'true')
            expect(page.locator('#download')).to_be_disabled()
            restore(page, 'clearance')
            expect(page.locator('#download')).to_be_enabled()
            assert not jobs

        def verified_custom_baseline_restores_precise_values_and_cached_cad(page):
            jobs = setup(page)
            edit_custom(page)
            build(page)
            mesh = download(page)
            cad = download(page, 'download-cad')
            page.locator('#param-length').fill('190.55555555555554')
            page.locator('#param-width').fill('')
            preview(page, 'length', 'Preview: 180.5 mm')
            restore(page, 'length')
            expect(page.locator('#param-length')).to_have_value('180.5')
            expect(page.locator('#param-width')).to_have_value('')
            expect(page.locator('#param-width')).to_have_attribute('aria-invalid', 'true')
            restore(page, 'width')
            assert download(page) == mesh and mesh[1] == fixtures['parts_tray'][2]
            assert download(page, 'download-cad') == cad and len(jobs) == 2
            assert '180.5x' in mesh[0] and '-custom-' in cad[0]
            page.locator('#reset-parameters').click()
            preview(page, 'length', 'Preview: 180.5 mm')
            restore(page, 'length')
            expect(page.locator('#download')).to_be_enabled()

        def all_53_model_schemas_restore_without_building(page):
            jobs = setup(page)
            for number, (name, model) in enumerate(catalog.items()):
                page.locator('#close-editor').click()
                expect(page.locator('#editor')).not_to_be_visible()
                page.wait_for_function("() => !new URL(location.href).searchParams.has('model')")
                page.locator(f'[data-model="{name}"]').click()
                expect(page.locator('#download-cad')).to_be_enabled()
                before = values(page)
                field = model['parameters'][0]
                key = field['key']
                page.locator('#param-' + key).fill('')
                expected = 'Preview: ' + text(model['defaults'][key]) + (' ' + field['unit'] if field['unit'] else '')
                preview(page, key, expected)
                restore(page, key)
                assert values(page) == before, name
                expect(page.locator('#download-cad')).to_be_enabled()
                assert page.locator('.parameter-preview:visible').count() == 0, name
                if number % 10 == 0:
                    print('SCHEMA ' + name, flush=True)
            assert not jobs

        def pending_build_guards_actions_and_publishes_the_new_baseline(page):
            waiting = []
            jobs = setup(page, waiting=waiting)
            edit_custom(page)
            page.locator('#rebuild').click()
            expect(page.locator('#revert-field-length')).to_be_disabled()
            page.locator('#revert-field-length').dispatch_event('click')
            expect(page.locator('#param-length')).to_have_value('180.5')
            page.locator('#param-length').fill('190.55')
            preview(page, 'length', 'Preview: 150 mm')
            page.wait_for_function('() => document.querySelector("#stop-build").hidden === false')
            respond(pending_route(page, waiting, 0))
            expect(page.locator('#revert-field-length')).to_be_enabled()
            preview(page, 'length', 'Preview: 180.5 mm')
            expect(page.locator('#download')).to_be_disabled()
            restore(page, 'length')
            assert download(page)[1] == fixtures['parts_tray'][2] and len(jobs) == 1

        def stop_and_failed_preview_keep_last_verified_values(page):
            waiting = []
            jobs = setup(page, waiting=waiting)
            edit_custom(page)
            page.locator('#rebuild').click()
            expect(page.locator('#stop-build')).to_be_visible()
            pending_route(page, waiting, 0)
            page.locator('#stop-build').click()
            respond(waiting[0])
            preview(page, 'length', 'Preview: 150 mm')
            expect(page.locator('#revert-field-length')).to_be_enabled()
            page.locator('#rebuild').click()
            expect(page.locator('#stop-build')).to_be_visible()
            respond(pending_route(page, waiting, 1), mismatch=True)
            expect(page.locator('#form-message')).to_have_class('form-message error')
            preview(page, 'length', 'Preview: 150 mm')
            for key in catalog['parts_tray']['defaults']:
                if page.locator('#revert-field-' + key).is_visible():
                    restore(page, key)
            assert download(page)[1] == original_mesh('parts_tray') and len(jobs) == 2

        def unavailable_preview_never_offers_unverified_reverts(page):
            pattern = '**/models/parts_tray.stl'
            page.route(pattern, lambda route: route.fulfill(status=503, body='Unavailable'))
            jobs = setup(page, ready=False)
            expect(page.locator('#mesh-status')).to_have_text('Preview unavailable')
            page.locator('#param-length').fill('190.55')
            expect(page.locator('#revert-field-length')).to_be_hidden()
            page.locator('#revert-field-length').dispatch_event('click')
            expect(page.locator('#param-length')).to_have_value('190.55')
            page.unroute(pattern)
            page.locator('#retry-original').click()
            expect(page.locator('#revert-field-length')).to_be_enabled()
            preview(page, 'length', 'Preview: 150 mm')
            restore(page, 'length')
            assert download(page)[1] == original_mesh('parts_tray') and not jobs

        def graphics_failure_keeps_comparison_and_exact_files_available(page):
            page.route('**/assets/viewer-*.js', lambda route: route.fulfill(status=503, body='Unavailable'))
            jobs = setup(page)
            edit_custom(page)
            build(page)
            expect(page.locator('#fallback-image')).to_be_visible()
            page.locator('#param-length').fill('190.55')
            preview(page, 'length', 'Preview: 180.5 mm')
            restore(page, 'length')
            assert download(page)[1] == fixtures['parts_tray'][2] and len(jobs) == 1

        def field_revert_discards_late_dimensions_but_keeps_library_imports(page):
            jobs = setup(page)
            page.locator('#param-length').fill('190.55')
            dimensions = dict(model='parts_tray', units='mm', parameters=fixtures['parts_tray'][1]['parameters'])
            choose(page, 'dimensions-file', dimensions, 'slow-dimensions.json')
            page.wait_for_function('() => window.pendingDimensionReads.length === 1')
            restore(page, 'length')
            release_file(page, 0)
            expect(page.locator('#param-length')).to_have_value('150')
            page.locator('#param-width').fill('110.5')
            backup = dict(format='everyday-prints-versions', version=1, versions=[dict(name='Routing', dimensions=record('cable_comb')['dimensions'])])
            choose(page, 'versions-file', backup, 'slow-backup.json')
            page.wait_for_function('() => window.pendingDimensionReads.length === 2')
            restore(page, 'width')
            release_file(page, 1)
            expect(page.locator('#version-backup-message')).to_contain_text('Imported 1')
            expect(page.locator('#param-width')).to_have_value('100')
            expect(page.locator('#download')).to_be_enabled()
            assert not jobs

        def save_share_versions_and_library_undo_keep_independent_measurements(page):
            jobs = setup(page)
            page.locator('#param-length').fill('180.5')
            page.locator('#param-width').fill('110.5')
            page.locator('#version-name').fill('Changed tray')
            page.locator('#save-version').click()
            restore(page, 'width')
            expect(page.locator('#undo-version')).to_be_enabled()
            saved = json.loads(download(page, 'save-dimensions')[1])
            assert saved['parameters']['length'] == 180.5 and saved['parameters']['width'] == 100
            page.locator('#share').click()
            expect(page.locator('#share-message')).to_contain_text('Link copied')
            copied = page.evaluate('window.copies[0]')
            from urllib.parse import parse_qs, urlparse
            assert json.loads(parse_qs(urlparse(copied).query)['p'][0]) == saved['parameters']
            page.locator('#undo-version').click()
            expect(page.locator('#param-length')).to_have_value('180.5')
            expect(page.locator('#param-width')).to_have_value('100')
            assert len(page.evaluate('key => JSON.parse(localStorage.getItem(key))', KEY)) == 1
            restore(page, 'length')
            assert download(page)[1] == original_mesh('parts_tray') and not jobs

        def history_refresh_and_component_navigation_keep_other_drafts(page):
            jobs = setup(page)
            page.locator('#param-length').fill('190.55')
            page.locator('#param-width').fill('110.5')
            restore(page, 'width')
            page.locator('#close-editor').click()
            expect(page.locator('#editor')).not_to_be_visible()
            page.wait_for_function("() => !new URL(location.href).searchParams.has('model')")
            page.go_forward()
            expect(page.locator('#param-length')).to_have_value('190.55')
            expect(page.locator('#param-width')).to_have_value('100')
            preview(page, 'length', 'Preview: 150 mm')
            page.reload()
            expect(page.locator('#revert-field-length')).to_be_enabled()
            expect(page.locator('#param-length')).to_have_value('190.55')
            restore(page, 'length')
            jobs = setup(page, model='soap_dish_assembly')
            page.locator('#param-length').fill('130')
            page.locator('#param-width').fill('90')
            page.locator('#part-links button').first.click()
            expect(page.locator('#mesh-status')).to_have_text('Update preview to apply edits')
            before = values(page)
            restore(page, 'length')
            assert values(page) == {**before, 'length': '120'}
            expect(page.locator('#param-width')).to_have_value('90')
            expect(page.locator('#download')).to_be_disabled()
            assert not jobs

        def scrolled_keyboard_restore_brings_the_input_back_into_view(page):
            jobs = setup(page)
            page.set_viewport_size(dict(width=390, height=844))
            page.locator('.saved-dimensions summary').click()
            page.locator('#param-length').fill('190.55')
            page.locator('#param-height').fill('26.5')
            page.locator('#revert-field-length').scroll_into_view_if_needed()
            page.evaluate("""() => {
              const layout = document.querySelector('.editor-layout');
              const button = document.querySelector('#revert-field-length');
              layout.scrollTop += button.getBoundingClientRect().top - layout.getBoundingClientRect().top - 5;
            }""")
            layout = page.locator('.editor-layout').bounding_box()
            before = page.locator('#param-length').bounding_box()
            assert before['y'] < layout['y'], (before, layout)
            restore(page, 'length', keyboard=True)
            after = page.locator('#param-length').bounding_box()
            assert after['y'] >= layout['y'] and after['y'] + after['height'] <= layout['y'] + layout['height'], (after, layout)
            expect(page.locator('#param-height')).to_have_value('26.5')
            expect(page.locator('#download')).to_be_disabled()
            restore(page, 'height', keyboard=True)
            assert download(page)[1] == original_mesh('parts_tray') and not jobs

        def mobile_keyboard_actions_keep_focus_and_reachable_layout(page):
            jobs = setup(page, model='cable_comb')
            page.locator('#param-cable_diameters').fill('9, 2, 3.55')
            page.locator('#param-depth').fill('40')
            page.locator('#parameter-fields').scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / 'review/cloud_field_revert_desktop.png'))
            page.set_viewport_size(dict(width=390, height=844))
            page.locator('#parameter-fields').scroll_into_view_if_needed()
            for key in ('cable_diameters', 'depth'):
                box = page.locator('#revert-field-' + key).bounding_box()
                assert box and box['width'] >= 44 and box['height'] >= 44, (key, box)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('#editor').evaluate('el => el.scrollWidth <= el.clientWidth')
            page.screenshot(path=str(ROOT / 'review/cloud_field_revert_mobile.png'))
            restore(page, 'cable_diameters', keyboard=True)
            expect(page.locator('#param-depth')).to_have_value('40')
            expect(page.locator('#download')).to_be_disabled()
            restore(page, 'depth', keyboard=True)
            assert download(page)[1] == original_mesh('cable_comb') and not jobs

        tests = (one_field_restore_keeps_other_edits_and_exact_original_file,
                 semantic_numbers_lists_counts_and_invalid_drafts_have_exact_preview_values,
                 verified_custom_baseline_restores_precise_values_and_cached_cad,
                 all_53_model_schemas_restore_without_building,
                 pending_build_guards_actions_and_publishes_the_new_baseline,
                 stop_and_failed_preview_keep_last_verified_values,
                 unavailable_preview_never_offers_unverified_reverts,
                 graphics_failure_keeps_comparison_and_exact_files_available,
                 field_revert_discards_late_dimensions_but_keeps_library_imports,
                 save_share_versions_and_library_undo_keep_independent_measurements,
                 history_refresh_and_component_navigation_keep_other_drafts,
                 scrolled_keyboard_restore_brings_the_input_back_into_view,
                 mobile_keyboard_actions_keep_focus_and_reachable_layout)
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
    report = dict(endpoint=BASE, passed=passed, failures=failures, model_schemas=53,
                  transport='compiled assets and real CAD fixtures' if OFFLINE else 'local HTTP')
    (ROOT / 'review/cloud_field_revert_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    assert not failures, report


if __name__ == '__main__':
    main()
