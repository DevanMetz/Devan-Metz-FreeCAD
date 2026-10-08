"""Check mesh records and dimensions before STL or CAD files become downloads."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import traceback
from urllib.parse import quote

from playwright.sync_api import expect, sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = '--offline' in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5178')
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))


def main():
    archive, metadata, mesh = fixture('parts_tray')
    original_archive, original_meta, original_mesh = fixture('parts_tray_original')
    preview = {**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}
    catalog_data = json.loads((CLOUD / 'public/catalog.json').read_text(encoding='utf-8'))
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1080}, accept_downloads=True)
        context.set_default_timeout(20000)
        if OFFLINE:
            attach_assets(context)

        def setup(page, reply=None):
            jobs = []

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload)
                if reply:
                    reply(route, payload)
                elif payload.get('format') == 'cad':
                    route.fulfill(body=archive, headers=headers(metadata))
                else:
                    route.fulfill(body=mesh, headers=headers(preview, 'model/stl'))

            page.route('**/api/generate', generate)
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            page.locator('[data-model="parts_tray"]').click()
            page.wait_for_function("() => !document.querySelector('#download').disabled")
            return jobs

        def build(page):
            page.locator('[data-parameter="length"]').fill('180.5')
            page.locator('#rebuild').click()
            expect(page.locator('#rebuild')).to_be_enabled()

        def download(page, button):
            with page.expect_download() as event:
                page.locator('#' + button).click()
            value = event.value
            return value.suggested_filename, Path(value.path()).read_bytes()

        def rejected(page, text):
            expect(page.locator('#form-message')).to_contain_text(text)
            assert page.locator('#download').is_disabled()
            assert page.locator('#download-cad').is_disabled()
            assert page.locator('#model-size').inner_text() == '150 × 100 × 24'
            assert page.locator('[data-parameter="length"]').input_value() == '180.5'

        def incorrect_bounds_reject_then_retry_exact_files(page):
            valid = False

            def reply(route, payload):
                if payload.get('format') == 'cad':
                    route.fulfill(body=archive, headers=headers(metadata))
                    return
                details = preview if valid else {**preview, 'bounds_mm': [190.5, 100, 24]}
                route.fulfill(body=mesh, headers=headers(details, 'model/stl'))

            jobs = setup(page, reply)
            build(page)
            rejected(page, 'mesh dimensions do not match')
            valid = True
            page.locator('#rebuild').click()
            expect(page.locator('#download')).to_be_enabled()
            filename, body = download(page, 'download')
            assert '-180.5x100x24mm-' in filename and body == mesh
            filename, body = download(page, 'download-cad')
            assert '-180.5x100x24mm-' in filename and body == archive
            assert len(jobs) == 3

        def malformed_facets_preserve_the_previous_preview(page):
            invalid = {'short header': b'not an STL', 'truncated facet': mesh[:-1]}
            for label, offset, value, kind in (
                ('wrong facet count', 80, 4294967295, '<I'),
                ('zero facets', 80, 0, '<I'),
                ('nonfinite vertex', 96, float('nan'), '<f'),
                ('nonfinite normal', 84, float('inf'), '<f'),
            ):
                data = bytearray(mesh)
                struct.pack_into(kind, data, offset, value)
                invalid[label] = bytes(data)
            selected = next(iter(invalid))

            def reply(route, payload):
                body = invalid[selected]
                digest = hashlib.sha256(body).hexdigest()
                details = {**preview, 'mesh_sha256': digest, 'file_sha256': digest}
                route.fulfill(body=body, headers=headers(details, 'model/stl'))

            jobs = setup(page, reply)
            original = download(page, 'download')[1]
            for selected in invalid:
                build(page)
                rejected(page, 'mesh file could not be verified')
                page.locator('#revert-parameters').click()
                expect(page.locator('#download')).to_be_enabled()
                assert download(page, 'download')[1] == original, selected
            assert len(jobs) == len(invalid)

        def no_webgl_rejects_bad_mesh_without_discarding_cached_cad(page):
            page.add_init_script("""const getContext = HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                return type.startsWith('webgl') ? null : getContext.call(this, type, ...args);
              };""")
            valid = True
            data = bytearray(mesh)
            struct.pack_into('<f', data, 96, float('nan'))
            bad = bytes(data)

            def reply(route, payload):
                if payload.get('format') == 'cad':
                    route.fulfill(body=archive, headers=headers(metadata))
                else:
                    body = mesh if valid else bad
                    digest = hashlib.sha256(body).hexdigest()
                    details = {**preview, 'parameters': {**preview['parameters'], 'length': payload['parameters']['length']},
                               'mesh_sha256': digest, 'file_sha256': digest}
                    route.fulfill(body=body, headers=headers(details, 'model/stl'))

            jobs = setup(page, reply)
            build(page)
            expect(page.locator('#download')).to_be_enabled()
            assert download(page, 'download-cad')[1] == archive
            valid = False
            page.locator('[data-parameter="length"]').fill('190.5')
            page.locator('#rebuild').click()
            expect(page.locator('#form-message')).to_contain_text('mesh file could not be verified')
            assert page.locator('#model-size').inner_text() == '180.5 × 100 × 24'
            assert page.locator('#download').is_disabled()
            expect(page.locator('#fallback-image')).to_be_visible()
            page.locator('#revert-parameters').click()
            assert download(page, 'download')[1] == mesh
            assert download(page, 'download-cad')[1] == archive
            assert len(jobs) == 3, jobs

        def original_bounds_mismatch_keeps_build_recovery(page):
            data = json.loads(json.dumps(catalog_data))
            next(item for item in data['models'] if item['name'] == 'parts_tray')['bounds_mm'] = [160, 100, 24]
            page.route('**/catalog.json', lambda route: route.fulfill(json=data))
            jobs = []

            def generate(route):
                jobs.append(route.request.post_data_json)
                details = {**original_meta, 'format': 'stl', 'file_sha256': original_meta['mesh_sha256']}
                route.fulfill(body=original_mesh, headers=headers(details, 'model/stl'))

            page.route('**/api/generate', generate)
            page.goto(BASE)
            page.locator('[data-model="parts_tray"]').click()
            expect(page.locator('#form-message')).to_contain_text('mesh dimensions do not match')
            assert page.locator('#download').is_disabled()
            expect(page.locator('#retry-original')).to_be_visible()
            page.locator('#retry-original').click()
            expect(page.locator('#retry-original')).to_be_enabled()
            expect(page.locator('#form-message')).to_contain_text('mesh dimensions do not match')
            assert not jobs
            page.locator('#rebuild').click()
            expect(page.locator('#download')).to_be_enabled()
            assert download(page, 'download')[1] == original_mesh
            assert page.locator('#model-size').inner_text() == '150 × 100 × 24'
            assert len(jobs) == 1

        def cad_bounds_reject_before_read_and_allow_retry(page):
            page.add_init_script("""window.badCadBounds = true;
              window.badCadBody = { reads: 0, cancelled: 0 };
              const originalFetch = window.fetch;
              window.fetch = async (...args) => {
                const response = await originalFetch(...args);
                if (args[0] !== '/api/generate' || !window.badCadBounds || JSON.parse(args[1].body).format !== 'cad') return response;
                const metadata = JSON.parse(decodeURIComponent(response.headers.get('X-Model-Metadata')));
                metadata.bounds_mm = [190.5, 100, 24];
                const headers = new Headers(response.headers);
                headers.set('X-Model-Metadata', encodeURIComponent(JSON.stringify(metadata)));
                const body = new ReadableStream({}, { highWaterMark: 0 });
                const getReader = body.getReader.bind(body);
                body.getReader = () => { window.badCadBody.reads++; return getReader(); };
                body.cancel = () => { window.badCadBody.cancelled++; return new Promise(() => {}); };
                return new Response(body, { headers });
              };""")
            jobs = setup(page)
            build(page)
            expect(page.locator('#download-cad')).to_be_enabled()
            page.locator('#download-cad').click()
            expect(page.locator('#download-cad')).to_be_enabled()
            expect(page.locator('#form-message')).to_contain_text('mesh dimensions do not match')
            assert page.evaluate('window.badCadBody') == {'reads': 0, 'cancelled': 1}
            assert download(page, 'download')[1] == mesh
            page.evaluate('window.badCadBounds = false')
            assert download(page, 'download-cad')[1] == archive
            assert download(page, 'download-cad')[1] == archive
            assert len(jobs) == 3

        def mobile_bounds_failure_preserves_revert_and_keyboard_download(page):
            page.set_viewport_size({'width': 390, 'height': 844})
            jobs = setup(page, lambda route, payload: route.fulfill(body=mesh, headers=headers({**preview, 'bounds_mm': [190.5, 100, 24]}, 'model/stl')))
            build(page)
            rejected(page, 'mesh dimensions do not match')
            page.locator('#form-message').scroll_into_view_if_needed()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(ROOT / 'review/cloud_mesh_dimensions_mobile.png'), full_page=False)
            page.locator('#revert-parameters').focus()
            page.keyboard.press('Enter')
            expect(page.locator('#download')).to_be_enabled()
            page.locator('#download').focus()
            with page.expect_download() as event:
                page.keyboard.press('Enter')
            assert event.value.suggested_filename == 'parts_tray.stl'
            assert len(jobs) == 1

        for test in (incorrect_bounds_reject_then_retry_exact_files,
                     malformed_facets_preserve_the_previous_preview,
                     no_webgl_rejects_bad_mesh_without_discarding_cached_cad,
                     original_bounds_mismatch_keeps_build_recovery,
                     cad_bounds_reject_before_read_and_allow_retry,
                     mobile_bounds_failure_preserves_revert_and_keyboard_download):
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
                  fixture_mesh_sha256=metadata['mesh_sha256'], malformed_mesh_variants=6,
                  transport='compiled assets and real CAD fixtures' if OFFLINE else 'local HTTP and real CAD fixtures')
    (ROOT / 'review/cloud_mesh_dimensions_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    assert not failures, report


if __name__ == '__main__':
    main()
