"""Verify recognizable filenames belong to the actual verified download bytes."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import traceback
from zipfile import ZipFile

from playwright.sync_api import expect, sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = '--offline' in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5178')
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))


def main():
    passed, failures, downloads = [], [], []
    original, custom, comb = (fixture(name) for name in ('parts_tray_original', 'parts_tray', 'cable_comb'))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        context = browser.new_context(accept_downloads=True)
        context.set_default_timeout(120000)
        if OFFLINE:
            attach_assets(context)

        def open_model(page, name='parts_tray'):
            page.goto(BASE + '?model=' + name)
            expect(page.locator('#download')).to_be_enabled()

        def rebuild(page):
            page.locator('#rebuild').click()
            expect(page.locator('#download')).to_be_enabled()

        def download(page, button='download'):
            with page.expect_download() as event:
                page.locator('#' + button).click()
            item = event.value
            body = Path(item.path()).read_bytes()
            row = {'filename': item.suggested_filename, 'file_sha256': hashlib.sha256(body).hexdigest(),
                   'preview_size': page.locator('#model-size').inner_text()}
            downloads.append(row)
            return row, body

        def replay(page, sample):
            jobs = []
            archive, metadata, mesh = sample

            def generate(route):
                payload = route.request.post_data_json
                assert payload['parameters'] == metadata['parameters'], payload
                jobs.append(payload.get('format', 'stl'))
                if payload.get('format') == 'cad':
                    route.fulfill(body=archive, headers=headers(metadata))
                else:
                    value = {**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}
                    route.fulfill(body=mesh, headers=headers(value, 'model/stl'))

            page.route('**/api/generate', generate)
            return jobs

        def defaults_keep_existing_names(page):
            replay(page, original)
            open_model(page)
            row, _ = download(page)
            assert row['filename'] == 'parts_tray.stl'
            row, body = download(page, 'download-cad')
            assert row['filename'] == 'parts_tray-cad.zip' and body == original[0]
            row, body = download(page)
            assert row['filename'] == 'parts_tray.stl' and body == original[2]

        def real_decimal_variants_have_distinct_stl_and_cad_names(page):
            open_model(page)
            names = {'stl': [], 'cad': []}
            for length in ('180.5', '201.35'):
                page.locator('#param-length').fill(length)
                rebuild(page)
                stl, mesh = download(page)
                assert stl['preview_size'] == f'{length} × 100 × 24'
                assert stl['filename'] == f"parts_tray-custom-{length}x100x24mm-{stl['file_sha256'][:12]}.stl"
                cad, body = download(page, 'download-cad')
                assert cad['filename'] == f"parts_tray-custom-{length}x100x24mm-{cad['file_sha256'][:12]}-cad.zip"
                with ZipFile(io.BytesIO(body)) as archive:
                    assert archive.testzip() is None
                    assert archive.read('parts_tray.stl') == mesh
                    assert json.loads(archive.read('parameters.json'))['parameters']['length'] == float(length)
                names['stl'].append(stl['filename'])
                names['cad'].append(cad['filename'])
            assert all(values[0] != values[1] for values in names.values())

        def fingerprints_distinguish_internal_changes_at_the_same_size(page):
            open_model(page)
            names, hashes = [], []
            for columns in ('2', '4'):
                page.locator('#param-columns').fill(columns)
                rebuild(page)
                row, _ = download(page)
                assert row['preview_size'] == '150 × 100 × 24'
                assert row['filename'] == f"parts_tray-custom-150x100x24mm-{row['file_sha256'][:12]}.stl"
                names.append(row['filename'])
                hashes.append(row['file_sha256'])
            assert names[0] != names[1] and hashes[0] != hashes[1]

        def reverted_edits_keep_the_verified_cached_name(page):
            jobs = replay(page, custom)
            open_model(page)
            page.locator('#param-length').fill('180.5')
            rebuild(page)
            first, body = download(page, 'download-cad')
            assert body == custom[0]
            page.locator('#param-length').fill('201.35')
            expect(page.locator('#download-cad')).to_be_disabled()
            page.locator('#revert-parameters').click()
            second, body = download(page, 'download-cad')
            assert second == first and body == custom[0]
            assert jobs == ['stl', 'cad'], jobs

        def list_dimensions_use_the_mesh_size_and_save_files_keep_their_name(page):
            replay(page, comb)
            open_model(page, 'cable_comb')
            page.locator('#param-cable_diameters').fill('2, 3.5, 9')
            rebuild(page)
            row, body = download(page)
            assert body == comb[2]
            dimensions = 'x'.join(f'{value:.2f}'.rstrip('0').rstrip('.') for value in comb[1]['bounds_mm'])
            assert row['filename'] == f"cable_comb-custom-{dimensions}mm-{comb[1]['mesh_sha256'][:12]}.stl"
            page.locator('.saved-dimensions summary').click()
            with page.expect_download() as event:
                page.locator('#save-dimensions').click()
            assert event.value.suggested_filename == 'cable_comb-dimensions.json'

        for check in (defaults_keep_existing_names,
                      real_decimal_variants_have_distinct_stl_and_cad_names,
                      fingerprints_distinguish_internal_changes_at_the_same_size,
                      reverted_edits_keep_the_verified_cached_name,
                      list_dimensions_use_the_mesh_size_and_save_files_keep_their_name):
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
    report = {'base': BASE, 'passed': passed, 'failures': failures, 'downloads': downloads,
              'transport': 'compiled assets with native CAD jobs and real export fixtures' if OFFLINE else 'local HTTP bridge'}
    (ROOT / 'review/cloud_download_names_validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    sys.exit(bool(failures))


if __name__ == '__main__':
    main()
