"""Verify fresh builds after CAD rejects a retained preview's mesh identity."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import traceback
from zipfile import ZIP_DEFLATED, ZipFile

from playwright.sync_api import sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = '--offline' in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5178')
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))


def reencoded_fixture(source):
    """Change a native STL's optional header; retain every facet and CAD member."""
    body, metadata, mesh = source
    label = b'Everyday Prints alternative native STL encoding'
    updated_mesh = label.ljust(80, b'\0') + mesh[80:]
    assert updated_mesh != mesh and updated_mesh[80:] == mesh[80:]
    digest = hashlib.sha256(updated_mesh).hexdigest()
    output = io.BytesIO()
    with ZipFile(io.BytesIO(body)) as original, ZipFile(output, 'w', ZIP_DEFLATED) as changed:
        for member in original.infolist():
            value = original.read(member)
            if member.filename == metadata['model'] + '.stl':
                value = updated_mesh
            elif member.filename == 'parameters.json':
                record = json.loads(value)
                record['mesh_sha256'] = digest
                value = json.dumps(record, indent=2).encode('utf-8')
            changed.writestr(member, value)
    updated_body = output.getvalue()
    with ZipFile(io.BytesIO(updated_body)) as changed:
        assert changed.testzip() is None
        assert changed.read(metadata['model'] + '.stl') == updated_mesh
        assert json.loads(changed.read('parameters.json'))['mesh_sha256'] == digest
    return updated_body, {**metadata, 'mesh_sha256': digest,
        'file_sha256': hashlib.sha256(updated_body).hexdigest()}, updated_mesh


def main():
    original, old = fixture('parts_tray_original'), fixture('parts_tray')
    new = reencoded_fixture(old)
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])

        def setup(page):
            jobs = []
            service = {'preview': old, 'mode': 'valid'}

            def generate(route):
                payload = route.request.post_data_json
                kind = payload.get('format', 'stl')
                jobs.append(kind)
                assert payload['model'] == 'parts_tray'
                if payload['parameters'] == original[1]['parameters']:
                    selected = original
                else:
                    assert payload['parameters'] == old[1]['parameters'], payload
                    selected = new if kind == 'cad' else service['preview']
                if kind != 'cad' and service['mode'] == 'failed':
                    route.fulfill(status=503, content_type='application/json', body='{"error":"Native refresh is unavailable. Try again."}')
                    return
                body, metadata = (selected[0], selected[1]) if kind == 'cad' else (selected[2],
                    {**selected[1], 'format': 'stl', 'file_sha256': selected[1]['mesh_sha256']})
                if kind != 'cad' and service['mode'] == 'corrupt':
                    body = body[:-1]
                    digest = hashlib.sha256(body).hexdigest()
                    metadata = {**metadata, 'mesh_sha256': digest, 'file_sha256': digest}
                route.fulfill(body=body, headers=headers(metadata, 'application/zip' if kind == 'cad' else 'model/stl'))

            page.route('**/api/generate', generate)
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            return jobs, service

        def ready(page):
            page.wait_for_function("() => document.querySelector('#editor').open && !document.querySelector('#download-cad').disabled")

        def open_tray(page, custom=False, native=False):
            page.locator('[data-model="parts_tray"]').click()
            ready(page)
            if custom:
                page.locator('#param-length').fill('180.5')
            if custom or native:
                page.locator('#rebuild').click()
                ready(page)

        def close(page):
            page.locator('#close-editor').click()
            page.wait_for_function("() => !document.querySelector('#editor').open")

        def download(page, body, button='download', keyboard=False):
            with page.expect_download() as event:
                if keyboard:
                    page.locator('#' + button).focus()
                    page.keyboard.press('Space')
                else:
                    page.locator('#' + button).click()
            assert Path(event.value.path()).read_bytes() == body
            return event.value.suggested_filename

        def error(page, text):
            page.wait_for_function("() => !document.querySelector('#rebuild').disabled && document.querySelector('#form-message').classList.contains('error')")
            assert text in page.locator('#form-message').inner_text()

        def mismatch(page):
            downloads = []
            listener = lambda value: downloads.append(value)
            page.on('download', listener)
            page.locator('#download-cad').click()
            error(page, 'do not match the preview')
            assert not downloads, 'A ZIP for a different preview became a download'
            page.remove_listener('download', listener)

        def cached_mismatch_forces_fresh_preview_and_exact_mobile_cad(page):
            jobs, service = setup(page)
            open_tray(page, custom=True)
            old_name = download(page, old[2])
            close(page)
            open_tray(page, custom=True)
            assert jobs == ['stl']
            mismatch(page)
            assert download(page, old[2]) == old_name
            service['preview'] = new
            page.locator('#rebuild').focus()
            page.keyboard.press('Space')
            ready(page)
            new_name = download(page, new[2])
            assert new_name == f'parts_tray-custom-180.5x100x24mm-{new[1]["mesh_sha256"][:12]}.stl'
            assert new_name != old_name
            cad_name = download(page, new[0], 'download-cad')
            assert cad_name == f'parts_tray-custom-180.5x100x24mm-{new[1]["file_sha256"][:12]}-cad.zip'
            assert jobs == ['stl', 'cad', 'stl', 'cad']
            page.screenshot(path=str(ROOT / 'review/cloud_cad_cache_recovery_desktop.png'))
            page.set_viewport_size({'width': 390, 'height': 844})
            assert download(page, new[2], keyboard=True) == new_name
            assert download(page, new[0], 'download-cad', keyboard=True) == cad_name
            assert page.locator('#download-cad').evaluate('element => element === document.activeElement')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert jobs == ['stl', 'cad', 'stl', 'cad']
            page.screenshot(path=str(ROOT / 'review/cloud_cad_cache_recovery_mobile.png'))

        def aliases_files_and_revert_cannot_restore_the_rejected_cached_mesh(page):
            jobs, service = setup(page)
            open_tray(page, custom=True)
            cable = next(item for item in json.loads((CLOUD / 'public/catalog.json').read_text(encoding='utf-8'))['models']
                         if item['name'] == 'cable_comb')

            def load_file(record):
                page.locator('#dimensions-file').set_input_files({'name': 'parameters.json',
                    'mimeType': 'application/json', 'buffer': json.dumps(record).encode('utf-8')})
                page.wait_for_function("name => new URL(location.href).searchParams.get('model') === name && document.querySelector('#editor').open && document.querySelector('#preview-loading').hidden", arg=record['model'])

            for _ in range(3):
                load_file({'model': cable['name'], 'parameters': cable['defaults'], 'units': 'mm'})
                load_file(old[1])
                page.locator('#rebuild').click()
                ready(page)
                assert download(page, old[2]).endswith('.stl')
            assert jobs == ['stl']
            mismatch(page)
            page.locator('#param-height').fill('')
            assert page.locator('#download').is_disabled() and page.locator('#download-cad').is_disabled()
            page.locator('#revert-parameters').click()
            assert download(page, old[2]).endswith('.stl')
            close(page)
            service['preview'] = new
            open_tray(page, custom=True)
            assert download(page, new[2]).endswith('.stl')
            assert download(page, new[0], 'download-cad').endswith('-cad.zip')
            assert jobs == ['stl', 'cad', 'stl', 'cad']

        def stopped_failed_and_expired_refreshes_keep_old_stl_and_allow_retry(page):
            jobs, service = setup(page)
            open_tray(page, custom=True)
            close(page)
            open_tray(page, custom=True)
            mismatch(page)
            service['preview'] = new
            page.clock.install()
            page.evaluate("""() => {
              const fetch = window.fetch.bind(window);
              window.holdRecovery = true;
              window.recoveryResponses = [];
              window.fetch = async (...args) => {
                const response = await fetch(...args);
                const payload = args[1]?.body && JSON.parse(args[1].body);
                if (!window.holdRecovery || !String(args[0]).includes('/api/generate') || payload?.format === 'cad') return response;
                return new Promise(resolve => { window.recoveryResponses.push(() => resolve(response)); });
              };
            }""")

            def release(index):
                page.evaluate('index => { window.recoveryResponses[index](); }', index)
                page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')

            page.locator('#rebuild').click()
            page.wait_for_function('() => window.recoveryResponses.length === 1')
            page.locator('#stop-build').click()
            release(0)
            assert 'Stopped waiting' in page.locator('#form-message').inner_text()
            assert download(page, old[2]).endswith('.stl')
            page.locator('#rebuild').click()
            page.wait_for_function('() => window.recoveryResponses.length === 2')
            page.clock.fast_forward(15 * 60 * 1000)
            release(1)
            assert 'exceeded 15 minutes' in page.locator('#form-message').inner_text()
            assert download(page, old[2]).endswith('.stl')
            page.evaluate('window.holdRecovery = false')
            service['mode'] = 'failed'
            page.locator('#rebuild').click()
            error(page, 'Native refresh is unavailable')
            assert download(page, old[2]).endswith('.stl')
            service['mode'] = 'corrupt'
            page.locator('#rebuild').click()
            error(page, 'mesh file could not be verified')
            assert download(page, old[2]).endswith('.stl')
            service['mode'] = 'valid'
            page.locator('#rebuild').click()
            ready(page)
            assert download(page, new[2]).endswith('.stl')
            assert download(page, new[0], 'download-cad').endswith('-cad.zip')
            assert jobs == ['stl', 'cad', 'stl', 'stl', 'stl', 'stl', 'stl', 'cad']

        def superseded_cad_headers_cannot_invalidate_other_verified_previews(page):
            jobs, _ = setup(page)
            open_tray(page, native=True)
            assert download(page, original[2]) == 'parts_tray.stl'
            close(page)
            open_tray(page, custom=True)
            close(page)
            open_tray(page, custom=True)
            page.evaluate("""() => {
              const fetch = window.fetch.bind(window);
              window.fetch = async (...args) => {
                const response = await fetch(...args);
                const payload = args[1]?.body && JSON.parse(args[1].body);
                if (!String(args[0]).includes('/api/generate') || payload?.format !== 'cad') return response;
                return new Promise(resolve => { window.releaseOldCad = () => resolve(response); });
              };
            }""")
            page.locator('#download-cad').click()
            page.wait_for_function("() => typeof window.releaseOldCad === 'function'")
            close(page)
            open_tray(page, native=True)
            page.evaluate('() => { window.releaseOldCad(); }')
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            assert download(page, original[2]) == 'parts_tray.stl'
            close(page)
            open_tray(page, native=True)
            assert download(page, original[2]) == 'parts_tray.stl'
            close(page)
            open_tray(page, custom=True)
            assert download(page, old[2]).endswith('.stl')
            assert jobs == ['stl', 'stl', 'cad']

        def other_complete_downloads_stay_reusable_while_rejected_version_refreshes(page):
            jobs, service = setup(page)
            open_tray(page)
            assert download(page, original[0], 'download-cad') == 'parts_tray-cad.zip'
            close(page)
            open_tray(page, custom=True)
            mismatch(page)
            close(page)
            open_tray(page)
            assert download(page, original[0], 'download-cad') == 'parts_tray-cad.zip'
            assert download(page, original[2]) == 'parts_tray.stl'
            assert jobs == ['stl', 'cad', 'stl', 'cad']
            close(page)
            service['preview'] = new
            open_tray(page, custom=True)
            assert download(page, new[2]).endswith('.stl')
            assert download(page, new[0], 'download-cad').endswith('-cad.zip')
            assert jobs == ['stl', 'cad', 'stl', 'cad', 'stl', 'cad']

        for test in (cached_mismatch_forces_fresh_preview_and_exact_mobile_cad,
                     aliases_files_and_revert_cannot_restore_the_rejected_cached_mesh,
                     stopped_failed_and_expired_refreshes_keep_old_stl_and_allow_retry,
                     superseded_cad_headers_cannot_invalidate_other_verified_previews,
                     other_complete_downloads_stay_reusable_while_rejected_version_refreshes):
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
            except Exception:
                failures.append({'test': test.__name__, 'error': traceback.format_exc(), 'browser_errors': errors})
                print('FAIL ' + test.__name__ + ': ' + failures[-1]['error'], flush=True)
            finally:
                context.close()
        browser.close()
    report = {'endpoint': BASE, 'passed': passed, 'failures': failures,
        'old_mesh_sha256': old[1]['mesh_sha256'], 'updated_mesh_sha256': new[1]['mesh_sha256'],
        'updated_zip_sha256': new[1]['file_sha256'], 'facets_unchanged': new[2][80:] == old[2][80:],
        'transport': 'compiled assets; native CAD fixtures with a valid alternative STL header, matching ZIP metadata and unchanged facets; held headers and virtual deadlines' if OFFLINE else 'local HTTP'}
    (ROOT / 'review/cloud_cad_cache_recovery_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    assert not failures, report


if __name__ == '__main__':
    main()
