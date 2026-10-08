"""Verify keyboard focus through preview/CAD builds, Stop, failure and navigation."""
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright
from browser_assets import ASSETS, OFFLINE_BASE, attach_assets
from browser_transfers import DEFERRED_BODY
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = '--offline' in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5178')
WAIT_MS = 15 * 60 * 1000
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))


def main():
    original, custom = fixture('parts_tray_original'), fixture('parts_tray')
    passed, failures, delayed_viewer_cases = [], [], []
    pending_viewers = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1080}, accept_downloads=True)
        context.set_default_timeout(20000)
        if OFFLINE:
            attach_assets(context)

        def setup(page, customized=False, hold_viewer=False):
            page.clock.install()
            page.add_init_script(DEFERRED_BODY + """
              window.holdFocusJobs = false;
              window.pendingFocusJobs = [];
              const focusFetch = window.fetch;
              window.fetch = async (...args) => {
                const response = await focusFetch(...args);
                if (!String(args[0]).includes('/api/generate') || !window.holdFocusJobs) return response;
                const bytes = await response.arrayBuffer();
                window.deferFileBody(response, bytes, async () => {});
                await new Promise(resolve => window.pendingFocusJobs.push(resolve));
                return response;
              };
            """)
            control = {'jobs': [], 'failed': False, 'modules': []}
            if hold_viewer:
                pending_viewers[page] = control['modules']
                page.route('**/assets/viewer-*.js' if OFFLINE else '**/web/viewer.js*',
                           lambda route: control['modules'].append(route))

            def generate(route):
                payload = route.request.post_data_json
                control['jobs'].append(payload.get('format', 'stl'))
                if control['failed']:
                    route.fulfill(status=503, json={'error': 'Controlled service failure. Try again.'})
                    return
                archive, metadata, mesh = custom if payload['parameters']['length'] == 180.5 else original
                assert payload['parameters'] == metadata['parameters'], payload
                if payload.get('format') == 'cad':
                    route.fulfill(body=archive, headers=headers(metadata))
                else:
                    value = {**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}
                    route.fulfill(body=mesh, headers=headers(value, 'model/stl'))

            page.route('**/api/generate', generate)
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            page.locator('[data-model="parts_tray"]').click()
            expect(page.locator('#download')).to_be_enabled()
            if customized:
                page.locator('#param-length').fill('180.5')
                page.locator('#rebuild').click()
                expect(page.locator('#download-cad')).to_be_enabled()
            page.evaluate('() => { window.holdFocusJobs = true; }')
            return control

        def pending(page, count=1):
            page.wait_for_function('count => window.pendingFocusJobs.length === count', arg=count)
            expect(page.locator('#stop-build')).to_be_visible()

        def start(page, button='rebuild', count=1):
            page.locator('#' + button).focus()
            page.locator('#' + button).press('Enter')
            pending(page, count)
            expect(page.locator('#stop-build')).to_be_focused()

        def release(page, index=0):
            page.evaluate('index => window.pendingFocusJobs[index]()', index)

        def preview_keyboard_completion_returns_to_update_and_exact_stl(page):
            setup(page)
            page.locator('#param-length').fill('180.5')
            start(page)
            release(page)
            expect(page.locator('#download')).to_be_enabled()
            expect(page.locator('#rebuild')).to_be_focused()
            page.keyboard.press('Tab')
            expect(page.locator('#download')).to_be_focused()
            with page.expect_download() as event:
                page.keyboard.press('Enter')
            assert Path(event.value.path()).read_bytes() == custom[2]

        def stop_preview_returns_to_update_before_late_reply(page):
            setup(page)
            page.locator('#param-length').fill('180.5')
            start(page)
            page.keyboard.press('Enter')
            expect(page.locator('#stop-build')).to_be_hidden()
            expect(page.locator('#rebuild')).to_be_focused()
            expect(page.locator('#download')).to_be_disabled()
            release(page)
            expect(page.locator('#form-message')).to_contain_text('Stopped waiting')
            expect(page.locator('#rebuild')).to_be_focused()

        def input_submission_keeps_field_and_stop_returns_to_it(page):
            setup(page)
            field = page.locator('#param-length')
            field.fill('180.5')
            field.press('Enter')
            pending(page)
            expect(field).to_be_focused()
            page.locator('#stop-build').focus()
            page.keyboard.press('Enter')
            expect(field).to_be_focused()
            assert field.input_value() == '180.5'
            release(page)
            expect(field).to_be_focused()

        def custom_cad_returns_to_download_and_reuses_verified_zip(page):
            control = setup(page, customized=True)
            start(page, 'download-cad')
            with page.expect_download() as event:
                release(page)
            assert Path(event.value.path()).read_bytes() == custom[0]
            expect(page.locator('#download-cad')).to_be_focused()
            with page.expect_download() as cached:
                page.keyboard.press('Enter')
            assert Path(cached.value.path()).read_bytes() == custom[0]
            assert cached.value.suggested_filename == event.value.suggested_filename
            assert control['jobs'] == ['stl', 'cad']
            expect(page.locator('#download-cad')).to_be_focused()

        def original_cad_refresh_keeps_focus_through_both_requests(page):
            control = setup(page)
            start(page, 'download-cad')
            release(page)
            pending(page, 2)
            expect(page.locator('#stop-build')).to_be_focused()
            with page.expect_download() as event:
                release(page, 1)
            assert Path(event.value.path()).read_bytes() == original[0]
            assert control['jobs'] == ['stl', 'cad']
            expect(page.locator('#download-cad')).to_be_focused()

        def failed_requests_restore_keyboard_retry_controls(page):
            control = setup(page, customized=True)
            control['failed'] = True
            for index, button in enumerate(('rebuild', 'download-cad')):
                start(page, button, index + 1)
                release(page, index)
                expect(page.locator('#rebuild')).to_be_enabled()
                expect(page.locator('#' + button)).to_be_focused()
                expect(page.locator('#form-message')).to_contain_text('Controlled service failure')
                expect(page.locator('#download')).to_be_enabled()

        def completion_preserves_focus_moved_to_a_field(page):
            setup(page, customized=True)
            for index, button in enumerate(('rebuild', 'download-cad')):
                start(page, button, index + 1)
                field = page.locator('#param-width')
                field.focus()
                if button == 'download-cad':
                    with page.expect_download() as event:
                        release(page, index)
                    assert Path(event.value.path()).read_bytes() == custom[0]
                else:
                    release(page, index)
                expect(page.locator('#rebuild')).to_be_enabled()
                expect(field).to_be_focused()

        def deadlines_restore_keyboard_focus(page):
            setup(page, customized=True)
            for index, button in enumerate(('rebuild', 'download-cad')):
                start(page, button, index + 1)
                page.clock.fast_forward(WAIT_MS + 1)
                expect(page.locator('#stop-build')).to_be_hidden()
                expect(page.locator('#' + button)).to_be_focused()
                expect(page.locator('#form-message')).to_contain_text('exceeded 15 minutes')
                release(page, index)
                expect(page.locator('#' + button)).to_be_focused()

        def mobile_stop_is_visible_and_navigation_keeps_library_focus(page):
            page.set_viewport_size({'width': 390, 'height': 844})
            setup(page, customized=True)
            start(page, 'download-cad')
            rect = page.locator('#stop-build').bounding_box()
            assert rect['height'] >= 44 and 0 <= rect['y'] and rect['y'] + rect['height'] <= 844, rect
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(ROOT / 'review/cloud_build_focus_mobile.png'))
            page.locator('#close-editor').focus()
            page.keyboard.press('Enter')
            page.wait_for_function("() => !document.querySelector('#editor').open && !new URL(location.href).searchParams.has('model')")
            expect(page.locator('[data-model="parts_tray"]')).to_be_focused()
            release(page)
            page.clock.fast_forward(WAIT_MS + 1)
            expect(page.locator('[data-model="parts_tray"]')).to_be_focused()

        def visible_focus(page, selector):
            control = page.locator(selector)
            expect(control).to_be_focused()
            rect = control.bounding_box()
            layout = page.locator('.editor-layout').bounding_box()
            viewport = page.viewport_size
            assert rect and layout and viewport
            assert rect['height'] >= 44, rect
            assert max(0, layout['y']) <= rect['y'] <= rect['y'] + rect['height'] <= min(viewport['height'], layout['y'] + layout['height']), (rect, layout, viewport)
            assert 0 <= rect['x'] <= rect['x'] + rect['width'] <= viewport['width'], (rect, viewport)
            return {key: round(value, 3) for key, value in rect.items()}

        def release_viewer(page, control):
            assert len(control['modules']) == 1, 'Pending previews loaded duplicate 3D modules'
            route = control['modules'].pop()
            body = (ASSETS / urlparse(route.request.url).path.lstrip('/')).read_bytes() if OFFLINE else route.fetch().body()
            route.fulfill(body=body, content_type='text/javascript')
            page.wait_for_function("() => document.querySelector('#viewer canvas') && document.querySelector('#viewer').getAttribute('aria-busy') === 'false'")
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            expect(page.locator('.view-tools')).to_be_visible()
            expect(page.locator('#fallback-image')).to_be_hidden()

        def delayed_viewer_download(page, width, height, screenshot=None):
            page.set_viewport_size({'width': width, 'height': height})
            control = setup(page, customized=True, hold_viewer=True)
            expect(page.locator('#fallback-image')).to_be_visible()
            expect(page.locator('.view-tools')).to_be_hidden()
            start(page, 'download-cad')
            before = visible_focus(page, '#stop-build')
            release_viewer(page, control)
            after = visible_focus(page, '#stop-build')
            expect(page.locator('#download-cad')).to_be_disabled()
            expect(page.locator('#transfer-status')).to_be_hidden()
            if screenshot:
                page.screenshot(path=str(ROOT / f'review/cloud_build_focus_delayed_{screenshot}.png'))
            with page.expect_download() as event:
                release(page)
            archive = Path(event.value.path()).read_bytes()
            assert archive == custom[0]
            filename = f"parts_tray-custom-180.5x100x24mm-{hashlib.sha256(archive).hexdigest()[:12]}-cad.zip"
            assert event.value.suggested_filename == filename
            completed = visible_focus(page, '#download-cad')
            with page.expect_download() as cached:
                page.keyboard.press('Space')
            assert Path(cached.value.path()).read_bytes() == archive
            assert cached.value.suggested_filename == filename
            page.locator('#download').focus()
            with page.expect_download() as mesh:
                page.keyboard.press('Enter')
            assert Path(mesh.value.path()).read_bytes() == custom[2]
            assert mesh.value.suggested_filename == f"parts_tray-custom-180.5x100x24mm-{custom[1]['mesh_sha256'][:12]}.stl"
            assert control['jobs'] == ['stl', 'cad'], control['jobs']
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            delayed_viewer_cases.append({'viewport': page.viewport_size, 'before_loading': before,
                'after_loading': after, 'after_download': completed, 'cad_filename': filename,
                'cad_sha256': hashlib.sha256(archive).hexdigest(), 'stl_sha256': custom[1]['mesh_sha256'],
                'jobs': control['jobs']})

        def delayed_viewer_keeps_stop_and_download_visible_on_phone(page):
            delayed_viewer_download(page, 390, 844)

        def delayed_viewer_keeps_stop_and_download_visible_on_short_phone(page):
            delayed_viewer_download(page, 390, 600, 'mobile')

        def delayed_viewer_keeps_stop_and_download_visible_on_small_phone(page):
            delayed_viewer_download(page, 320, 568)

        def delayed_viewer_keeps_stop_and_download_visible_on_short_desktop(page):
            delayed_viewer_download(page, 1440, 600, 'desktop')

        def delayed_viewer_and_cad_preserve_focus_moved_to_measurement(page):
            page.set_viewport_size({'width': 390, 'height': 600})
            control = setup(page, customized=True, hold_viewer=True)
            start(page, 'download-cad')
            page.locator('#param-width').focus()
            before = visible_focus(page, '#param-width')
            release_viewer(page, control)
            after = visible_focus(page, '#param-width')
            with page.expect_download() as event:
                release(page)
            assert Path(event.value.path()).read_bytes() == custom[0]
            completed = visible_focus(page, '#param-width')
            assert page.locator('#param-width').input_value() == '100'
            assert control['jobs'] == ['stl', 'cad']
            delayed_viewer_cases.append({'viewport': page.viewport_size, 'chosen_measurement': 'width',
                'before_loading': before, 'after_loading': after, 'after_download': completed,
                'jobs': control['jobs']})

        for check in (preview_keyboard_completion_returns_to_update_and_exact_stl,
                      stop_preview_returns_to_update_before_late_reply,
                      input_submission_keeps_field_and_stop_returns_to_it,
                      custom_cad_returns_to_download_and_reuses_verified_zip,
                      original_cad_refresh_keeps_focus_through_both_requests,
                      failed_requests_restore_keyboard_retry_controls,
                      completion_preserves_focus_moved_to_a_field,
                      deadlines_restore_keyboard_focus,
                      mobile_stop_is_visible_and_navigation_keeps_library_focus,
                      delayed_viewer_keeps_stop_and_download_visible_on_phone,
                      delayed_viewer_keeps_stop_and_download_visible_on_short_phone,
                      delayed_viewer_keeps_stop_and_download_visible_on_small_phone,
                      delayed_viewer_keeps_stop_and_download_visible_on_short_desktop,
                      delayed_viewer_and_cad_preserve_focus_moved_to_measurement):
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
                for route in pending_viewers.pop(page, []):
                    route.abort()
                page.close()
        browser.close()
    report = {'base': BASE, 'passed': passed, 'failures': failures, 'wait_deadline_ms': WAIT_MS,
              'transport': 'compiled assets, keyboard events and real CAD fixtures',
              'delayed_viewer_cases': delayed_viewer_cases}
    (ROOT / 'review/cloud_build_focus_validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    sys.exit(bool(failures))


if __name__ == '__main__':
    main()
