"""Verify printer profiles shared by real tabs without changing model work."""
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
KEY = 'everydayPrints.printerVolume'
AXES = ('width', 'depth', 'height')
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))
sys.stdout.reconfigure(encoding='utf-8')
EVENTS = """window.printerEvents = 0; window.printerWrites = 0; window.allStorageEvents = 0;
addEventListener('storage', event => {
  window.allStorageEvents++;
  if (event.storageArea === localStorage && (event.key === 'everydayPrints.printerVolume' || event.key === null)) window.printerEvents++;
});
for (const name of ['setItem', 'removeItem']) {
  const original = Storage.prototype[name];
  Storage.prototype[name] = function(key, ...args) {
    if (this === localStorage && key === 'everydayPrints.printerVolume') window.printerWrites++;
    return original.call(this, key, ...args);
  };
}"""
HOLD = """window.releasePrinterOriginal = null; window.releasePrinterBuild = null;
window.holdPrinterOriginal = false; window.holdPrinterBuild = false;
const realFetch = window.fetch;
window.fetch = async (...args) => {
  const response = await realFetch(...args);
  const url = String(args[0]);
  if (url.endsWith('/models/parts_tray.stl') && window.holdPrinterOriginal)
    await new Promise(resolve => window.releasePrinterOriginal = resolve);
  if (url.includes('/api/generate') && window.holdPrinterBuild)
    await new Promise(resolve => window.releasePrinterBuild = resolve);
  return response;
};"""


def main():
    archive, metadata, mesh = fixture('parts_tray')
    preview = {**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}
    catalog = {item['name']: item for item in json.loads((CLOUD / 'public/catalog.json').read_text(encoding='utf-8'))['models']}
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])

        def open_tray(page, wait=True):
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            page.locator('[data-model="parts_tray"]').click()
            if wait:
                expect(page.locator('#download-cad')).to_be_enabled()
            page.locator('#printer-check summary').click()

        def setup(page, wait=True):
            peer = page.context.new_page()
            peer.goto(BASE + '/favicon.svg')
            peer.evaluate('args => localStorage.setItem(...args)', [KEY, '[200,200,30]'])
            peer.goto(BASE)
            open_tray(peer)
            page.add_init_script(EVENTS)
            jobs = []

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload)
                assert payload['model'] == metadata['model'] and payload['parameters'] == metadata['parameters'], payload
                if payload.get('format') == 'cad':
                    route.fulfill(body=archive, headers=headers(metadata))
                else:
                    route.fulfill(body=mesh, headers=headers(preview, 'model/stl'))

            page.route('**/api/generate', generate)
            page.goto(BASE)
            open_tray(page, wait)
            return peer, jobs

        def settle(page, count):
            page.wait_for_function('count => window.printerEvents >= count', arg=count)
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')

        def raw_update(page, peer, raw):
            before = page.evaluate('window.printerEvents')
            peer.evaluate('args => args[1] === null ? localStorage.removeItem(args[0]) : localStorage.setItem(...args)', [KEY, raw])
            settle(page, before + 1)

        def update(page, peer, values):
            raw_update(page, peer, json.dumps(values))

        def values(page):
            return [page.locator('#printer-' + axis).input_value() for axis in AXES]

        def volume(page, expected):
            for axis, value in zip(AXES, expected):
                expect(page.locator('#printer-' + axis)).to_have_value(str(value))

        def fit(page, kind):
            expect(page.locator('#printer-fit-result')).to_have_attribute('data-fit', kind)

        def snapshot(page):
            return page.evaluate("""() => ({
              url: location.href, history: history.state,
              fields: [...document.querySelectorAll('#parameter-fields input')].map(el => [el.id, el.value, el.getAttribute('aria-invalid')]),
              feedback: ['form-message', 'model-size', 'version-name', 'version-message', 'versions-sync-message', 'version-backup-message', 'dimensions-error'].map(id => {
                const el = document.getElementById(id); return [id, el.value ?? el.textContent, el.hidden, el.className];
              }),
              controls: ['download', 'download-cad', 'rebuild', 'stop-build', 'undo-version'].map(id => {
                const el = document.getElementById(id); return [id, el.disabled, el.hidden];
              })
            })""")

        def download(page, button='download'):
            with page.expect_download() as event:
                page.locator('#' + button).click()
            return event.value.suggested_filename, Path(event.value.path()).read_bytes()

        def idle_tabs_follow_real_ui_edits_clear_and_exact_original_files(page):
            peer, jobs = setup(page)
            original = download(page)
            before = snapshot(page)
            count = page.evaluate('window.printerEvents')
            peer.locator('#printer-width').fill('80')
            settle(page, count + 1)
            volume(page, [80, 200, 30])
            fit(page, 'large')
            update(page, peer, [100, 150, 24])
            fit(page, 'rotate')
            update(page, peer, [150, 100, 24])
            fit(page, 'fits')
            count = page.evaluate('window.printerEvents')
            peer.locator('#clear-printer').click()
            settle(page, count + 1)
            assert values(page) == ['', '', '']
            fit(page, '')
            update(page, peer, [185, 110, 30])
            count = page.evaluate('window.printerEvents')
            peer.evaluate('localStorage.clear()')
            settle(page, count + 1)
            assert values(page) == ['', '', '']
            assert snapshot(page) == before
            assert download(page) == original and not jobs
            assert page.evaluate('window.printerWrites') == 0

        def focused_entries_keep_raw_text_and_manual_apply_reads_fresh_settings(page):
            peer, jobs = setup(page)
            page.locator('#printer-width').fill('200.00')
            page.evaluate("window.printerInput = document.getElementById('printer-width')")
            update(page, peer, [185, 110, 30])
            expect(page.locator('#printer-width')).to_be_focused()
            assert values(page) == ['200.00', '200', '30']
            assert page.evaluate("window.printerInput === document.getElementById('printer-width')")
            expect(page.locator('#printer-sync-message')).to_contain_text('Current entries are kept')
            notice = page.locator('#printer-sync-message').inner_text()
            raw_update(page, peer, '[185.0,110,30]')
            assert page.locator('#printer-sync-message').inner_text() == notice
            expect(page.locator('#printer-width')).to_be_focused()
            page.evaluate('args => localStorage.setItem(...args)', [KEY, '[100,185,24]'])
            page.locator('#apply-printer-volume').focus()
            page.keyboard.press('Enter')
            volume(page, [100, 185, 24])
            fit(page, 'rotate')
            expect(page.locator('#printer-width')).to_be_focused()
            expect(page.locator('#apply-printer-volume')).to_be_hidden()
            raw_update(page, peer, None)
            volume(page, [100, 185, 24])
            expect(page.locator('#apply-printer-volume')).to_be_visible()
            page.locator('#apply-printer-volume').focus()
            page.keyboard.press('Enter')
            assert values(page) == ['', '', '']
            expect(page.locator('#printer-width')).to_be_focused()
            fit(page, '')
            assert not jobs

        def incomplete_invalid_drafts_survive_then_local_save_or_clear_resolves_notice(page):
            peer, jobs = setup(page)
            page.locator('#printer-height').fill('')
            page.locator('#param-length').focus()
            update(page, peer, [160, 110, 30])
            assert values(page) == ['200', '200', '']
            expect(page.locator('#param-length')).to_be_focused()
            expect(page.locator('#apply-printer-volume')).to_be_visible()
            page.locator('#printer-height').fill('30')
            expect(page.locator('#printer-sync-message')).to_be_hidden()
            volume(peer, [200, 200, 30])
            page.locator('#printer-width').fill('0')
            page.locator('#param-length').focus()
            update(page, peer, [170, 120, 30])
            expect(page.locator('#printer-width')).to_have_value('0')
            expect(page.locator('#printer-width')).to_have_attribute('aria-invalid', 'true')
            fit(page, '')
            page.locator('#clear-printer').click()
            expect(page.locator('#printer-sync-message')).to_be_hidden()
            assert values(page) == ['', '', ''] and not jobs
            for axis in AXES:
                expect(peer.locator('#printer-' + axis)).to_have_value('')

        def unrelated_session_and_canonical_noop_events_preserve_feedback_and_formatting(page):
            peer, _ = setup(page)
            page.locator('#param-length').fill('')
            page.evaluate("document.getElementById('printer-width').value = '200.00'")
            before = snapshot(page)
            count = page.evaluate('window.allStorageEvents')
            peer.evaluate("localStorage.setItem('unrelated-setting', 'changed')")
            page.wait_for_function('n => window.allStorageEvents > n', arg=count)
            page.evaluate("""key => {
              dispatchEvent(new StorageEvent('storage', {key, storageArea: sessionStorage, newValue: 'broken'}));
              dispatchEvent(new StorageEvent('storage', {key, storageArea: localStorage, newValue: 'obsolete'}));
            }""", KEY)
            raw_update(page, peer, '[200.0,200,30]')
            assert snapshot(page) == before and values(page) == ['200.00', '200', '30']
            expect(page.locator('#param-length')).to_be_focused()
            expect(page.locator('#printer-sync-message')).to_be_hidden()
            assert page.evaluate('window.printerWrites') == 0

        def queued_events_and_obsolete_payloads_use_current_storage(page):
            peer, _ = setup(page)
            count = page.evaluate('window.printerEvents')
            peer.evaluate("""args => {
              localStorage.setItem(args[0], '[100,150,24]');
              localStorage.setItem(args[0], '[185,110,30]');
            }""", [KEY])
            settle(page, count + 2)
            volume(page, [185, 110, 30])
            page.evaluate("""key => {
              localStorage.setItem(key, '[80,80,20]');
              dispatchEvent(new StorageEvent('storage', {key, storageArea: localStorage, newValue: '[200,200,30]'}));
            }""", KEY)
            volume(page, [80, 80, 20])
            fit(page, 'large')

        def corrupt_oversized_denied_reads_keep_data_and_recover_without_writes(page):
            peer, _ = setup(page)
            before = snapshot(page)
            page.locator('#param-length').focus()
            for raw in ('broken', 'x' * 257, '[200,200,0]'):
                raw_update(page, peer, raw)
                expect(page.locator('#printer-sync-message')).to_have_class('printer-note error')
                volume(page, [200, 200, 30])
                assert peer.evaluate('key => localStorage.getItem(key)', KEY) == raw
                assert snapshot(page) == before
            page.locator('#apply-printer-volume').click()
            expect(page.locator('#printer-sync-message')).to_contain_text('could not be read')
            expect(page.locator('#apply-printer-volume')).to_be_focused()
            page.evaluate("""key => {
              const read = Storage.prototype.getItem;
              window.restorePrinterRead = () => { Storage.prototype.getItem = read; };
              Storage.prototype.getItem = function(name) {
                if (this === localStorage && name === key) throw new DOMException('Denied', 'SecurityError');
                return read.call(this, name);
              };
            }""", KEY)
            update(page, peer, [185, 110, 30])
            expect(page.locator('#printer-sync-message')).to_contain_text('unavailable')
            page.locator('#apply-printer-volume').click()
            volume(page, [200, 200, 30])
            page.evaluate('window.restorePrinterRead()')
            page.locator('#apply-printer-volume').click()
            volume(page, [185, 110, 30])
            page.locator('#param-length').focus()
            raw_update(page, peer, 'broken again')
            update(page, peer, [185, 110, 30])
            expect(page.locator('#printer-sync-message')).to_contain_text('available again')
            expect(page.locator('#apply-printer-volume')).to_be_hidden()
            assert page.evaluate('window.printerWrites') == 0 and snapshot(page) == before

        def failed_local_saves_keep_deferred_notice_and_saved_profile_apply_needs_no_write(page):
            peer, _ = setup(page)
            page.locator('#printer-width').focus()
            update(page, peer, [160, 110, 30])
            page.evaluate("""key => {
              const saved = {};
              for (const name of ['setItem', 'removeItem']) {
                saved[name] = Storage.prototype[name];
                Storage.prototype[name] = function(item, ...args) {
                  if (this === localStorage && item === key) throw new DOMException('Full', 'QuotaExceededError');
                  return saved[name].call(this, item, ...args);
                };
              }
              window.restorePrinterWrites = () => Object.assign(Storage.prototype, saved);
            }""", KEY)
            page.locator('#printer-width').fill('201')
            volume(page, [201, 200, 30])
            expect(page.locator('#printer-profile-note')).to_contain_text('while this page is open')
            expect(page.locator('#apply-printer-volume')).to_be_visible()
            assert json.loads(peer.evaluate('key => localStorage.getItem(key)', KEY)) == [160, 110, 30]
            page.locator('#apply-printer-volume').click()
            volume(page, [160, 110, 30])
            expect(page.locator('#printer-sync-message')).to_contain_text('applied')
            page.locator('#clear-printer').click()
            assert values(page) == ['', '', '']
            assert json.loads(peer.evaluate('key => localStorage.getItem(key)', KEY)) == [160, 110, 30]
            page.evaluate('window.restorePrinterWrites()')
            page.locator('#printer-width').fill('185')
            page.locator('#printer-depth').fill('110')
            page.locator('#printer-height').fill('30')
            expect(page.locator('#printer-sync-message')).to_be_hidden()
            volume(peer, [185, 110, 30])

        def active_preview_and_cached_cad_keep_progress_focus_mesh_and_filenames(page):
            page.add_init_script(HOLD)
            peer, jobs = setup(page)
            page.evaluate('window.holdPrinterBuild = true')
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').focus()
            page.keyboard.press('Enter')
            page.wait_for_function('() => window.releasePrinterBuild !== null')
            expect(page.locator('#stop-build')).to_be_focused()
            before = snapshot(page)
            update(page, peer, [160, 110, 30])
            expect(page.locator('#stop-build')).to_be_focused()
            assert snapshot(page) == before
            fit(page, 'fits')
            expect(page.locator('#printer-preview-note')).to_be_visible()
            page.evaluate('() => { window.holdPrinterBuild = false; window.releasePrinterBuild(); }')
            expect(page.locator('#download')).to_be_enabled()
            fit(page, 'large')
            stl = download(page)
            cad = download(page, 'download-cad')
            assert stl[1] == mesh and '-180.5x100x24mm-' in stl[0]
            assert cad[1] == archive and '-180.5x100x24mm-' in cad[0]
            update(page, peer, [100, 185, 24])
            fit(page, 'rotate')
            assert download(page) == stl and download(page, 'download-cad') == cad and len(jobs) == 2

        def late_original_preview_and_stopped_build_follow_latest_profile_only(page):
            page.add_init_script(HOLD + '\nwindow.holdPrinterOriginal = true;')
            peer, jobs = setup(page, wait=False)
            page.wait_for_function('() => window.releasePrinterOriginal !== null')
            update(page, peer, [160, 110, 30])
            fit(page, '')
            expect(page.locator('#printer-fit-result')).to_contain_text('Waiting for a verified STL')
            page.evaluate('window.releasePrinterOriginal()')
            expect(page.locator('#download')).to_be_enabled()
            fit(page, 'fits')
            original = download(page)
            page.evaluate('window.holdPrinterBuild = true')
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            page.wait_for_function('() => window.releasePrinterBuild !== null')
            update(page, peer, [100, 150, 24])
            page.locator('#stop-build').click()
            before = snapshot(page)
            page.evaluate('window.releasePrinterBuild()')
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            assert snapshot(page) == before
            fit(page, 'rotate')
            page.locator('#revert-parameters').click()
            assert download(page) == original and len(jobs) == 1

        def version_undo_typed_names_and_model_errors_stay_independent(page):
            peer, jobs = setup(page)
            page.locator('.saved-dimensions > summary').click()
            page.locator('#version-name').fill('Original')
            page.locator('#save-version').click()
            page.locator('#version-name').fill('Revised')
            page.locator('#rename-version').click()
            expect(page.locator('#undo-version')).to_be_enabled()
            page.locator('#param-length').fill('')
            page.locator('#version-name').fill('Unsaved name')
            before = snapshot(page)
            saved = page.evaluate("localStorage.getItem('everyday-prints-versions')")
            update(page, peer, [80, 80, 20])
            assert snapshot(page) == before
            assert page.evaluate("localStorage.getItem('everyday-prints-versions')") == saved
            expect(page.locator('#version-name')).to_be_focused()
            page.locator('#undo-version').click()
            expect(page.locator('#version-choice option').filter(has_text='Original')).to_have_count(1)
            expect(page.locator('#param-length')).to_have_value('')
            assert not jobs

        def early_catalog_closed_editor_history_refresh_and_assemblies_use_current_profile(page):
            page.add_init_script(EVENTS)
            waiting = []
            page.route('**/catalog.json', lambda route: waiting.append(route))
            page.goto(BASE)
            page.wait_for_function("() => !document.getElementById('catalog-loading').hidden")
            while not waiting:
                page.wait_for_timeout(20)
            peer = page.context.new_page()
            peer.goto(BASE + '/favicon.svg')
            update(page, peer, [185, 110, 30])
            volume(page, [185, 110, 30])
            waiting[0].fulfill(path=str(CLOUD / '.cloudflare/output/v0/workers/default/assets/catalog.json'), content_type='application/json')
            page.unroute('**/catalog.json')
            open_tray(page)
            fit(page, 'fits')
            page.locator('#close-editor').click()
            page.locator('#search').focus()
            update(page, peer, [100, 150, 24])
            expect(page.locator('#search')).to_be_focused()
            page.locator('[data-model="parts_tray"]').click()
            fit(page, 'rotate')
            cable = dict(model='cable_comb', units='mm', parameters=catalog['cable_comb']['defaults'])
            page.locator('#dimensions-file').set_input_files(dict(name='cable.json', mimeType='application/json', buffer=json.dumps(cable).encode()))
            expect(page.locator('#model-title')).to_have_text(catalog['cable_comb']['title'])
            update(page, peer, [200, 200, 30])
            page.go_back()
            expect(page.locator('#model-title')).to_have_text(catalog['parts_tray']['title'])
            volume(page, [200, 200, 30])
            page.reload()
            expect(page.locator('#download')).to_be_enabled()
            volume(page, [200, 200, 30])
            page.locator('#close-editor').click()
            page.locator('[data-model="soap_dish_assembly"]').click()
            page.locator('#printer-check summary').click()
            update(page, peer, [300, 300, 300])
            expect(page.locator('#printer-fit-result')).to_contain_text('Reference assembly')
            expect(page.locator('#printer-mesh-size')).to_be_hidden()
            page.locator('#part-links button').first.click()
            fit(page, 'fits')

        def mobile_desktop_keyboard_apply_is_bounded_accessible_and_keeps_files(page):
            peer, jobs = setup(page)
            original = download(page)
            page.set_viewport_size(dict(width=390, height=844))
            page.locator('#printer-width').focus()
            update(page, peer, [100, 150, 24])
            page.locator('#apply-printer-volume').scroll_into_view_if_needed()
            for control in ('printer-width', 'printer-depth', 'printer-height', 'apply-printer-volume'):
                box = page.locator('#' + control).bounding_box()
                assert box and box['width'] >= 44 and box['height'] >= 44, (control, box)
            for axis in AXES:
                assert 'printer-sync-message' in page.locator('#printer-' + axis).get_attribute('aria-describedby').split()
            expect(page.locator('#printer-sync-message')).to_have_attribute('role', 'status')
            expect(page.locator('#printer-sync-message')).to_have_attribute('aria-live', 'polite')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('#editor').evaluate('(el) => el.scrollWidth <= el.clientWidth')
            page.screenshot(path=str(ROOT / 'review/cloud_printer_sync_mobile.png'))
            page.set_viewport_size(dict(width=1440, height=1080))
            page.locator('#apply-printer-volume').scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / 'review/cloud_printer_sync_desktop.png'))
            page.set_viewport_size(dict(width=390, height=844))
            page.locator('#apply-printer-volume').focus()
            page.keyboard.press('Enter')
            expect(page.locator('#printer-width')).to_be_focused()
            volume(page, [100, 150, 24])
            box = page.locator('#printer-width').bounding_box()
            layout = page.locator('.editor-layout').bounding_box()
            assert box and layout and box['y'] >= layout['y'] and box['y'] + box['height'] <= 844, (box, layout)
            fit(page, 'rotate')
            assert download(page) == original and not jobs

        def peer_barrier(page, peer):
            peer.evaluate("""() => {
              if (window.printerEditCheckpoints !== undefined) return;
              window.printerEditCheckpoints = 0;
              addEventListener('storage', event => {
                if (event.key === 'everydayPrints.printerEditCheckpoint') window.printerEditCheckpoints++;
              });
            }""")
            count = peer.evaluate('window.printerEditCheckpoints')
            page.evaluate("localStorage.setItem('everydayPrints.printerEditCheckpoint', crypto.randomUUID())")
            peer.wait_for_function('count => window.printerEditCheckpoints > count', arg=count)
            peer.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')

        def incomplete_edits_keep_saved_volume_other_tab_and_refresh(page):
            peer, jobs = setup(page)
            original = download(page)
            page.locator('#param-length').fill('')
            before = snapshot(page)
            for value in ('', '0', '-1'):
                page.locator('#printer-width').fill(value)
                peer_barrier(page, peer)
                volume(peer, [200, 200, 30])
                assert json.loads(page.evaluate('key => localStorage.getItem(key)', KEY)) == [200, 200, 30]
                assert page.evaluate('window.printerWrites') == 0 and snapshot(page) == before
                expect(page.locator('#printer-width')).to_have_attribute('aria-invalid', 'true')
                expect(page.locator('#printer-profile-note')).to_contain_text('Complete a positive')
                fit(page, '')
            page.locator('#printer-width').fill('')
            page.locator('#printer-check').scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / 'review/cloud_printer_edit_desktop.png'))
            page.reload()
            expect(page.locator('#param-length')).to_have_value('')
            page.locator('#printer-check summary').click()
            volume(page, [200, 200, 30])
            fit(page, 'fits')
            expect(page.locator('#download')).to_be_disabled()
            page.locator('#revert-parameters').click()
            expect(page.locator('#download')).to_be_enabled()
            assert download(page) == original and not jobs

        def complete_edits_publish_once_and_all_empty_fields_clear(page):
            peer, jobs = setup(page)
            original = download(page)
            before = snapshot(page)
            for axis, value in (('height', ''), ('depth', ''), ('width', '185'), ('depth', '110')):
                page.locator('#printer-' + axis).fill(value)
            peer_barrier(page, peer)
            volume(peer, [200, 200, 30])
            assert page.evaluate('window.printerWrites') == 0
            page.locator('#printer-height').fill('30')
            peer_barrier(page, peer)
            volume(peer, [185, 110, 30])
            assert page.evaluate('window.printerWrites') == 1
            expect(page.locator('#printer-profile-note')).to_contain_text('Build volume saved')
            for axis in ('width', 'depth'):
                page.locator('#printer-' + axis).fill('')
            peer_barrier(page, peer)
            volume(peer, [185, 110, 30])
            assert page.evaluate('window.printerWrites') == 1
            page.locator('#printer-height').fill('')
            peer_barrier(page, peer)
            assert values(page) == values(peer) == ['', '', '']
            assert page.evaluate('key => localStorage.getItem(key)', KEY) is None
            assert page.evaluate('window.printerWrites') == 2
            fit(peer, '')
            for axis, value in zip(AXES, (190, 120, 35)):
                page.locator('#printer-' + axis).fill(str(value))
            peer_barrier(page, peer)
            volume(peer, [190, 120, 35])
            assert page.evaluate('window.printerWrites') == 3 and snapshot(page) == before
            assert download(page) == original and not jobs

        def native_bad_input_keeps_saved_settings_until_explicit_clear(page):
            peer, jobs = setup(page)
            original = download(page)
            page.set_viewport_size(dict(width=390, height=844))
            page.locator('#printer-height').fill('')
            page.locator('#printer-depth').fill('')
            field = page.locator('#printer-width')
            field.press('Control+A')
            field.press_sequentially('1e')
            assert field.evaluate('(el) => el.validity.badInput') and field.input_value() == ''
            peer_barrier(page, peer)
            volume(peer, [200, 200, 30])
            assert json.loads(page.evaluate('key => localStorage.getItem(key)', KEY)) == [200, 200, 30]
            assert page.evaluate('window.printerWrites') == 0
            expect(field).to_have_attribute('aria-invalid', 'true')
            fit(page, '')
            field.scroll_into_view_if_needed()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(ROOT / 'review/cloud_printer_edit_mobile.png'))
            page.locator('#clear-printer').focus()
            page.keyboard.press('Enter')
            peer_barrier(page, peer)
            assert values(page) == values(peer) == ['', '', '']
            assert not field.evaluate('(el) => el.validity.badInput')
            expect(field).to_have_attribute('aria-invalid', 'false')
            expect(field).to_be_focused()
            assert page.evaluate('key => localStorage.getItem(key)', KEY) is None
            assert page.evaluate('window.printerWrites') == 1
            assert download(page) == original and not jobs

        def partial_edits_keep_deferred_settings_build_progress_and_cached_cad(page):
            page.add_init_script(HOLD)
            peer, jobs = setup(page)
            page.locator('#printer-width').fill('')
            page.locator('#param-length').focus()
            count = page.evaluate('window.printerEvents')
            for axis, value in zip(AXES, (160, 110, 30)):
                peer.locator('#printer-' + axis).fill(str(value))
            settle(page, count + 2)
            page.locator('#printer-depth').fill('0')
            peer_barrier(page, peer)
            expect(page.locator('#apply-printer-volume')).to_be_visible()
            expect(page.locator('#printer-sync-message')).to_contain_text('Current entries are kept')
            volume(peer, [160, 110, 30])
            assert page.evaluate('window.printerWrites') == 0
            page.locator('#apply-printer-volume').focus()
            page.keyboard.press('Enter')
            volume(page, [160, 110, 30])
            expect(page.locator('#apply-printer-volume')).to_be_hidden()
            page.evaluate('window.holdPrinterBuild = true')
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            page.wait_for_function("() => typeof window.releasePrinterBuild === 'function'")
            before = snapshot(page)
            page.locator('#printer-height').fill('')
            count = page.evaluate('window.printerEvents')
            peer.locator('#printer-width').fill('185')
            settle(page, count + 1)
            assert values(page) == ['160', '110', '']
            expect(page.locator('#apply-printer-volume')).to_be_visible()
            page.locator('#apply-printer-volume').click()
            assert snapshot(page) == before and page.evaluate('window.printerWrites') == 0
            expect(page.locator('#stop-build')).to_be_visible()
            page.evaluate('window.holdPrinterBuild = false; window.releasePrinterBuild()')
            expect(page.locator('#rebuild')).to_be_enabled()
            assert download(page)[1] == mesh
            cached = download(page, 'download-cad')
            assert cached[1] == archive and len(jobs) == 2
            before = snapshot(page)
            page.locator('#printer-height').fill('0')
            peer_barrier(page, peer)
            volume(peer, [185, 110, 30])
            assert snapshot(page) == before and page.evaluate('window.printerWrites') == 0
            assert download(page, 'download-cad') == cached and len(jobs) == 2

        def local_restore_keeps_invalid_model_drafts_versions_and_cached_files(page):
            peer, jobs = setup(page)
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            expect(page.locator('#rebuild')).to_be_enabled()
            cached = download(page, 'download-cad')
            assert cached[1] == archive and len(jobs) == 2
            page.locator('.saved-dimensions > summary').click()
            page.locator('#version-name').fill('Saved tray')
            page.locator('#save-version').click()
            expect(page.locator('#undo-version')).to_be_visible()
            selected = page.locator('#version-choice').input_value()
            page.locator('#param-length').fill('')
            before = snapshot(page)
            page.locator('#printer-width').fill('')
            expect(page.locator('#apply-printer-volume')).to_be_visible()
            expect(page.locator('#printer-sync-message')).to_contain_text('saved build volume is kept')
            page.locator('#apply-printer-volume').focus()
            page.keyboard.press('Enter')
            volume(page, [200, 200, 30])
            expect(page.locator('#printer-width')).to_be_focused()
            expect(page.locator('#printer-width')).to_have_attribute('aria-invalid', 'false')
            expect(page.locator('#apply-printer-volume')).to_be_hidden()
            assert snapshot(page) == before and page.locator('#version-choice').input_value() == selected
            assert page.evaluate('window.printerWrites') == 0
            peer_barrier(page, peer)
            volume(peer, [200, 200, 30])
            page.locator('#revert-parameters').click()
            assert download(page)[1] == mesh
            assert download(page, 'download-cad') == cached and len(jobs) == 2

        def failed_saves_and_failed_clear_restore_without_a_write(page):
            peer, jobs = setup(page)
            original = download(page)
            before = snapshot(page)
            page.evaluate("""key => {
              window.failedPrinterWrites = 0;
              for (const name of ['setItem', 'removeItem']) {
                const real = Storage.prototype[name];
                Storage.prototype[name] = function(item, ...args) {
                  if (this === localStorage && item === key) {
                    window.failedPrinterWrites++;
                    throw new DOMException('Full', 'QuotaExceededError');
                  }
                  return real.call(this, item, ...args);
                };
              }
            }""", KEY)
            page.locator('#printer-width').fill('210')
            expect(page.locator('#apply-printer-volume')).to_be_visible()
            expect(page.locator('#printer-sync-message')).to_contain_text('Changes could not be saved')
            peer_barrier(page, peer)
            volume(peer, [200, 200, 30])
            page.locator('#printer-check').scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / 'review/cloud_printer_restore_desktop.png'))
            page.locator('#apply-printer-volume').focus()
            page.keyboard.press('Enter')
            volume(page, [200, 200, 30])
            assert page.evaluate('window.failedPrinterWrites') == 1 and snapshot(page) == before
            expect(page.locator('#apply-printer-volume')).to_be_hidden()
            page.locator('#clear-printer').click()
            assert values(page) == ['', '', '']
            expect(page.locator('#apply-printer-volume')).to_be_visible()
            page.locator('#apply-printer-volume').click()
            volume(page, [200, 200, 30])
            assert page.evaluate('window.failedPrinterWrites') == 2 and snapshot(page) == before
            assert json.loads(page.evaluate('key => localStorage.getItem(key)', KEY)) == [200, 200, 30]
            assert download(page) == original and not jobs

        def local_restore_reads_fresh_settings_preserves_read_errors_and_requires_a_saved_profile(page):
            peer, jobs = setup(page)
            original = download(page)
            before = snapshot(page)
            page.locator('#printer-width').fill('0')
            expect(page.locator('#apply-printer-volume')).to_be_visible()
            page.evaluate('args => localStorage.setItem(...args)', [KEY, '[100,185,24]'])
            peer_barrier(page, peer)
            volume(peer, [100, 185, 24])
            page.locator('#apply-printer-volume').click()
            volume(page, [100, 185, 24])
            fit(page, 'rotate')
            assert page.evaluate('window.printerWrites') == 1 and snapshot(page) == before
            page.locator('#printer-height').fill('')
            expect(page.locator('#apply-printer-volume')).to_be_visible()
            page.evaluate('args => localStorage.setItem(...args)', [KEY, 'broken'])
            kept = values(page)
            page.locator('#apply-printer-volume').click()
            expect(page.locator('#printer-sync-message')).to_contain_text('could not be read')
            expect(page.locator('#apply-printer-volume')).to_be_focused()
            assert values(page) == kept
            error = page.locator('#printer-sync-message').inner_text()
            page.locator('#printer-width').fill('0')
            assert page.locator('#printer-sync-message').inner_text() == error
            page.evaluate("""key => {
              window.realPrinterGet = Storage.prototype.getItem;
              Storage.prototype.getItem = function(item) {
                if (this === localStorage && item === key) throw new DOMException('Blocked', 'SecurityError');
                return window.realPrinterGet.call(this, item);
              };
            }""", KEY)
            kept = values(page)
            page.locator('#apply-printer-volume').click()
            expect(page.locator('#printer-sync-message')).to_contain_text('unavailable')
            assert values(page) == kept
            page.evaluate('() => { Storage.prototype.getItem = window.realPrinterGet; }')
            page.evaluate('args => localStorage.setItem(...args)', [KEY, '[185,110,30]'])
            page.locator('#apply-printer-volume').click()
            volume(page, [185, 110, 30])
            assert page.evaluate('window.printerWrites') == 3 and snapshot(page) == before
            expect(page.locator('#apply-printer-volume')).to_be_hidden()
            page.locator('#clear-printer').click()
            page.locator('#printer-width').fill('180')
            expect(page.locator('#apply-printer-volume')).to_be_hidden()
            assert page.evaluate('key => localStorage.getItem(key)', KEY) is None
            assert download(page) == original and not jobs

        def mobile_restore_preserves_pending_work_and_keeps_width_in_view(page):
            page.add_init_script(HOLD)
            peer, jobs = setup(page)
            page.set_viewport_size(dict(width=390, height=844))
            page.evaluate('window.holdPrinterBuild = true')
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            page.wait_for_function("() => typeof window.releasePrinterBuild === 'function'")
            before = snapshot(page)
            page.locator('#printer-height').fill('')
            expect(page.locator('#apply-printer-volume')).to_be_visible()
            expect(page.locator('.view-tools')).to_be_visible()
            page.locator('#printer-check').scroll_into_view_if_needed()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(ROOT / 'review/cloud_printer_restore_mobile.png'))
            page.locator('#apply-printer-volume').focus()
            page.keyboard.press('Enter')
            volume(page, [200, 200, 30])
            expect(page.locator('#printer-width')).to_be_focused()
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            field = page.locator('#printer-width').bounding_box()
            clip = page.locator('.editor-layout').bounding_box()
            assert field and clip and field['y'] >= clip['y'] and field['y'] + field['height'] <= clip['y'] + clip['height'], (field, clip)
            assert snapshot(page) == before and page.evaluate('window.printerWrites') == 0
            expect(page.locator('#stop-build')).to_be_visible()
            peer_barrier(page, peer)
            volume(peer, [200, 200, 30])
            page.evaluate('window.holdPrinterBuild = false; window.releasePrinterBuild()')
            expect(page.locator('#rebuild')).to_be_enabled()
            expect(page.locator('#printer-width')).to_be_focused()
            assert download(page)[1] == mesh and len(jobs) == 1

        tests = (idle_tabs_follow_real_ui_edits_clear_and_exact_original_files,
                 focused_entries_keep_raw_text_and_manual_apply_reads_fresh_settings,
                 incomplete_invalid_drafts_survive_then_local_save_or_clear_resolves_notice,
                 unrelated_session_and_canonical_noop_events_preserve_feedback_and_formatting,
                 queued_events_and_obsolete_payloads_use_current_storage,
                 corrupt_oversized_denied_reads_keep_data_and_recover_without_writes,
                 failed_local_saves_keep_deferred_notice_and_saved_profile_apply_needs_no_write,
                 active_preview_and_cached_cad_keep_progress_focus_mesh_and_filenames,
                 late_original_preview_and_stopped_build_follow_latest_profile_only,
                 version_undo_typed_names_and_model_errors_stay_independent,
                 early_catalog_closed_editor_history_refresh_and_assemblies_use_current_profile,
                 mobile_desktop_keyboard_apply_is_bounded_accessible_and_keeps_files,
                 incomplete_edits_keep_saved_volume_other_tab_and_refresh,
                 complete_edits_publish_once_and_all_empty_fields_clear,
                 native_bad_input_keeps_saved_settings_until_explicit_clear,
                 partial_edits_keep_deferred_settings_build_progress_and_cached_cad,
                 local_restore_keeps_invalid_model_drafts_versions_and_cached_files,
                 failed_saves_and_failed_clear_restore_without_a_write,
                 local_restore_reads_fresh_settings_preserves_read_errors_and_requires_a_saved_profile,
                 mobile_restore_preserves_pending_work_and_keeps_width_in_view)
        for test in tests:
            context = browser.new_context(viewport=dict(width=1440, height=1080), accept_downloads=True)
            context.set_default_timeout(20000)
            errors = []
            context.on('page', lambda page: page.on('pageerror', lambda error: errors.append(str(error))))
            if OFFLINE:
                attach_assets(context)
            page = context.new_page()
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
    report = dict(endpoint=BASE, passed=passed, failures=failures, fixture_mesh_sha256=metadata['mesh_sha256'],
                  transport='real shared-context browser tabs, compiled assets and real CAD fixtures' if OFFLINE else 'local HTTP')
    (ROOT / 'review/cloud_printer_sync_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    assert not failures, report


if __name__ == '__main__':
    main()
