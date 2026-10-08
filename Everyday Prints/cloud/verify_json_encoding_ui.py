"""Reject damaged UTF-8 without changing drafts, versions or verified downloads."""
import base64
import copy
import json
import os
from pathlib import Path
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
CHANNELS = ['dimensions_chooser', 'backup_chooser', 'dimensions_drop', 'backup_drop']


def main():
    models = json.loads((ASSETS / 'catalog.json').read_text(encoding='utf-8'))['models']
    catalog = {row['name']: row for row in models}
    fixtures = {name: fixture(name) for name in ['parts_tray', 'cable_comb']}
    passed, failures, cases = [], [], []
    csp = next(line.split(':', 1)[1].strip() for line in (CLOUD / 'public/_headers').read_text().splitlines() if 'Content-Security-Policy:' in line)

    def record(model='parts_tray', name='Wide tray', number=1):
        return {'id': f'00000000-0000-4000-8000-{number:012x}', 'name': name,
                'dimensions': {'model': model, 'units': 'mm', 'parameters': copy.deepcopy(fixtures[model][1]['parameters'] if model in fixtures else catalog[model]['defaults'])}}

    tray, cable = record(), record('cable_comb', 'Routing café 日本語 ✓ �', 2)

    def encode(value):
        return json.dumps(value, ensure_ascii=False).encode('utf-8')

    def backup(rows):
        return encode({'format': KEY, 'version': 1, 'versions': [{'name': row['name'], 'dimensions': row['dimensions']} for row in rows]})

    dimensions = encode({'model': 'parts_tray', 'units': 'mm', 'parameters': {'length': 180.5}, 'note': 'café 日本語 �'})
    bad_dimensions = encode({'model': 'parts_tray', 'units': 'mm', 'parameters': {'length': 180.5}, 'note': 'ENCODING_MARKER'}).replace(b'ENCODING_MARKER', b'\xff')
    bad_backup = backup([record('cable_comb', 'Broken ENCODING_MARKER', 3)]).replace(b'ENCODING_MARKER', b'\xff')

    def body_for(channel, malformed=False):
        return (bad_backup if malformed else backup([cable])) if 'backup' in channel else (bad_dimensions if malformed else dimensions)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])

        def context():
            result = browser.new_context(viewport={'width': 1440, 'height': 1080}, accept_downloads=True)
            result.set_default_timeout(20000)
            attach_assets(result)
            result.route(BASE + '/', lambda route: route.fulfill(body=(ASSETS / 'index.html').read_bytes(), headers={'Content-Type': 'text/html', 'Content-Security-Policy': csp}))
            return result

        def setup(page, rows=None):
            page.add_init_script(FILES + TIMERS + '''window.jsonEncodingErrors=[];
              window.addEventListener('error',event=>window.jsonEncodingErrors.push(event.message));
              window.addEventListener('unhandledrejection',event=>window.jsonEncodingErrors.push(String(event.reason)));
              const scheduleEncodingDeadline=window.setTimeout.bind(window);
              window.setTimeout=(callback,delay,...args)=>{
                const watched=delay===15000&&window.watchVersionReadTimer;
                const id=scheduleEncodingDeadline(callback,delay,...args);
                if(watched)window.fireEncodingDeadline=()=>{window.clearTimeout(id);callback(...args);};
                return id;
              };''')
            if rows is not None:
                page.add_init_script('localStorage.setItem(' + json.dumps(KEY) + ',' + json.dumps(json.dumps(rows, ensure_ascii=False)) + ');')
            control = {'jobs': [], 'hold': False, 'waiting': []}

            def generate(route):
                payload = route.request.post_data_json
                control['jobs'].append(payload)
                if control['hold']:
                    control['waiting'].append(route)
                    page.evaluate('window.encodingBuildHeld=true')
                    return
                archive, metadata, mesh = fixtures[payload['model']]
                assert payload['parameters'] == metadata['parameters'], payload
                route.fulfill(body=archive if payload.get('format') == 'cad' else mesh,
                    headers=headers(metadata) if payload.get('format') == 'cad' else headers({**metadata, 'format': 'stl', 'file_sha256': metadata['mesh_sha256']}, 'model/stl'))

            page.route('**/api/generate', generate)
            page.goto(BASE)
            page.locator('[data-model="parts_tray"]').click()
            expect(page.locator('#download-cad')).to_be_enabled()
            page.locator('.saved-dimensions > summary').click()
            return control

        def ingest(page, channel, body=None, name='encoding.json', size=None):
            body = body_for(channel) if body is None else body
            if name.startswith('slow'):
                page.evaluate('window.watchVersionReadTimer=true')
            if 'chooser' in channel:
                page.locator('#versions-file' if 'backup' in channel else '#dimensions-file').set_input_files(
                    {'name': name, 'mimeType': 'application/json', 'buffer': body if size is None else b' ' * size})
            else:
                file = {'name': name, 'mime': 'application/json', **({'size': size} if size is not None else {'body': base64.b64encode(body).decode()})}
                return page.evaluate(DROP, {'files': [file], 'event': 'drop', 'target': '#viewer' if 'backup' in channel else '#param-length', 'text': None, 'related': None})

        def error_area(page, channel):
            return page.locator('#version-backup-message' if channel == 'backup_chooser' else '#dimensions-error')

        def accepted(page, channel):
            expect(page.locator('#version-backup-message' if 'backup' in channel else '#form-message')).to_contain_text('Imported 1' if 'backup' in channel else 'Saved dimensions')

        def stored(page):
            return page.evaluate('key=>localStorage.getItem(key)', KEY)

        def snapshot(page):
            return page.evaluate('''key=>({model:document.querySelector('#model-title').textContent,
              fields:Array.from(document.querySelectorAll('[data-parameter]'),el=>[el.dataset.parameter,el.value,el.getAttribute('aria-invalid')]),
              name:document.querySelector('#version-name').value,
              library:localStorage.getItem(key),href:location.href,history:history.length})''', KEY)

        def download(page, button):
            with page.expect_download() as event:
                page.locator('#' + button).click()
            return event.value.suggested_filename, Path(event.value.path()).read_bytes()

        def custom(page):
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            expect(page.locator('#download-cad')).to_be_enabled()
            assert download(page, 'download-cad')[1] == fixtures['parts_tray'][0]

        def invalid_draft(page):
            page.locator('#param-length').fill('')
            page.locator('#save-dimensions').click()
            expect(page.locator('#param-length')).to_have_attribute('aria-invalid', 'true')
            page.locator('#version-name').fill('Unfinished café name')

        def retained(page, control):
            page.locator('#revert-parameters').click()
            stl_name, mesh = download(page, 'download')
            cad_name, archive = download(page, 'download-cad')
            assert mesh == fixtures['parts_tray'][2] and archive == fixtures['parts_tray'][0]
            assert '180.5x100x24mm' in stl_name and '180.5x100x24mm' in cad_name
            assert len(control['jobs']) == 2

        def release(page, index):
            page.evaluate('index=>window.pendingDimensionReads[index]()', index)
            page.evaluate('()=>new Promise(done=>requestAnimationFrame(()=>requestAnimationFrame(done)))')

        def native_drop(page, path, target):
            page.locator(target).scroll_into_view_if_needed()
            rect = page.locator(target).bounding_box()
            page.evaluate('''()=>{window.encodingDrops=[];document.querySelector('#editor').addEventListener('drop',event=>{
              window.encodingDrops.push({trusted:event.isTrusted,files:[...event.dataTransfer.files].map(file=>file.name)});},{once:true});}''')
            session = page.context.new_cdp_session(page)
            try:
                data = {'items': [], 'files': [str(path)], 'dragOperationsMask': 1}
                for kind in ['dragEnter', 'dragOver', 'drop']:
                    session.send('Input.dispatchDragEvent', {'type': kind, 'x': rect['x'] + rect['width'] / 2, 'y': rect['y'] + rect['height'] / 2, 'data': data})
            finally:
                session.detach()
            page.wait_for_function('()=>window.encodingDrops.length===1')
            events = page.evaluate('window.encodingDrops')
            assert events == [{'trusted': True, 'files': [path.name]}]
            return events

        def damaged_dimensions_chooser_keeps_invalid_draft_and_cached_files(page):
            control = setup(page, [tray])
            custom(page)
            invalid_draft(page)
            before = snapshot(page)
            ingest(page, 'dimensions_chooser', bad_dimensions)
            expect(error_area(page, 'dimensions_chooser')).to_contain_text('not valid UTF-8')
            assert snapshot(page) == before and page.evaluate('window.fileReads') == 1
            retained(page, control)
            page.locator('#param-length').fill('190.55')
            ingest(page, 'dimensions_chooser', b'\xef\xbb\xbf' + dimensions)
            accepted(page, 'dimensions_chooser')
            expect(page.locator('#param-length')).to_have_value('180.5')
            assert download(page, 'download')[1] == fixtures['parts_tray'][2]
            assert download(page, 'download-cad')[1] == fixtures['parts_tray'][0] and len(control['jobs']) == 2
            cases.append({'check': 'dimensions_chooser', 'invalid_byte': 'ff', 'draft_library_history_kept': True, 'raw_reads': 2, 'bom_recovery': True, 'exact_cached_files_and_dimension_names': True, 'native_jobs': 2})

        def damaged_backup_chooser_keeps_names_and_recovers_unicode_list_version(page):
            control = setup(page, [tray])
            custom(page)
            invalid_draft(page)
            before = snapshot(page)
            ingest(page, 'backup_chooser', bad_backup)
            expect(error_area(page, 'backup_chooser')).to_contain_text('not valid UTF-8')
            assert snapshot(page) == before and page.evaluate('window.fileReads') == 1
            ingest(page, 'backup_chooser', b'\xef\xbb\xbf' + backup([cable]))
            accepted(page, 'backup_chooser')
            saved = json.loads(stored(page))
            assert len(saved) == 2 and saved[0]['name'] == cable['name'] and saved[0]['dimensions'] == cable['dimensions']
            assert {key: value for key, value in snapshot(page).items() if key != 'library'} == {key: value for key, value in before.items() if key != 'library'}
            page.locator('#undo-version').click()
            after_undo = snapshot(page)
            assert json.loads(after_undo['library']) == json.loads(before['library'])
            assert {key: value for key, value in after_undo.items() if key != 'library'} == {key: value for key, value in before.items() if key != 'library'}
            retained(page, control)
            cases.append({'check': 'backup_chooser', 'invalid_byte': 'ff', 'invalid_draft_and_names_kept': True, 'unicode_list_and_literal_replacement_preserved': True, 'bom_recovery': True, 'undo_restored_library': True, 'exact_cached_files_and_dimension_names': True, 'native_jobs': 2})

        def native_malformed_drops_reject_then_restore_a_real_export(page):
            control = setup(page, [tray])
            custom(page)
            page.locator('#version-choice').select_option(tray['id'])
            name, exported = download(page, 'export-version')
            invalid_draft(page)
            before = snapshot(page)
            for channel, target in [('dimensions_drop', '#viewer'), ('backup_drop', '#param-length')]:
                path = ROOT.parent / '.cad-cache' / (channel + '-invalid-encoding.json')
                path.write_bytes(body_for(channel, True))
                events = native_drop(page, path, target)
                expect(error_area(page, channel)).to_contain_text('not valid UTF-8')
                assert snapshot(page) == before
                cases.append({'check': 'native_rejection', 'channel': channel, 'target': target, 'native_drop': events, 'draft_library_history_kept': True})
            assert page.evaluate('window.fileReads') == 2
            page.locator('#dimensions-error').scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / 'review/cloud_json_encoding_desktop.png'))
            page.locator('#remove-version').click()
            after_remove = snapshot(page)
            path = ROOT.parent / '.cad-cache' / name
            path.write_bytes(exported)
            events = native_drop(page, path, '#viewer')
            expect(page.locator('#version-backup-message')).to_contain_text('Imported 1')
            assert json.loads(stored(page))[0]['name'] == tray['name']
            assert {key: value for key, value in snapshot(page).items() if key != 'library'} == {key: value for key, value in after_remove.items() if key != 'library'}
            retained(page, control)
            cases.append({'check': 'native_recovery', 'exported_file': name, 'native_drop': events, 'raw_reads': 3, 'exact_cached_files_and_dimension_names': True, 'native_jobs': 2})

        def unicode_replacement_and_six_canonical_kits_remain_portable(page):
            control = setup(page)
            page.locator('#param-length').fill('190.55')
            assemblies = [record(row['name'], row['title'] + ' café �', number) for number, row in enumerate(models, 1) if row['kind'] == 'assembly']
            for row in assemblies:
                row['dimensions'].update(kit=[{'model': 'parts_tray', 'quantity': 999}], note='ENCODING_MARKER')
            malformed = backup(assemblies).replace(b'ENCODING_MARKER', b'\xed\xa0\x80')
            before = snapshot(page)
            ingest(page, 'backup_drop', malformed)
            expect(error_area(page, 'backup_drop')).to_contain_text('not valid UTF-8')
            assert snapshot(page) == before
            good = backup(assemblies).replace(b'ENCODING_MARKER', '日本語 �'.encode())
            ingest(page, 'backup_drop', b'\xef\xbb\xbf' + good)
            expect(page.locator('#version-backup-message')).to_contain_text('Imported 6')
            saved = json.loads(stored(page))
            assert len(saved) == 6
            for row in saved:
                item = catalog[row['dimensions']['model']]
                assert row['name'].endswith(' café �')
                assert row['dimensions'] == {'model': item['name'], 'units': 'mm', 'parameters': item['defaults'], 'kit': item['kit']}
            page.locator('#undo-version').click()
            assert json.loads(stored(page)) == [] and page.locator('#param-length').input_value() == '190.55'
            assert not control['jobs']
            cases.append({'check': 'unicode_kits', 'invalid_surrogate_bytes_rejected': True, 'literal_replacement_preserved': True, 'canonical_kits': 6, 'undo_restored_empty_library': True, 'native_jobs': 0})

        def exact_bom_byte_limits_accept_and_oversize_files_never_read(page):
            for channel in CHANNELS:
                session = context()
                try:
                    other = session.new_page()
                    control = setup(other)
                    other.locator('#param-length').fill('190.55')
                    limit = 65536 if 'backup' in channel else 16384
                    text = b'\xef\xbb\xbf' + body_for(channel)
                    text += b' ' * (limit - len(text))
                    ingest(other, channel, text)
                    accepted(other, channel)
                    assert other.evaluate('window.fileReads') == 1
                    before = snapshot(other)
                    ingest(other, channel, size=(65537 if 'drop' in channel else limit + 1))
                    expect(error_area(other, channel)).to_contain_text('exceeds ' + str(64 if 'drop' in channel else limit // 1024) + ' KiB')
                    assert other.evaluate('window.fileReads') == 1 and snapshot(other) == before and not control['jobs']
                    assert not other.evaluate('window.jsonEncodingErrors')
                    cases.append({'check': 'byte_limits', 'channel': channel, 'accepted_bytes': limit, 'bom_included_in_limit': True, 'raw_reads': 1, 'oversize_reads': 0, 'state_kept': True})
                finally:
                    session.close()

        def superseded_malformed_bytes_cannot_replace_newer_actions(page):
            actions = [(channel, action) for channel in CHANNELS for action in ['new_file', 'build', 'close']]
            actions += [(channel, 'field') for channel in CHANNELS if channel != 'backup_chooser']
            for channel, action in actions:
                session = context()
                try:
                    other = session.new_page()
                    setup(other, [tray])
                    other.locator('#param-length').fill('180.5')
                    ingest(other, channel, body_for(channel, True), 'slow-malformed.json')
                    other.wait_for_function('()=>window.pendingDimensionReads.length===1&&window.versionReadTimers.size===1')
                    if action == 'new_file':
                        ingest(other, channel)
                        accepted(other, channel)
                    elif action == 'build':
                        other.locator('#rebuild').click()
                        expect(other.locator('#download-cad')).to_be_enabled()
                    elif action == 'field':
                        other.locator('#param-length').fill('')
                        other.locator('#save-dimensions').click()
                    else:
                        other.locator('#close-editor').click()
                    other.wait_for_function('()=>window.versionReadTimers.size===0')
                    before = snapshot(other)
                    messages = tuple(other.locator('#' + name).text_content() for name in ['dimensions-error', 'version-backup-message', 'form-message'])
                    release(other, 0)
                    assert snapshot(other) == before
                    assert messages == tuple(other.locator('#' + name).text_content() for name in ['dimensions-error', 'version-backup-message', 'form-message'])
                    assert not other.evaluate('window.jsonEncodingErrors')
                    cases.append({'check': 'discarded_bytes', 'channel': channel, 'action': action, 'deadlines_after_action': 0, 'late_state_and_feedback_kept': True})
                finally:
                    session.close()

        def unreadable_and_stalled_byte_reads_recover_without_late_errors(page):
            for channel in CHANNELS:
                session = context()
                try:
                    other = session.new_page()
                    control = setup(other, [tray])
                    other.locator('#param-length').fill('190.55')
                    before = snapshot(other)
                    ingest(other, channel, name='unreadable.json')
                    expect(error_area(other, channel)).to_contain_text('could not be read')
                    assert snapshot(other) == before
                    ingest(other, channel, body_for(channel, True), 'slow-expired.json')
                    other.wait_for_function('()=>window.pendingDimensionReads.length===1&&window.versionReadTimers.size===1')
                    other.evaluate('window.fireEncodingDeadline()')
                    expect(error_area(other, channel)).to_contain_text('took too long')
                    assert snapshot(other) == before and other.evaluate('window.versionReadTimers.size') == 0
                    ingest(other, channel)
                    accepted(other, channel)
                    after = snapshot(other)
                    messages = tuple(other.locator('#' + name).text_content() for name in ['dimensions-error', 'version-backup-message', 'form-message'])
                    release(other, 0)
                    assert snapshot(other) == after and messages == tuple(other.locator('#' + name).text_content() for name in ['dimensions-error', 'version-backup-message', 'form-message'])
                    assert not control['jobs'] and not other.evaluate('window.jsonEncodingErrors')
                    cases.append({'check': 'read_recovery', 'channel': channel, 'unreadable_state_kept': True, 'timeout_state_kept': True, 'deadline_cleared': True, 'new_file_recovered': True, 'late_malformed_bytes_ignored': True, 'native_jobs': 0})
                finally:
                    session.close()

        def busy_and_closed_editor_reject_without_byte_reads(page):
            control = setup(page, [tray])
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            expect(page.locator('#download-cad')).to_be_enabled()
            control['hold'] = True
            page.locator('#download-cad').click()
            page.wait_for_function('()=>window.encodingBuildHeld===true')
            expect(page.locator('#stop-build')).to_be_focused()
            for channel in CHANNELS:
                ingest(page, channel, body_for(channel, True))
            assert page.evaluate('window.fileReads') == 0 and json.loads(stored(page)) == [tray]
            expect(page.locator('#stop-build')).to_be_focused()
            with page.expect_download() as event:
                control['waiting'].pop().fulfill(body=fixtures['parts_tray'][0], headers=headers(fixtures['parts_tray'][1]))
            assert Path(event.value.path()).read_bytes() == fixtures['parts_tray'][0]
            page.locator('#close-editor').click()
            for channel in CHANNELS:
                ingest(page, channel, body_for(channel, True))
            assert page.evaluate('window.fileReads') == 0 and json.loads(stored(page)) == [tray]
            cases.append({'check': 'inactive', 'busy_and_closed_raw_reads': 0, 'stop_focus_kept': True, 'exact_pending_cad': True, 'library_kept': True, 'native_jobs': 2})

        def short_phone_keyboard_chooser_recovers_without_graphics(page):
            page.set_viewport_size({'width': 390, 'height': 600})
            page.add_init_script('''const canvas=HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext=function(type,...args){return type.startsWith('webgl')?null:canvas.call(this,type,...args);};''')
            control = setup(page, [tray])
            page.locator('#param-length').fill('')
            before = snapshot(page)
            session = page.context.new_cdp_session(page)
            try:
                with page.expect_file_chooser() as event:
                    session.send('Page.setInterceptFileChooserDialog', {'enabled': True})
                    page.locator('#import-versions').focus()
                    page.locator('#import-versions').press('Enter')
                event.value.set_files({'name': 'damaged.json', 'mimeType': 'application/json', 'buffer': bad_backup})
            finally:
                session.detach()
            expect(error_area(page, 'backup_chooser')).to_contain_text('Save it as UTF-8 JSON')
            assert snapshot(page) == before
            message = error_area(page, 'backup_chooser').bounding_box()
            assert 0 <= message['y'] and message['y'] + message['height'] <= 600
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(ROOT / 'review/cloud_json_encoding_mobile.png'))
            ingest(page, 'backup_chooser', b'\xef\xbb\xbf' + backup([cable]))
            accepted(page, 'backup_chooser')
            assert json.loads(stored(page))[0]['name'] == cable['name'] and page.locator('#param-length').input_value() == ''
            page.locator('#version-choice').select_option(json.loads(stored(page))[0]['id'])
            page.locator('#export-version').focus()
            with page.expect_download() as event:
                page.locator('#export-version').press('Enter')
            assert json.loads(Path(event.value.path()).read_bytes())['versions'][0]['name'] == cable['name']
            page.locator('#revert-parameters').click()
            assert download(page, 'download')[1] == (ASSETS / 'models/parts_tray.stl').read_bytes() and not control['jobs']
            cases.append({'check': 'mobile', 'viewport': {'width': 390, 'height': 600}, 'keyboard_chooser': True, 'encoding_feedback_visible': True, 'invalid_draft_kept': True, 'unicode_export_preserved': True, 'exact_original_stl': True, 'graphics_required': False, 'native_jobs': 0})

        tests = [damaged_dimensions_chooser_keeps_invalid_draft_and_cached_files,
                 damaged_backup_chooser_keeps_names_and_recovers_unicode_list_version,
                 native_malformed_drops_reject_then_restore_a_real_export,
                 unicode_replacement_and_six_canonical_kits_remain_portable,
                 exact_bom_byte_limits_accept_and_oversize_files_never_read,
                 superseded_malformed_bytes_cannot_replace_newer_actions,
                 unreadable_and_stalled_byte_reads_recover_without_late_errors,
                 busy_and_closed_editor_reject_without_byte_reads,
                 short_phone_keyboard_chooser_recovers_without_graphics]
        for test in tests:
            session = context()
            page = session.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                print('START', test.__name__, flush=True)
                test(page)
                assert not errors and not page.evaluate('window.jsonEncodingErrors || []'), errors
                passed.append(test.__name__)
                print('PASS', test.__name__, flush=True)
            except Exception:
                failures.append({'check': test.__name__, 'error': traceback.format_exc(), 'browser_errors': errors})
                print('FAIL', test.__name__, failures[-1]['error'], flush=True)
            finally:
                session.close()
        browser.close()
    report = {'endpoint': BASE, 'passed': passed, 'failures': failures, 'cases': cases,
              'transport': 'Compiled production CSP/assets, actual malformed UTF-8 files, trusted Chromium disk drops, native downloads and CAD fixtures, bounded raw-byte reads and controlled deadlines.'}
    (ROOT / 'review/cloud_json_encoding_validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
