"""Verify receipt and verification feedback using real CAD files and delayed readers."""
import json
import os
from pathlib import Path
import sys
import traceback

from playwright.sync_api import expect, sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = '--offline' in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5178')
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))

DELAYS = r"""window.progressFault = null;
window.progressStats = [];
window.pauseFileHash = false;
const realFetch = window.fetch;
window.fetch = async (...args) => {
  const response = await realFetch(...args);
  const url = String(args[0]);
  const target = url.includes('/api/generate')
    ? (JSON.parse(args[1].body).format === 'cad' ? 'cad' : 'preview')
    : (/\/models\/[^/]+\.stl$/.test(url) ? 'original' : null);
  const fault = window.progressFault;
  if (!fault || target !== fault.target) return response;
  window.progressFault = null;
  if (fault.headersDelay) await new Promise(resolve => setTimeout(resolve, fault.headersDelay));
  const bytes = new Uint8Array(await response.arrayBuffer());
  const prefix = Math.min(fault.prefix || 1024, bytes.length);
  const stats = { target, length: bytes.length, prefix, reads: 0, cancelled: 0, released: false };
  window.progressStats.push(stats);
  const wait = () => new Promise(resolve => { stats.release = resolve; });
  Object.defineProperty(response, 'body', { value: { getReader: () => ({
    read: async () => {
      stats.reads++;
      if (stats.reads === 1) {
        if (fault.zero) await wait();
        return { done: false, value: bytes.slice(0, prefix) };
      }
      if (stats.reads === 2) {
        if (!fault.zero) await wait();
        return { done: false, value: bytes.slice(prefix) };
      }
      return { done: true };
    },
    cancel: () => { stats.cancelled++; return fault.neverCancel ? new Promise(() => {}) : Promise.resolve(); },
    releaseLock: () => { stats.released = true; }
  }) } });
  Object.defineProperty(response, 'headers', { value: new Headers(response.headers) });
  response.headers.set('Content-Length', '1');
  response.arrayBuffer = () => { throw new Error('The app skipped the streamed reader'); };
  return response;
};
const realDigest = crypto.subtle.digest.bind(crypto.subtle);
crypto.subtle.digest = async (...args) => {
  if (window.pauseFileHash) {
    window.pauseFileHash = false;
    await new Promise(resolve => { window.releaseFileHash = resolve; });
  }
  return realDigest(...args);
};"""


def main():
    original, custom = fixture('parts_tray_original'), fixture('parts_tray')
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1080}, accept_downloads=True)
        context.set_default_timeout(20000)
        if OFFLINE:
            attach_assets(context)

        def setup(page, open_model=True):
            page.add_init_script(DELAYS)
            jobs, problems = [], {}

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload)
                target = 'cad' if payload.get('format') == 'cad' else 'preview'
                problem = problems.pop(target, None)
                if problem:
                    route.fulfill(status=503, body=problem, content_type='application/json')
                    return
                archive, metadata, mesh = custom if payload['parameters']['length'] == 180.5 else original
                if target == 'cad':
                    route.fulfill(body=archive, headers=headers(metadata))
                else:
                    value = {**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}
                    route.fulfill(body=mesh, headers=headers(value, 'model/stl'))

            page.route('**/api/generate', generate)
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            if open_model:
                page.locator('[data-model="parts_tray"]').click()
                ready(page)
            return jobs, problems

        def ready(page):
            page.wait_for_function("() => !document.querySelector('#download-cad').disabled")
            expect(page.locator('#transfer-status')).to_be_hidden()

        def fault(page, target, **options):
            page.evaluate('''value => {
                window.progressExpected = window.progressStats.length;
                window.progressFault = value;
            }''', dict(target=target, **options))

        def waiting(page):
            page.wait_for_function("() => typeof window.progressStats[window.progressExpected]?.release === 'function'")
            return page.evaluate('window.progressExpected')

        def release(page, index):
            page.evaluate('index => window.progressStats[index].release()', index)
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')

        def build(page):
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()

        def custom_preview(page):
            build(page)
            ready(page)

        def download(page, button='download'):
            with page.expect_download() as event:
                page.locator('#' + button).click()
            return Path(event.value.path()).read_bytes()

        def finish_cad(page, index):
            with page.expect_download() as event:
                release(page, index)
            ready(page)
            assert Path(event.value.path()).read_bytes() == custom[0]

        def hash_waiting(page, label):
            page.wait_for_function("() => typeof window.releaseFileHash === 'function'")
            expect(page.locator('#transfer-status')).to_have_text('Verifying ' + label + '…')

        def original_receipt_keeps_saved_confirmation(page):
            jobs, _ = setup(page)
            fault(page, 'original')
            page.locator('.saved-dimensions summary').click()
            with page.expect_file_chooser() as event:
                page.locator('#load-dimensions').click()
            record = {'model': 'cable_comb', 'units': 'mm', 'parameters': {'depth': 40}}
            event.value.set_files({'name': 'parameters.json', 'mimeType': 'application/json', 'buffer': json.dumps(record).encode('utf-8')})
            index = waiting(page)
            expect(page.locator('#transfer-status')).to_have_text('Receiving original preview… 1.0 KiB received')
            expect(page.locator('#form-message')).to_contain_text('Saved dimensions loaded.')
            expect(page.locator('#parameter-fields input').first).to_be_focused()
            release(page, index)
            expect(page.locator('#transfer-status')).to_be_hidden()
            expect(page.locator('#form-message')).to_contain_text('Saved dimensions loaded.')
            assert page.locator('#param-depth').input_value() == '40' and page.locator('#download').is_disabled()
            assert not jobs

        def preview_receipt_counts_bytes_and_retains_exact_mesh(page):
            setup(page)
            fault(page, 'preview')
            build(page)
            index = waiting(page)
            expect(page.locator('#transfer-status')).to_have_text('Receiving preview file… 1.0 KiB received')
            expect(page.locator('#form-message')).to_have_text('Receiving your preview file…')
            assert page.locator('#download').is_disabled() and page.locator('#download-cad').is_disabled()
            release(page, index)
            ready(page)
            assert download(page) == custom[2]

        def cad_receipt_and_cache_keep_verified_files(page):
            jobs, _ = setup(page)
            custom_preview(page)
            fault(page, 'cad')
            page.locator('#download-cad').click()
            index = waiting(page)
            expect(page.locator('#transfer-status')).to_have_text('Receiving CAD download… 1.0 KiB received')
            expect(page.locator('#download-cad')).to_have_text('Receiving CAD files…')
            finish_cad(page, index)
            count = len(jobs)
            assert download(page, 'download-cad') == custom[0] and len(jobs) == count
            expect(page.locator('#transfer-status')).to_be_hidden()

        def valid_headers_show_zero_bytes_before_first_chunk(page):
            setup(page)
            fault(page, 'preview', zero=True)
            build(page)
            index = waiting(page)
            expect(page.locator('#transfer-status')).to_have_text('Receiving preview file… 0 B received')
            assert page.locator('#stop-build').is_visible()
            release(page, index)
            ready(page)

        def preview_verification_blocks_download_until_hash_matches(page):
            setup(page)
            page.evaluate('window.pauseFileHash = true')
            build(page)
            hash_waiting(page, 'preview file')
            assert page.locator('#download').is_disabled() and page.locator('#download-cad').is_disabled()
            page.evaluate('window.releaseFileHash()')
            ready(page)
            assert download(page) == custom[2]

        def cad_verification_blocks_delivery_until_hash_matches(page):
            setup(page)
            custom_preview(page)
            deliveries = []
            page.on('download', lambda item: deliveries.append(item))
            page.evaluate('window.pauseFileHash = true')
            page.locator('#download-cad').click()
            hash_waiting(page, 'CAD download')
            expect(page.locator('#download-cad')).to_have_text('Verifying CAD files…')
            assert not deliveries and page.locator('#download').is_disabled()
            with page.expect_download() as event:
                page.evaluate('window.releaseFileHash()')
            ready(page)
            assert Path(event.value.path()).read_bytes() == custom[0]

        def original_verification_preserves_rejected_file_feedback(page):
            setup(page, open_model=False)
            page.evaluate('window.pauseFileHash = true')
            page.locator('[data-model="parts_tray"]').click()
            hash_waiting(page, 'original preview')
            page.locator('.saved-dimensions summary').click()
            with page.expect_file_chooser() as event:
                page.locator('#load-dimensions').click()
            event.value.set_files({'name': 'bad.json', 'mimeType': 'application/json', 'buffer': b'{broken'})
            expect(page.locator('#dimensions-error')).to_be_visible()
            before = page.locator('#form-message').inner_text()
            page.evaluate('window.releaseFileHash()')
            ready(page)
            assert page.locator('#form-message').inner_text() == before

        def stopped_old_bytes_cannot_hide_new_transfer(page):
            setup(page)
            fault(page, 'preview', neverCancel=True)
            build(page)
            old = waiting(page)
            page.locator('#stop-build').click()
            expect(page.locator('#transfer-status')).to_be_hidden()
            fault(page, 'preview', prefix=2048)
            build(page)
            current = waiting(page)
            release(page, old)
            expect(page.locator('#transfer-status')).to_have_text('Receiving preview file… 2.0 KiB received')
            assert page.locator('#rebuild').is_disabled()
            release(page, current)
            ready(page)
            assert download(page) == custom[2]

        def model_switch_discards_old_progress(page):
            setup(page)
            fault(page, 'preview')
            build(page)
            old = waiting(page)
            page.locator('#close-editor').click()
            expect(page.locator('#editor')).to_be_hidden()
            fault(page, 'original', prefix=2048)
            page.locator('[data-model="cable_comb"]').click()
            current = waiting(page)
            release(page, old)
            expect(page.locator('#transfer-status')).to_have_text('Receiving original preview… 2.0 KiB received')
            release(page, current)
            ready(page)
            assert download(page) == (CLOUD / 'public/models/cable_comb.stl').read_bytes()

        def original_retry_keeps_only_current_progress(page):
            jobs, _ = setup(page, open_model=False)
            fault(page, 'original')
            page.locator('[data-model="parts_tray"]').click()
            old = waiting(page)
            fault(page, 'original', prefix=2048, headersDelay=100)
            page.locator('#retry-original').click()
            current = waiting(page)
            assert current != old
            release(page, old)
            expect(page.locator('#transfer-status')).to_have_text('Receiving original preview… 2.0 KiB received')
            release(page, current)
            ready(page)
            assert not jobs

        def build_reminders_cannot_overwrite_receiving_phases(page):
            page.clock.install()
            setup(page)
            fault(page, 'preview')
            build(page)
            index = waiting(page)
            before = page.locator('#form-message').inner_text()
            page.clock.fast_forward(16000)
            assert page.locator('#form-message').inner_text() == before == 'Receiving your preview file…'
            release(page, index)
            ready(page)
            fault(page, 'cad', headersDelay=100)
            page.locator('#download-cad').click()
            index = waiting(page)
            page.clock.fast_forward(16000)
            expect(page.locator('#form-message')).to_have_text('Receiving your CAD download…')
            finish_cad(page, index)

        def deadline_clears_progress_and_allows_retry(page):
            page.clock.install()
            setup(page)
            fault(page, 'preview', neverCancel=True)
            build(page)
            index = waiting(page)
            page.clock.fast_forward(15 * 60 * 1000 + 1)
            expect(page.locator('#transfer-status')).to_be_hidden()
            expect(page.locator('#form-message')).to_contain_text('15 minutes')
            assert page.locator('#rebuild').is_enabled()
            release(page, index)
            expect(page.locator('#transfer-status')).to_be_hidden()
            build(page)
            ready(page)

        def failed_service_details_never_become_file_progress(page):
            page.clock.install()
            _, problems = setup(page)
            problems['preview'] = '{"error":"Delayed service detail"}'
            fault(page, 'preview')
            build(page)
            waiting(page)
            expect(page.locator('#form-message')).to_contain_text('Reading service details')
            expect(page.locator('#transfer-status')).to_be_hidden()
            page.clock.fast_forward(5001)
            expect(page.locator('#transfer-status')).to_be_hidden()
            assert page.locator('#rebuild').is_enabled()

        def edits_during_receipt_stay_gated_after_verification(page):
            setup(page)
            fault(page, 'preview')
            build(page)
            index = waiting(page)
            page.locator('#param-length').fill('190.5')
            release(page, index)
            page.wait_for_function("() => !document.querySelector('#rebuild').disabled")
            expect(page.locator('#transfer-status')).to_be_hidden()
            assert page.locator('#download').is_disabled() and page.locator('#download-cad').is_disabled()
            assert page.locator('#param-length').input_value() == '190.5'
            page.locator('#revert-parameters').click()
            assert download(page) == custom[2]

        def mobile_progress_is_accessible_and_stop_clears_it(page):
            page.set_viewport_size({'width': 390, 'height': 844})
            setup(page)
            fault(page, 'cad')
            custom_preview(page)
            page.locator('#download-cad').click()
            waiting(page)
            status = page.locator('#transfer-status')
            expect(status).to_have_attribute('role', 'status')
            expect(status).to_have_attribute('aria-live', 'polite')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            status.scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / 'review/cloud_transfer_progress_mobile.png'))
            stop = page.locator('#stop-build')
            assert stop.bounding_box()['height'] >= 44
            stop.focus()
            stop.press('Enter')
            expect(status).to_be_hidden()
            assert download(page) == custom[2]

        for check in (
            original_receipt_keeps_saved_confirmation,
            preview_receipt_counts_bytes_and_retains_exact_mesh,
            cad_receipt_and_cache_keep_verified_files,
            valid_headers_show_zero_bytes_before_first_chunk,
            preview_verification_blocks_download_until_hash_matches,
            cad_verification_blocks_delivery_until_hash_matches,
            original_verification_preserves_rejected_file_feedback,
            stopped_old_bytes_cannot_hide_new_transfer,
            model_switch_discards_old_progress,
            original_retry_keeps_only_current_progress,
            build_reminders_cannot_overwrite_receiving_phases,
            deadline_clears_progress_and_allows_retry,
            failed_service_details_never_become_file_progress,
            edits_during_receipt_stay_gated_after_verification,
            mobile_progress_is_accessible_and_stop_clears_it,
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
              'transport': 'compiled assets, real CAD payloads, deliberately delayed readers and hashes'}
    (ROOT / 'review/cloud_transfer_progress_validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    sys.exit(bool(failures))


if __name__ == '__main__':
    main()
