"""Verify exact CAD/kit reuse and bounded file retention through browser history."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import traceback
from urllib.parse import unquote
from zipfile import ZIP_STORED, ZipFile

from playwright.sync_api import sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from validation_job import native_request
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = '--offline' in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5178')
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))


def main():
    original, custom, assembly = (fixture(name) for name in
                                  ('parts_tray_original', 'parts_tray', 'soap_dish_assembly'))
    status, assembly_mesh, response_headers = native_request({
        'model': 'soap_dish_assembly', 'parameters': assembly[1]['parameters']})
    assert status == 200, (status, assembly_mesh[:250])
    assembly_preview = json.loads(unquote(response_headers['X-Model-Metadata']))
    assert assembly_preview['mesh_sha256'] == assembly[1]['mesh_sha256']
    padded = io.BytesIO(custom[0])
    with ZipFile(padded, 'a', compression=ZIP_STORED) as archive:
        archive.writestr('cache-budget-padding.bin', bytes(6 * 1024 * 1024 - len(custom[0])))
    large_zip = padded.getvalue()
    with ZipFile(io.BytesIO(large_zip)) as archive:
        assert archive.testzip() is None and archive.read('parts_tray.stl') == custom[2]
    assert len(large_zip) < 8 * 1024 * 1024 and len(large_zip) * 6 > 32 * 1024 * 1024
    status, dense_zip, response_headers = native_request({'model': 'parts_tray',
        'parameters': {**custom[1]['parameters'], 'columns': 6, 'rows': 6}, 'format': 'cad'})
    assert status == 200, (status, dense_zip[:250])
    dense_metadata = json.loads(unquote(response_headers['X-Model-Metadata']))
    with ZipFile(io.BytesIO(dense_zip)) as archive:
        assert archive.testzip() is None
        dense_mesh = archive.read('parts_tray.stl')
    assert hashlib.sha256(dense_mesh).hexdigest() == dense_metadata['mesh_sha256']
    assert len(dense_mesh) < 8 * 1024 * 1024 and len(dense_mesh) * 20 > 32 * 1024 * 1024
    shared_variants = []
    for body, metadata, mesh in (original, (dense_zip, dense_metadata, dense_mesh)):
        padded = io.BytesIO(body)
        with ZipFile(padded, 'a', compression=ZIP_STORED) as archive:
            archive.writestr('cache-budget-padding.bin', bytes(6 * 1024 * 1024 - len(body)))
        padded_body = padded.getvalue()
        with ZipFile(io.BytesIO(padded_body)) as archive:
            assert archive.testzip() is None and archive.read('parts_tray.stl') == mesh
        assert len(padded_body) < 8 * 1024 * 1024
        shared_variants.append((padded_body, metadata, mesh))
    passed, failures, shared_retention = [], [], []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=[
            '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])

        def setup(page, large=False, file_variants=None):
            jobs = []

            def generate(route):
                payload = route.request.post_data_json
                kind = payload.get('format', 'stl')
                jobs.append((payload['model'], kind))
                if payload['model'] == 'soap_dish_assembly':
                    assert payload['parameters'] == assembly[1]['parameters']
                    body, metadata = (assembly[0], assembly[1]) if kind == 'cad' else (assembly_mesh, assembly_preview)
                else:
                    assert payload['model'] == 'parts_tray'
                    if file_variants:
                        selected = next(row for row in file_variants if payload['parameters'] == row[1]['parameters'])
                    else:
                        selected = large[payload['parameters']['length']] if large else custom if payload['parameters'] == custom[1]['parameters'] else original
                    assert payload['parameters'] == selected[1]['parameters'], payload
                    body = selected[0]
                    metadata = {**selected[1], 'file_sha256': hashlib.sha256(body).hexdigest()}
                    if kind != 'cad':
                        body = selected[2]
                        metadata = {**selected[1], 'format': 'stl', 'file_sha256': selected[1]['mesh_sha256']}
                route.fulfill(body=body, headers=headers(metadata, 'application/zip' if kind == 'cad' else 'model/stl'))

            page.route('**/api/generate', generate)
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            return jobs

        def wait_model(page, name='parts_tray'):
            page.wait_for_function("name => new URL(location.href).searchParams.get('model') === name && document.querySelector('#editor').open && document.querySelector('#preview-loading').hidden", arg=name)

        def ready(page):
            page.wait_for_function("() => document.querySelector('#editor').open && !document.querySelector('#download-cad').disabled")

        def open_tray(page, customized=False):
            page.locator('[data-model="parts_tray"]').click()
            wait_model(page)
            ready(page)
            if customized:
                page.locator('[data-parameter="length"]').fill('180.5')
                page.locator('#rebuild').click()
                ready(page)

        def download(page, body, button='download-cad', keyboard=False):
            with page.expect_download() as event:
                if keyboard:
                    page.locator('#' + button).focus()
                    page.keyboard.press('Space')
                else:
                    page.locator('#' + button).click()
            assert Path(event.value.path()).read_bytes() == body
            return event.value.suggested_filename

        def round_trip(page):
            identity = page.evaluate('history.state.everydayPrints.id')
            page.go_back()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            page.go_forward()
            page.wait_for_function('id => history.state.everydayPrints.id === id', arg=identity)
            wait_model(page)

        def custom_history_keeps_exact_files_and_mobile_keyboard_downloads(page):
            jobs = setup(page)
            open_tray(page, customized=True)
            filename = download(page, custom[0])
            assert filename == f"parts_tray-custom-180.5x100x24mm-{hashlib.sha256(custom[0]).hexdigest()[:12]}-cad.zip"
            for _ in range(2):
                round_trip(page)
                ready(page)
                assert page.locator('#model-size').inner_text() == '180.5 × 100 × 24'
                assert download(page, custom[0]) == filename
                assert download(page, custom[2], 'download') == f"parts_tray-custom-180.5x100x24mm-{custom[1]['mesh_sha256'][:12]}.stl"
                assert jobs == [('parts_tray', 'stl'), ('parts_tray', 'cad')]
            page.screenshot(path=str(ROOT / 'review/cloud_history_downloads_desktop.png'))
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('#close-editor').click()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            page.go_forward()
            wait_model(page)
            ready(page)
            assert download(page, custom[0], keyboard=True) == filename
            cad = page.locator('#download-cad')
            assert cad.evaluate('element => element === document.activeElement')
            box, clip = cad.bounding_box(), page.locator('.editor-layout').bounding_box()
            assert box['height'] >= 44 and box['y'] >= clip['y']
            assert box['y'] + box['height'] <= min(844, clip['y'] + clip['height']) + 1
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('#stop-build').is_hidden()
            assert jobs == [('parts_tray', 'stl'), ('parts_tray', 'cad')]
            page.screenshot(path=str(ROOT / 'review/cloud_history_downloads_mobile.png'))

        def original_history_keeps_once_refreshed_mesh_and_zip(page):
            jobs = setup(page)
            open_tray(page)
            assert download(page, original[0]) == 'parts_tray-cad.zip'
            assert download(page, original[2], 'download') == 'parts_tray.stl'
            round_trip(page)
            ready(page)
            assert download(page, original[0]) == 'parts_tray-cad.zip'
            assert download(page, original[2], 'download') == 'parts_tray.stl'
            assert jobs == [('parts_tray', 'stl'), ('parts_tray', 'cad')]

        def invalid_and_dirty_history_keeps_gates_and_new_previews_discard_old_cad(page):
            jobs = setup(page)
            open_tray(page, customized=True)
            custom_name = download(page, custom[0])
            page.locator('[data-parameter="height"]').fill('')
            round_trip(page)
            assert page.locator('[data-parameter="height"]').input_value() == ''
            assert page.locator('[data-parameter="height"]').get_attribute('aria-invalid') == 'true'
            assert page.locator('#download').is_disabled() and page.locator('#download-cad').is_disabled()
            page.locator('#revert-parameters').click()
            assert download(page, custom[0]) == custom_name
            page.locator('[data-parameter="length"]').fill('190.55')
            round_trip(page)
            assert page.locator('[data-parameter="length"]').input_value() == '190.55'
            assert page.locator('#model-size').inner_text() == '180.5 × 100 × 24'
            assert page.locator('#download').is_disabled() and page.locator('#download-cad').is_disabled()
            page.locator('#revert-parameters').click()
            assert download(page, custom[0]) == custom_name
            assert jobs == [('parts_tray', 'stl'), ('parts_tray', 'cad')]
            page.locator('[data-parameter="length"]').fill('150')
            page.locator('#rebuild').click()
            ready(page)
            assert download(page, original[0]) == 'parts_tray-cad.zip'
            assert download(page, original[2], 'download') == 'parts_tray.stl'
            round_trip(page)
            ready(page)
            assert download(page, original[0]) == 'parts_tray-cad.zip'
            assert jobs == [('parts_tray', 'stl'), ('parts_tray', 'cad')] * 2

        def assembly_kit_history_keeps_reference_and_component_navigation(page):
            jobs = setup(page)
            page.locator('[data-model="soap_dish_assembly"]').click()
            wait_model(page, 'soap_dish_assembly')
            for key, value in assembly[1]['parameters'].items():
                page.locator(f'[data-parameter="{key}"]').fill(str(value))
            page.locator('#rebuild').click()
            ready(page)
            filename = download(page, assembly[0])
            assert filename == f"soap_dish_assembly-custom-160x84x14mm-{hashlib.sha256(assembly[0]).hexdigest()[:12]}-kit.zip"
            page.locator('[data-part="soap_dish_tray"]').click()
            wait_model(page, 'soap_dish_tray')
            assert page.locator('[data-parameter="length"]').input_value() == '160'
            page.go_back()
            wait_model(page, 'soap_dish_assembly')
            ready(page)
            assert page.locator('#download').is_hidden()
            assert page.locator('#model-size').inner_text() == '160 × 84 × 14'
            assert download(page, assembly[0]) == filename
            page.go_forward()
            wait_model(page, 'soap_dish_tray')
            page.go_back()
            wait_model(page, 'soap_dish_assembly')
            ready(page)
            assert download(page, assembly[0]) == filename
            assert jobs == [('soap_dish_assembly', 'stl'), ('soap_dish_assembly', 'cad')]

        def superseded_cached_verification_cannot_restore_old_cad(page):
            jobs = setup(page)
            open_tray(page, customized=True)
            download(page, custom[0])
            page.go_back()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            page.evaluate("""() => {
              const digest = crypto.subtle.digest.bind(crypto.subtle);
              crypto.subtle.digest = async (...args) => {
                const value = await digest(...args);
                if (window.historyHashHeld) return value;
                window.historyHashHeld = true;
                return new Promise(resolve => { window.releaseHistoryHash = () => resolve(value); });
              };
            }""")
            page.go_forward()
            page.wait_for_function("() => typeof window.releaseHistoryHash === 'function'")
            page.locator('#close-editor').click()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            open_tray(page)
            page.locator('[data-parameter="width"]').focus()
            page.evaluate('window.releaseHistoryHash()')
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            assert page.locator('[data-parameter="width"]').evaluate('element => element === document.activeElement')
            assert page.locator('#model-size').inner_text() == '150 × 100 × 24'
            assert download(page, original[0]) == 'parts_tray-cad.zip'
            assert jobs == [('parts_tray', 'stl'), ('parts_tray', 'cad')] * 2

        def reopened_library_cards_reuse_original_files_without_requests(page):
            jobs = setup(page)
            open_tray(page)
            assert download(page, original[0]) == 'parts_tray-cad.zip'
            page.locator('#close-editor').click()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            open_tray(page)
            assert download(page, (CLOUD / 'public/models/parts_tray.stl').read_bytes(), 'download') == 'parts_tray.stl'
            assert download(page, original[0]) == 'parts_tray-cad.zip'
            assert download(page, original[2], 'download') == 'parts_tray.stl'
            assert jobs == [('parts_tray', 'stl'), ('parts_tray', 'cad')]
            page.screenshot(path=str(ROOT / 'review/cloud_download_reuse_desktop.png'))
            page.set_viewport_size({'width': 390, 'height': 600})
            page.locator('#close-editor').click()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            open_tray(page)
            assert download(page, original[0], keyboard=True) == 'parts_tray-cad.zip'
            assert page.locator('#download-cad').evaluate('element => element === document.activeElement')
            assert jobs == [('parts_tray', 'stl'), ('parts_tray', 'cad')]
            page.screenshot(path=str(ROOT / 'review/cloud_download_reuse_mobile.png'))

        def reopened_named_versions_reuse_custom_files_but_changed_parameters_build(page):
            jobs = setup(page)
            open_tray(page, customized=True)
            filename = download(page, custom[0])
            page.locator('.saved-dimensions').evaluate('element => { element.open = true; }')
            page.locator('#version-name').fill('Wide tray')
            page.locator('#save-version').click()
            version = page.locator('#version-choice').input_value()
            page.locator('#close-editor').click()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            open_tray(page)
            page.locator('#version-choice').select_option(version)
            page.locator('#load-version').click()
            assert page.locator('[data-parameter="length"]').input_value() == '180.5'
            assert page.locator('#download').is_disabled() and page.locator('#download-cad').is_disabled()
            page.locator('#rebuild').focus()
            page.keyboard.press('Space')
            ready(page)
            assert download(page, custom[0]) == filename
            assert download(page, custom[2], 'download').startswith('parts_tray-custom-180.5x100x24mm-')
            assert jobs == [('parts_tray', 'stl'), ('parts_tray', 'cad')]
            page.locator('[data-parameter="length"]').fill('150')
            page.locator('#rebuild').click()
            ready(page)
            assert download(page, original[0]) == 'parts_tray-cad.zip'
            assert jobs == [('parts_tray', 'stl'), ('parts_tray', 'cad')] * 2

        def reopened_assembly_files_reuse_exact_kit_and_keep_model_boundaries(page):
            jobs = setup(page)
            page.locator('[data-model="soap_dish_assembly"]').click()
            wait_model(page, 'soap_dish_assembly')
            for key, value in assembly[1]['parameters'].items():
                page.locator(f'[data-parameter="{key}"]').fill(str(value))
            page.locator('#rebuild').click()
            ready(page)
            filename = download(page, assembly[0])
            page.locator('#close-editor').click()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            page.locator('[data-model="soap_dish_assembly"]').click()
            wait_model(page, 'soap_dish_assembly')
            page.locator('#dimensions-file').set_input_files({'name': 'parameters.json',
                'mimeType': 'application/json', 'buffer': json.dumps(assembly[1]).encode('utf-8')})
            page.wait_for_function("() => document.querySelector('#param-length').value === '160'")
            page.locator('#rebuild').click()
            ready(page)
            assert download(page, assembly[0]) == filename
            assert page.locator('#download').is_hidden()
            assert jobs == [('soap_dish_assembly', 'stl'), ('soap_dish_assembly', 'cad')]
            page.locator('#close-editor').click()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            open_tray(page)
            assert download(page, original[0]) == 'parts_tray-cad.zip'
            assert jobs[-2:] == [('parts_tray', 'stl'), ('parts_tray', 'cad')]

        def cached_preview_verification_respects_stop_edits_deadlines_and_navigation(page):
            jobs = setup(page)
            open_tray(page, customized=True)
            filename = download(page, custom[0])
            page.locator('#close-editor').click()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            open_tray(page)
            page.clock.install()
            page.evaluate("""() => {
              const digest = crypto.subtle.digest.bind(crypto.subtle);
              window.cachedHashes = [];
              crypto.subtle.digest = async (...args) => {
                const value = await digest(...args);
                if (!window.holdCachedHash) return value;
                return new Promise(resolve => { window.cachedHashes.push(() => resolve(value)); });
              };
            }""")

            def hold(count):
                page.evaluate('window.holdCachedHash = true')
                page.locator('#rebuild').focus()
                page.keyboard.press('Space')
                page.wait_for_function('count => window.cachedHashes.length === count', arg=count)
                assert page.locator('#stop-build').evaluate('element => element === document.activeElement')
                assert 'Restoring' in page.locator('#form-message').inner_text()
                assert jobs == [('parts_tray', 'stl'), ('parts_tray', 'cad')]

            def release(index):
                page.evaluate('index => { window.holdCachedHash = false; window.cachedHashes[index](); }', index)
                page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')

            page.locator('[data-parameter="length"]').fill('180.5')
            hold(1)
            page.keyboard.press('Space')
            assert 'Stopped waiting.' in page.locator('#form-message').inner_text()
            assert 'service' not in page.locator('#form-message').inner_text()
            release(0)
            assert page.locator('#model-size').inner_text() == '150 × 100 × 24'
            hold(2)
            page.locator('[data-parameter="length"]').fill('190.55')
            release(1)
            page.wait_for_function("() => !document.querySelector('#rebuild').disabled")
            assert page.locator('[data-parameter="length"]').input_value() == '190.55'
            assert page.locator('[data-parameter="length"]').evaluate('element => element === document.activeElement')
            assert page.locator('#model-size').inner_text() == '180.5 × 100 × 24'
            assert page.locator('#download-cad').is_disabled()
            page.locator('#revert-parameters').click()
            assert download(page, custom[0]) == filename
            hold(3)
            page.clock.fast_forward(15 * 60 * 1000)
            assert 'exceeded 15 minutes' in page.locator('#form-message').inner_text()
            assert 'service' not in page.locator('#form-message').inner_text()
            release(2)
            assert download(page, custom[0]) == filename
            hold(4)
            page.locator('#close-editor').click()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            page.evaluate('window.holdCachedHash = false')
            open_tray(page)
            release(3)
            assert page.locator('#model-size').inner_text() == '150 × 100 × 24'
            assert download(page, original[0]) == 'parts_tray-cad.zip'
            assert jobs == [('parts_tray', 'stl'), ('parts_tray', 'cad')] * 2

        def shared_files_survive_repeated_views(page, visits):
            jobs = setup(page, file_variants=shared_variants)
            page.evaluate("""() => {
              const create = URL.createObjectURL.bind(URL), ids = new WeakMap();
              window.cadReferences = [];
              let next = 0;
              URL.createObjectURL = blob => {
                if (blob.type === 'application/zip') {
                  if (!ids.has(blob)) ids.set(blob, ++next);
                  window.cadReferences.push({id: ids.get(blob), bytes: blob.size});
                }
                return create(blob);
              };
              const digest = crypto.subtle.digest.bind(crypto.subtle), buffers = new WeakMap();
              window.meshReferences = [];
              let nextBuffer = 0;
              crypto.subtle.digest = (...args) => {
                const buffer = args[1] instanceof ArrayBuffer ? args[1] : args[1].buffer;
                if (!buffers.has(buffer)) buffers.set(buffer, ++nextBuffer);
                window.meshReferences.push({id: buffers.get(buffer), bytes: buffer.byteLength});
                return digest(...args);
              };
            }""")
            open_tray(page)
            first_id = page.evaluate('history.state.everydayPrints.id')
            filename = download(page, shared_variants[0][0])
            cable = next(item for item in json.loads((CLOUD / 'public/catalog.json').read_text(encoding='utf-8'))['models']
                         if item['name'] == 'cable_comb')

            def load_file(record):
                page.locator('#dimensions-file').set_input_files({'name': 'parameters.json',
                    'mimeType': 'application/json', 'buffer': json.dumps(record).encode('utf-8')})
                wait_model(page, record['model'])

            for _ in range(visits):
                load_file({'model': cable['name'], 'parameters': cable['defaults'], 'units': 'mm'})
                load_file(dense_metadata)
                page.locator('#rebuild').click()
                ready(page)
                dense_filename = download(page, shared_variants[1][0])
                assert f'180.5x100x24mm-{hashlib.sha256(shared_variants[1][0]).hexdigest()[:12]}-cad.zip' in dense_filename
            newest_id = page.evaluate('history.state.everydayPrints.id')
            assert jobs == [('parts_tray', 'stl'), ('parts_tray', 'cad')] * 2, jobs
            blob_ids = page.evaluate('window.cadReferences')
            buffer_ids = page.evaluate('window.meshReferences')
            assert len(blob_ids) == visits + 1 and len({row['id'] for row in blob_ids}) == 2, blob_ids
            assert len({row['id'] for row in buffer_ids if row['bytes'] == len(dense_mesh)}) == 1, buffer_ids
            page.evaluate('steps => history.go(steps)', -2 * visits)
            page.wait_for_function('id => history.state.everydayPrints.id === id', arg=first_id)
            wait_model(page)
            ready(page)
            if visits == 20:
                page.set_viewport_size({'width': 390, 'height': 844})
            assert download(page, shared_variants[0][0], keyboard=visits == 20) == filename
            assert download(page, original[2], 'download') == 'parts_tray.stl'
            assert len(jobs) == 4, 'Shared file references evicted the older distinct download'
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(ROOT / f'review/cloud_shared_history_{"mobile" if visits == 20 else "desktop"}.png'))
            page.evaluate('steps => history.go(steps)', 2 * visits)
            page.wait_for_function('id => history.state.everydayPrints.id === id', arg=newest_id)
            wait_model(page)
            ready(page)
            assert download(page, shared_variants[1][0], keyboard=visits == 20) == dense_filename
            assert download(page, dense_mesh, 'download') == f'parts_tray-custom-180.5x100x24mm-{dense_metadata["mesh_sha256"][:12]}.stl'
            assert len(jobs) == 4
            shared_retention.append({'repeated_dense_views': visits, 'native_jobs': len(jobs),
                'unique_download_blobs': len({row['id'] for row in blob_ids}),
                'unique_dense_mesh_buffers': len({row['id'] for row in buffer_ids if row['bytes'] == len(dense_mesh)}),
                'dense_mesh_bytes': len(dense_mesh), 'two_zip_bytes': sum(len(row[0]) for row in shared_variants)})

        def shared_cad_references_do_not_evict_older_distinct_downloads(page):
            shared_files_survive_repeated_views(page, 6)

        def shared_dense_meshes_and_cad_survive_twenty_reopened_views(page):
            shared_files_survive_repeated_views(page, 20)

        def archive_budget_evicts_old_zips_without_discarding_verified_previews(page):
            variants = {}
            for index in range(6):
                if not index:
                    body, metadata, mesh = custom
                    variants[180.5] = (large_zip, metadata, mesh)
                    continue
                else:
                    status, body, response_headers = native_request({'model': 'parts_tray',
                        'parameters': {**custom[1]['parameters'], 'length': 180.5 + index}, 'format': 'cad'})
                    assert status == 200, (status, body[:250])
                    metadata = json.loads(unquote(response_headers['X-Model-Metadata']))
                    with ZipFile(io.BytesIO(body)) as archive:
                        mesh = archive.read('parts_tray.stl')
                padded = io.BytesIO(body)
                with ZipFile(padded, 'a', compression=ZIP_STORED) as archive:
                    archive.writestr('cache-budget-padding.bin', bytes(6 * 1024 * 1024 - len(body)))
                padded_body = padded.getvalue()
                with ZipFile(io.BytesIO(padded_body)) as archive:
                    assert archive.testzip() is None and archive.read('parts_tray.stl') == mesh
                assert len(padded_body) < 8 * 1024 * 1024
                variants[180.5 + index] = (padded_body, metadata, mesh)
            jobs = setup(page, large=variants)
            static_requests = []
            page.route('**/models/parts_tray.stl', lambda route: (static_requests.append(route.request.url), route.fallback()))
            open_tray(page, customized=True)
            first_id = page.evaluate('history.state.everydayPrints.id')
            filename = download(page, large_zip)
            cable = json.loads((CLOUD / 'public/catalog.json').read_text(encoding='utf-8'))['models'][1]

            def load_file(record):
                page.locator('#dimensions-file').set_input_files({'name': 'parameters.json',
                    'mimeType': 'application/json', 'buffer': json.dumps(record).encode('utf-8')})
                wait_model(page, record['model'])

            for index in range(1, 6):
                load_file({'model': cable['name'], 'parameters': cable['defaults'], 'units': 'mm'})
                selected = variants[180.5 + index]
                load_file(selected[1])
                page.locator('#rebuild').click()
                ready(page)
                newest_filename = download(page, selected[0])
                assert f'{180.5 + index}x100x24mm-' in newest_filename
            newest_id = page.evaluate('history.state.everydayPrints.id')
            assert jobs == [('parts_tray', 'stl'), ('parts_tray', 'cad')] * 6
            original_reads = len(static_requests)
            page.evaluate('() => history.go(-10)')
            page.wait_for_function('id => history.state.everydayPrints.id === id', arg=first_id)
            wait_model(page)
            ready(page)
            assert download(page, custom[2], 'download').endswith('.stl')
            assert len(static_requests) == original_reads, 'ZIP eviction also discarded the verified preview'
            assert download(page, large_zip) == filename
            assert jobs == [('parts_tray', 'stl'), ('parts_tray', 'cad')] * 6 + [('parts_tray', 'cad')]
            page.evaluate('() => history.go(10)')
            page.wait_for_function('id => history.state.everydayPrints.id === id', arg=newest_id)
            wait_model(page)
            ready(page)
            assert download(page, variants[185.5][0]) == newest_filename
            assert len(jobs) == 13, 'The newest retained ZIP was rebuilt'

        for test in (custom_history_keeps_exact_files_and_mobile_keyboard_downloads,
                     original_history_keeps_once_refreshed_mesh_and_zip,
                     invalid_and_dirty_history_keeps_gates_and_new_previews_discard_old_cad,
                     assembly_kit_history_keeps_reference_and_component_navigation,
                     superseded_cached_verification_cannot_restore_old_cad,
                     reopened_library_cards_reuse_original_files_without_requests,
                     reopened_named_versions_reuse_custom_files_but_changed_parameters_build,
                     reopened_assembly_files_reuse_exact_kit_and_keep_model_boundaries,
                     cached_preview_verification_respects_stop_edits_deadlines_and_navigation,
                     shared_cad_references_do_not_evict_older_distinct_downloads,
                     shared_dense_meshes_and_cad_survive_twenty_reopened_views,
                     archive_budget_evicts_old_zips_without_discarding_verified_previews):
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
        'history_cache_bytes': 32 * 1024 * 1024, 'padded_zip_bytes': len(large_zip),
        'padded_zip_sha256': hashlib.sha256(large_zip).hexdigest(),
        'shared_file_retention': shared_retention,
        'transport': 'compiled assets and exact CAD fixtures, native assembly and dense meshes, delayed hashes, real padded ZIPs and weak reference identity observation' if OFFLINE else 'local HTTP'}
    (ROOT / 'review/cloud_history_downloads_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    assert not failures, report


if __name__ == '__main__':
    main()
