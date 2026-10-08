"""Restore exported version backups by dropping them anywhere in the editor."""
import base64
import copy
import json
import os
from pathlib import Path
import sys
import traceback

from playwright.sync_api import expect, sync_playwright
from browser_assets import ASSETS, OFFLINE_BASE as BASE, attach_assets
from verify_dimension_drop_ui import DROP
from verify_dimensions_ui import FILES
from verify_export_ui import fixture, headers
from verify_version_backups_ui import TIMERS

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
KEY = 'everyday-prints-versions'
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))


def main():
    models = json.loads((ASSETS / 'catalog.json').read_text(encoding='utf-8'))['models']
    catalog = {row['name']: row for row in models}
    fixtures = {name: fixture(name) for name in ['parts_tray', 'cable_comb']}
    passed, failures, cases = [], [], []
    csp = next(line.split(':', 1)[1].strip() for line in (CLOUD / 'public/_headers').read_text().splitlines() if 'Content-Security-Policy:' in line)

    def record(model='parts_tray', name='Wide tray', number=1):
        parameters = fixtures[model][1]['parameters'] if model in fixtures else catalog[model]['defaults']
        return {'id': f'00000000-0000-4000-8000-{number:012x}', 'name': name,
                'dimensions': {'model': model, 'units': 'mm', 'parameters': copy.deepcopy(parameters)}}

    tray, cable = record(), record('cable_comb', 'Routing <wide> ✓', 2)

    def backup(records):
        return json.dumps({'format': 'everyday-prints-versions', 'version': 1,
                           'versions': [{'name': row['name'], 'dimensions': row['dimensions']} for row in records]}, ensure_ascii=False).encode()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])

        def context():
            result = browser.new_context(viewport={'width': 1440, 'height': 1080}, accept_downloads=True)
            result.set_default_timeout(20000)
            attach_assets(result)
            result.route(BASE + '/', lambda route: route.fulfill(body=(ASSETS / 'index.html').read_bytes(), headers={'Content-Type': 'text/html', 'Content-Security-Policy': csp}))
            return result

        def setup(page, records=None):
            page.add_init_script(FILES + TIMERS + '''window.droppedJsonReads=0;
              const scheduleDroppedDeadline=window.setTimeout.bind(window);
              window.setTimeout=(callback,delay,...args)=>{
                const watched=delay===15000&&window.watchVersionReadTimer;
                const id=scheduleDroppedDeadline(callback,delay,...args);
                if(watched)window.fireDroppedDeadline=()=>{window.clearTimeout(id);callback(...args);};
                return id;
              };
              const droppedBytes=File.prototype.arrayBuffer;
              File.prototype.arrayBuffer=function(){window.droppedJsonReads++;return droppedBytes.call(this);};''')
            if records is not None:
                page.add_init_script('localStorage.setItem(' + json.dumps(KEY) + ',' + json.dumps(json.dumps(records)) + ');')
            control = {'jobs': [], 'hold': False, 'waiting': []}

            def generate(route):
                payload = route.request.post_data_json
                control['jobs'].append(payload)
                if control['hold']:
                    control['waiting'].append(route)
                    return
                archive, metadata, mesh = fixtures[payload['model']]
                assert payload['parameters'] == metadata['parameters'], payload
                route.fulfill(body=archive if payload.get('format') == 'cad' else mesh,
                    headers=headers(metadata) if payload.get('format') == 'cad' else
                    headers({**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}, 'model/stl'))

            page.route('**/api/generate', generate)
            page.goto(BASE)
            page.locator('[data-model="parts_tray"]').click()
            expect(page.locator('#download-cad')).to_be_enabled()
            page.locator('.saved-dimensions summary').click()
            return control

        def drop(page, body=backup([cable]), name='version.json', target='#param-length', size=None):
            if name.startswith('slow'):
                page.evaluate('window.watchVersionReadTimer=true')
            file = {'name': name, 'mime': 'application/json', **({'size': size} if size is not None else {'body': base64.b64encode(body).decode()})}
            result = page.evaluate(DROP, {'files': [file], 'event': 'drop', 'target': target, 'text': None, 'related': None})
            assert result['prevented'] and not result['hovering']

        def native_drop(page, path, target):
            page.locator(target).scroll_into_view_if_needed()
            rect = page.locator(target).bounding_box()
            page.evaluate('''()=>{window.trustedVersionDrops=[];document.querySelector('#editor').addEventListener('drop',event=>{
              window.trustedVersionDrops.push({trusted:event.isTrusted,files:[...event.dataTransfer.files].map(file=>file.name)});});}''')
            session = page.context.new_cdp_session(page)
            try:
                data = {'items': [], 'files': [str(path)], 'dragOperationsMask': 1}
                for kind in ['dragEnter', 'dragOver', 'drop']:
                    session.send('Input.dispatchDragEvent', {'type': kind, 'x': rect['x'] + rect['width'] / 2,
                        'y': rect['y'] + rect['height'] / 2, 'data': data})
            finally:
                session.detach()
            expect(page.locator('#version-backup-message')).to_contain_text('Imported')
            events = page.evaluate('window.trustedVersionDrops')
            assert len(events) == 1 and events[0]['trusted'] and events[0]['files'] == [path.name]
            return events

        def download(page, button):
            with page.expect_download() as event:
                page.locator('#' + button).click()
            return event.value.suggested_filename, Path(event.value.path()).read_bytes()

        def stored(page):
            return page.evaluate('key=>localStorage.getItem(key)', KEY)

        def snapshot(page):
            return page.evaluate('''()=>({model:document.querySelector('#model-title').textContent,
              fields:Array.from(document.querySelectorAll('[data-parameter]'),el=>[el.dataset.parameter,el.value,el.getAttribute('aria-invalid')]),
              name:document.querySelector('#version-name').value,message:document.querySelector('#form-message').textContent,
              error:document.querySelector('#dimensions-error').textContent,errorHidden:document.querySelector('#dimensions-error').hidden,
              href:location.href,history:history.length})''')

        def custom(page):
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            expect(page.locator('#download-cad')).to_be_enabled()
            assert download(page, 'download-cad')[1] == fixtures['parts_tray'][0]

        def retained(page, control):
            stl_name, mesh = download(page, 'download')
            cad_name, archive = download(page, 'download-cad')
            assert mesh == fixtures['parts_tray'][2] and archive == fixtures['parts_tray'][0]
            assert '180.5x100x24mm' in stl_name and '180.5x100x24mm' in cad_name
            assert len(control['jobs']) == 2

        def native_selected_and_whole_exports_restore_without_changing_invalid_drafts(page):
            setup(page, [tray, cable])
            page.locator('#version-choice').select_option(cable['id'])
            exports = [download(page, button) for button in ['export-version', 'export-versions']]
            for number, ((name, body), target) in enumerate(zip(exports, ['#param-length', '#viewer']), 1):
                other_context = context()
                try:
                    other = other_context.new_page()
                    control = setup(other)
                    custom(other)
                    other.locator('#param-length').fill('')
                    other.locator('#save-dimensions').click()
                    expect(other.locator('#param-length')).to_have_attribute('aria-invalid', 'true')
                    other.locator('#version-name').fill('Unfinished name')
                    other.locator('.saved-dimensions summary').click()
                    before = snapshot(other)
                    path = ROOT.parent / '.cad-cache' / name
                    path.write_bytes(body)
                    events = native_drop(other, path, target)
                    rows = json.loads(stored(other))
                    assert len(rows) == number and snapshot(other) == before
                    assert other.locator('.saved-dimensions').evaluate('node=>node.open')
                    assert other.evaluate('window.droppedJsonReads') == 1
                    expect(other.locator('#undo-version')).to_be_enabled()
                    if number == 2:
                        other.screenshot(path=str(ROOT / 'review/cloud_version_drop_desktop.png'))
                    other.locator('#undo-version').click()
                    assert json.loads(stored(other)) == [] and snapshot(other) == before
                    other.locator('#revert-parameters').click()
                    retained(other, control)
                    cases.append({'check': 'native_export', 'file': name, 'target': target, 'entries': number,
                        'native_drop': events, 'json_reads': 1, 'invalid_draft_kept': True, 'undo_kept_fields': True,
                        'exact_cached_files_and_dimension_names': True, 'native_jobs': 2})
                finally:
                    other_context.close()

        def content_detection_bom_and_both_limits_stay_bounded(page):
            control = setup(page)
            page.locator('#param-length').fill('190.55')
            before = snapshot(page)
            row = json.loads(backup([cable]))
            text = b'\xef\xbb\xbf' + json.dumps({'versions': row['versions'], 'version': 1, 'format': row['format']}, ensure_ascii=False).encode()
            body = text + b' ' * (65536 - len(text))
            drop(page, body, 'renamed-without-extension')
            expect(page.locator('#version-backup-message')).to_contain_text('Imported 1')
            assert snapshot(page) == before and len(json.loads(stored(page))) == 1
            reads = page.evaluate('window.droppedJsonReads')
            drop(page, size=65537)
            expect(page.locator('#dimensions-error')).to_contain_text('exceeds 64 KiB')
            assert page.evaluate('window.droppedJsonReads') == reads
            dim = json.dumps({'model': 'parts_tray', 'units': 'mm', 'parameters': {'length': 180.5}}).encode()
            drop(page, dim + b' ' * (16385 - len(dim)))
            expect(page.locator('#dimensions-error')).to_contain_text('exceeds 16 KiB')
            assert page.evaluate('window.droppedJsonReads') == reads + 1
            assert page.locator('#param-length').input_value() == '190.55' and not control['jobs']
            page.locator('#dimensions-file').set_input_files({'name': 'dimensions.json', 'mimeType': 'application/json', 'buffer': dim + b' ' * 16384})
            expect(page.locator('#dimensions-error')).to_contain_text('exceeds 16 KiB')
            assert page.evaluate('window.droppedJsonReads') == reads + 1
            cases.append({'check': 'bounds', 'backup_bytes': len(body), 'backup_reads': 1,
                'oversize_drop_reads': 0, 'oversize_dimensions_drop_reads': 1, 'dimensions_chooser_oversize_reads': 0,
                'draft_kept': True, 'native_jobs': 0})

        def all_six_assemblies_merge_canonical_inventory_and_undo_without_building(page):
            control = setup(page)
            rows = [record(item['name'], item['title'], index) for index, item in enumerate(models, 1) if item['kind'] == 'assembly']
            for row in rows:
                row['dimensions'].update(kit=[{'model': 'parts_tray', 'quantity': 999}], bounds_mm=[999, 999, 999], mesh_sha256='untrusted')
            page.locator('#param-length').fill('190.55')
            before = snapshot(page)
            drop(page, backup(rows), target='#viewer')
            expect(page.locator('#version-backup-message')).to_contain_text('Imported 6')
            saved = json.loads(stored(page))
            assert len(saved) == 6 and snapshot(page) == before and not control['jobs']
            for row in saved:
                item = catalog[row['dimensions']['model']]
                assert row['dimensions'] == {'model': item['name'], 'units': 'mm', 'parameters': item['defaults'], 'kit': item['kit']}
            page.locator('#undo-version').click()
            assert json.loads(stored(page)) == [] and snapshot(page) == before
            cases.append({'check': 'kits', 'canonical_assemblies': 6, 'undo_restored_empty_library': True, 'native_jobs': 0})

        def conflicts_repeats_invalid_records_and_storage_failures_keep_atomic_data(page):
            control = setup(page, [tray])
            changed = copy.deepcopy(tray)
            changed['dimensions']['parameters']['length'] = 190.555
            before = snapshot(page)
            drop(page, backup([changed]))
            expect(page.locator('#version-backup-message')).to_contain_text('Imported 1')
            assert json.loads(stored(page))[0]['name'] == 'Wide tray (2)' and snapshot(page) == before
            good = stored(page)
            drop(page, backup([changed]))
            expect(page.locator('#version-backup-message')).to_contain_text('already saved')
            assert stored(page) == good
            invalid = copy.deepcopy(cable)
            invalid['dimensions']['parameters']['width'] = 'bad'
            drop(page, backup([record(name='Would add', number=3), invalid]))
            expect(page.locator('#version-backup-message')).to_contain_text('Existing versions are kept')
            assert stored(page) == good and snapshot(page) == before
            full = [record(name='Tray ' + str(i), number=i + 1) for i in range(20)]
            page.evaluate('args=>localStorage.setItem(...args)', [KEY, json.dumps(full)])
            full_text = stored(page)
            drop(page, backup([cable]))
            expect(page.locator('#version-backup-message')).to_contain_text('exceed 20')
            assert stored(page) == full_text
            page.evaluate('args=>localStorage.setItem(...args)', [KEY, good])
            page.evaluate('''()=>{const write=Storage.prototype.setItem;
              Storage.prototype.setItem=function(key,text){if(key==='everyday-prints-versions')throw new DOMException('Full','QuotaExceededError');return write.call(this,key,text);};}''')
            drop(page)
            expect(page.locator('#version-backup-message')).to_contain_text('storage is unavailable')
            assert stored(page) == good and snapshot(page) == before and not control['jobs']
            cases.append({'check': 'atomic', 'conflict_numbered': True, 'repeat_without_write': True,
                'invalid_mixed_capacity_and_quota_preserved': True, 'fields_kept': True, 'native_jobs': 0})

        def newer_actions_release_wait_and_deadline_before_late_dropped_bytes(page):
            actions = ['field', 'save_dimensions', 'copy', 'reset', 'save_version', 'rename', 'replace', 'remove', 'open', 'export', 'undo', 'build', 'retry', 'close']
            for action in actions:
                other_context = context()
                try:
                    other = other_context.new_page()
                    setup(other, [tray])
                    other.locator('#version-choice').select_option(tray['id'])
                    other.locator('#param-length').fill('180.5')
                    if action == 'undo':
                        other.locator('#version-name').fill('Renamed')
                        other.locator('#rename-version').click()
                    other.evaluate('window.watchVersionReadTimer=true')
                    drop(other, backup([cable]), 'slow-drop.json')
                    other.wait_for_function('()=>window.pendingDimensionReads.length===1&&window.versionReadTimers.size===1')
                    if action == 'field': other.locator('#param-length').fill('')
                    elif action == 'save_dimensions': download(other, 'save-dimensions')
                    elif action == 'copy': other.locator('#share').click()
                    elif action == 'reset': other.locator('#reset-parameters').click()
                    elif action == 'save_version':
                        other.locator('#version-name').fill('New version')
                        other.locator('#save-version').click()
                    elif action == 'rename':
                        other.locator('#version-name').fill('Renamed')
                        other.locator('#rename-version').click()
                    elif action == 'replace': other.locator('#replace-version').click()
                    elif action == 'remove': other.locator('#remove-version').click()
                    elif action == 'open': other.locator('#load-version').click()
                    elif action == 'export': download(other, 'export-version')
                    elif action == 'undo': other.locator('#undo-version').click()
                    elif action == 'build': other.locator('#rebuild').click()
                    elif action == 'retry': other.locator('#retry-original').dispatch_event('click')
                    elif action == 'close': other.locator('#close-editor').click()
                    other.wait_for_function('()=>window.versionReadTimers.size===0')
                    expected = stored(other)
                    other.evaluate('()=>window.pendingDimensionReads[0]()')
                    other.evaluate('()=>new Promise(done=>requestAnimationFrame(()=>requestAnimationFrame(done)))')
                    assert stored(other) == expected and 'Routing' not in (expected or '')
                    assert 'Reading dropped' not in other.locator('#version-backup-message').text_content()
                    cases.append({'check': 'discarded_read', 'action': action, 'deadlines_after_action': 0,
                                  'late_storage_unchanged': True})
                finally:
                    other_context.close()

        def timeouts_and_newer_files_keep_only_current_read_and_recover(page):
            control = setup(page)
            page.evaluate('window.watchVersionReadTimer=true')
            drop(page, backup([tray]), 'slow-expired.json')
            page.wait_for_function('()=>window.pendingDimensionReads.length===1&&window.versionReadTimers.size===1')
            page.evaluate('()=>window.fireDroppedDeadline()')
            expect(page.locator('#dimensions-error')).to_contain_text('took too long')
            assert page.evaluate('window.versionReadTimers.size') == 0 and stored(page) is None
            page.evaluate('()=>window.pendingDimensionReads[0]()')
            assert stored(page) is None
            drop(page, backup([tray]), 'slow-old.json')
            page.wait_for_function('()=>window.pendingDimensionReads.length===2&&window.versionReadTimers.size===1')
            drop(page, backup([cable]), 'slow-new.json')
            page.wait_for_function('()=>window.pendingDimensionReads.length===3&&window.versionReadTimers.size===1')
            page.evaluate('()=>window.pendingDimensionReads[1]()')
            assert stored(page) is None and page.evaluate('window.versionReadTimers.size') == 1
            page.evaluate('()=>window.pendingDimensionReads[2]()')
            expect(page.locator('#version-backup-message')).to_contain_text('Imported 1')
            assert json.loads(stored(page))[0]['name'] == cable['name']
            assert page.evaluate('window.versionReadTimers.size') == 0 and not control['jobs']
            cases.append({'check': 'deadlines', 'expired_and_old_bytes_ignored': True,
                'only_current_timer_retained': True, 'new_file_recovered': True, 'native_jobs': 0})

        def dimensions_drops_keep_exact_files_and_existing_chooser_behavior(page):
            control = setup(page)
            drop(page, json.dumps({'model': 'parts_tray', 'units': 'mm', 'parameters': {'length': 180.5}}).encode())
            expect(page.locator('#form-message')).to_contain_text('loaded. Update')
            assert page.locator('#version-backup-message').text_content() == ''
            page.locator('#rebuild').click()
            expect(page.locator('#download-cad')).to_be_enabled()
            assert download(page, 'download-cad')[1] == fixtures['parts_tray'][0]
            retained(page, control)
            page.locator('#param-length').fill('')
            page.locator('#versions-file').set_input_files({'name': 'versions.json', 'mimeType': 'application/json', 'buffer': backup([cable])})
            expect(page.locator('#version-backup-message')).to_contain_text('Imported 1')
            assert page.locator('#param-length').input_value() == ''
            page.locator('#revert-parameters').click()
            retained(page, control)
            cases.append({'check': 'dimensions', 'json_drop_exact_files': True, 'backup_chooser_invalid_draft_kept': True, 'native_jobs': 2})

        def busy_builds_closed_editor_and_text_drags_never_read_backups(page):
            control = setup(page)
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            expect(page.locator('#download-cad')).to_be_enabled()
            control['hold'] = True
            page.locator('#download-cad').click()
            page.wait_for_timeout(50)
            assert len(control['waiting']) == 1
            expect(page.locator('#stop-build')).to_be_focused()
            drop(page)
            assert page.evaluate('window.droppedJsonReads') == 0 and stored(page) is None
            expect(page.locator('#stop-build')).to_be_focused()
            with page.expect_download() as event:
                control['waiting'].pop().fulfill(body=fixtures['parts_tray'][0], headers=headers(fixtures['parts_tray'][1]))
            assert Path(event.value.path()).read_bytes() == fixtures['parts_tray'][0]
            result = page.evaluate(DROP, {'files': [], 'event': 'drop', 'target': '#param-length', 'text': 'Draft text', 'related': None})
            assert not result['prevented']
            page.locator('#close-editor').click()
            result = page.evaluate(DROP, {'files': [{'name': 'versions.json', 'mime': 'application/json', 'body': base64.b64encode(backup([cable])).decode()}],
                'event': 'drop', 'target': '#editor', 'text': None, 'related': None})
            assert not result['prevented'] and page.evaluate('window.droppedJsonReads') == 0 and stored(page) is None
            cases.append({'check': 'inactive', 'backup_reads': 0, 'stop_focus_kept': True, 'exact_pending_cad': True, 'native_jobs': 2})

        def short_phone_backup_feedback_and_keyboard_download_work_without_graphics(page):
            page.set_viewport_size({'width': 390, 'height': 600})
            page.add_init_script('''const canvas=HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext=function(type,...args){return type.startsWith('webgl')?null:canvas.call(this,type,...args);};''')
            control = setup(page)
            page.locator('#param-length').fill('')
            page.locator('#param-length').focus()
            drop(page)
            expect(page.locator('#version-backup-message')).to_contain_text('Imported 1')
            message = page.locator('#version-backup-message').bounding_box()
            assert message['y'] >= 0 and message['y'] + message['height'] <= 600
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert page.locator('#param-length').input_value() == '' and not control['jobs']
            page.locator('#version-choice').select_option(json.loads(stored(page))[0]['id'])
            page.locator('#export-version').focus()
            with page.expect_download() as event:
                page.locator('#export-version').press('Enter')
            assert json.loads(Path(event.value.path()).read_bytes())['versions'][0]['name'] == cable['name']
            expect(page.locator('#export-version')).to_be_focused()
            box = page.locator('#export-version').bounding_box()
            assert box['height'] >= 44 and 0 <= box['y'] <= 600 - box['height']
            page.screenshot(path=str(ROOT / 'review/cloud_version_drop_mobile.png'))
            page.locator('#revert-parameters').click()
            assert download(page, 'download')[1] == (ASSETS / 'models/parts_tray.stl').read_bytes()
            cases.append({'check': 'mobile', 'viewport': {'width': 390, 'height': 600}, 'feedback_visible': True,
                'keyboard_export_visible': True, 'graphics_required': False, 'draft_kept': True, 'exact_original_stl': True, 'native_jobs': 0})

        tests = [native_selected_and_whole_exports_restore_without_changing_invalid_drafts,
                 content_detection_bom_and_both_limits_stay_bounded,
                 all_six_assemblies_merge_canonical_inventory_and_undo_without_building,
                 conflicts_repeats_invalid_records_and_storage_failures_keep_atomic_data,
                 newer_actions_release_wait_and_deadline_before_late_dropped_bytes,
                 timeouts_and_newer_files_keep_only_current_read_and_recover,
                 dimensions_drops_keep_exact_files_and_existing_chooser_behavior,
                 busy_builds_closed_editor_and_text_drags_never_read_backups,
                 short_phone_backup_feedback_and_keyboard_download_work_without_graphics]
        for test in tests:
            session = context()
            page = session.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                print('START', test.__name__, flush=True)
                test(page)
                assert not errors, errors
                passed.append(test.__name__)
                print('PASS', test.__name__, flush=True)
            except Exception:
                failures.append({'check': test.__name__, 'error': traceback.format_exc(), 'browser_errors': errors})
                print('FAIL', test.__name__, failures[-1]['error'], flush=True)
            finally:
                session.close()
        browser.close()
    report = {'endpoint': BASE, 'passed': passed, 'failures': failures, 'cases': cases,
              'transport': 'Compiled production CSP/assets, exported native downloads, trusted Chromium file drops, real CAD fixtures and controlled local reads.'}
    (ROOT / 'review/cloud_version_drop_validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
