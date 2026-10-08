"""Inspect saved measurements without applying them or disturbing current files."""
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
SUMMARY = '#version-measurements > summary'
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))


def main():
    models = json.loads((ASSETS / 'catalog.json').read_text(encoding='utf-8'))['models']
    catalog = {row['name']: row for row in models}
    fixtures = {name: fixture(name) for name in ['parts_tray', 'cable_comb']}
    passed, failures, cases = [], [], []
    csp = next(line.split(':', 1)[1].strip() for line in (CLOUD / 'public/_headers').read_text().splitlines() if 'Content-Security-Policy:' in line)

    def record(model='parts_tray', name='Wide tray', number=1, defaults=False):
        parameters = catalog[model]['defaults'] if defaults or model not in fixtures else fixtures[model][1]['parameters']
        return {'id': f'00000000-0000-4000-8000-{number:012x}', 'name': name,
                'dimensions': {'model': model, 'units': 'mm', 'parameters': copy.deepcopy(parameters)}}

    tray, cable = record(), record('cable_comb', 'Routing <wide> café ✓', 2)

    def backup(rows):
        return json.dumps({'format': KEY, 'version': 1, 'versions': [{'name': row['name'], 'dimensions': row['dimensions']} for row in rows]}, ensure_ascii=False).encode()

    def display(value):
        if isinstance(value, list):
            return ', '.join(display(number) for number in value)
        return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)

    def expected_fields(row):
        item = catalog[row['dimensions']['model']]
        fields = [[field['label'], display(row['dimensions']['parameters'][field['key']]) + (' ' + field['unit'] if field['unit'] else '')] for field in item['parameters']]
        if item['kit']:
            fields.append(['Parts kit', '\n'.join(catalog[part['model']]['title'] + ' × ' + str(part['quantity']) + (' (fit coupon)' if part['role'] == 'fit_coupon' else '') for part in item['kit'])])
        return fields

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])

        def context():
            result = browser.new_context(viewport={'width': 1440, 'height': 1080}, accept_downloads=True)
            result.set_default_timeout(20000)
            attach_assets(result)
            result.route(BASE + '/', lambda route: route.fulfill(body=(ASSETS / 'index.html').read_bytes(), headers={'Content-Type': 'text/html', 'Content-Security-Policy': csp}))
            return result

        def setup(page, rows=None):
            page.add_init_script(FILES + TIMERS + '''window.measurementWrites=0;window.measurementErrors=[];
              window.addEventListener('error',event=>window.measurementErrors.push(event.message));
              window.addEventListener('unhandledrejection',event=>window.measurementErrors.push(String(event.reason)));
              const writeMeasurements=Storage.prototype.setItem;
              Storage.prototype.setItem=function(key,value){if(key==='everyday-prints-versions')window.measurementWrites++;return writeMeasurements.call(this,key,value);};''')
            if rows is not None:
                page.add_init_script('localStorage.setItem(' + json.dumps(KEY) + ',' + json.dumps(json.dumps(rows, ensure_ascii=False)) + ');')
            control = {'jobs': [], 'hold': False, 'waiting': []}

            def generate(route):
                payload = route.request.post_data_json
                control['jobs'].append(payload)
                if control['hold']:
                    control['waiting'].append(route)
                    page.evaluate('window.measurementBuildHeld=true')
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

        def stored(page):
            return page.evaluate('key=>localStorage.getItem(key)', KEY)

        def snapshot(page):
            return page.evaluate('''()=>({model:document.querySelector('#model-title').textContent,
              fields:[...document.querySelectorAll('[data-parameter]')].map(el=>[el.dataset.parameter,el.value,el.getAttribute('aria-invalid')]),
              fieldErrors:[...document.querySelectorAll('.parameter-error')].map(el=>[el.textContent,el.hidden]),
              name:document.querySelector('#version-name').value,message:document.querySelector('#form-message').textContent,
              error:document.querySelector('#dimensions-error').textContent,errorHidden:document.querySelector('#dimensions-error').hidden,
              href:location.href,history:history.length})''')

        def choose(page, row, expand=False):
            page.locator('#version-choice').select_option(row['id'])
            expect(page.locator('#version-measurements')).to_be_visible()
            if expand and not page.locator('#version-measurements').evaluate('node=>node.open'):
                page.locator(SUMMARY).click()
            expect(page.locator('#version-measurements-name')).to_have_text(row['name'] + ' · ' + catalog[row['dimensions']['model']]['title'])
            fields = page.locator('#version-measurements-fields').evaluate('node=>[...node.querySelectorAll("dt")].map(label=>[label.textContent,[...label.nextElementSibling.childNodes].map(child=>child.nodeName==="BR"?"\\n":child.textContent).join("")])')
            assert fields == expected_fields(row), (row['dimensions']['model'], fields, expected_fields(row))

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
            page.locator('#version-name').fill('Unfinished name')

        def retained(page, control):
            page.locator('#revert-parameters').click()
            stl_name, mesh = download(page, 'download')
            cad_name, archive = download(page, 'download-cad')
            assert mesh == fixtures['parts_tray'][2] and archive == fixtures['parts_tray'][0]
            assert '180.5x100x24mm' in stl_name and '180.5x100x24mm' in cad_name and len(control['jobs']) == 2

        def peer(page):
            other = page.context.new_page()
            other.goto(BASE)
            return other

        def update(other, rows):
            other.evaluate('args=>localStorage.setItem(...args)', [KEY, rows if isinstance(rows, str) else json.dumps(rows, ensure_ascii=False)])

        def inspection_keeps_invalid_drafts_and_exact_cached_downloads(page):
            precise = copy.deepcopy(tray)
            precise['dimensions']['parameters']['length'] = 180.555
            escaped = copy.deepcopy(cable)
            escaped['name'] = 'Routing <img src=x onerror=window.measurementXss=1> café ✓'
            control = setup(page, [precise, escaped])
            expect(page.locator('#version-measurements')).not_to_be_visible()
            assert page.locator('#version-measurements-fields').inner_html() == ''
            custom(page)
            invalid_draft(page)
            before, library, writes = snapshot(page), stored(page), page.evaluate('window.measurementWrites')
            choose(page, precise, True)
            expect(page.locator('#version-measurements-fields dd').first).to_have_text('180.555 mm')
            choose(page, escaped, True)
            assert page.locator('#version-measurements img').count() == 0 and page.evaluate('window.measurementXss || 0') == 0
            assert snapshot(page) == before and stored(page) == library and page.evaluate('window.measurementWrites') == writes
            page.locator('#version-measurements').scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / 'review/cloud_version_measurements_desktop.png'))
            page.locator(SUMMARY).click()
            assert snapshot(page) == before and stored(page) == library
            retained(page, control)
            cases.append({'check': 'inspection', 'exact_decimal': '180.555 mm', 'ordered_list': escaped['dimensions']['parameters']['cable_diameters'], 'escaped_name': True,
                'fields_errors_name_history_and_storage_kept': True, 'inspection_writes': 0, 'exact_cached_files_and_dimension_names': True, 'native_jobs': 2})

        def every_model_shows_ordered_units_and_canonical_kit_inventory(page):
            rows = [record(item['name'], item['title'], number, True) for number, item in enumerate(models, 1)]
            for row in rows:
                row['dimensions'].update(kit=[{'model': 'parts_tray', 'quantity': 999}], bounds_mm=[999,999,999], mesh_sha256='untrusted')
            control = setup(page, rows[:20])
            other = peer(page)
            before, writes = snapshot(page), page.evaluate('window.measurementWrites')
            seen = []
            for offset in range(0, len(rows), 20):
                batch = rows[offset:offset + 20]
                if offset:
                    update(other, batch)
                    expect(page.locator('#version-choice option[value="' + batch[0]['id'] + '"]')).to_have_count(1)
                for row in batch:
                    choose(page, row, True)
                    seen.append(row['dimensions']['model'])
                    assert snapshot(page) == before
            assert len(seen) == 53 and len([row for row in rows if catalog[row['dimensions']['model']]['kind'] == 'assembly']) == 6
            assert not control['jobs'] and page.evaluate('window.measurementWrites') == writes
            other.close()
            cases.append({'check': 'schemas', 'models': seen, 'canonical_assemblies': 6, 'catalog_order_and_units': True, 'stored_geometry_ignored': True, 'inspection_writes': 0, 'native_jobs': 0})

        def local_edits_undo_and_failed_writes_keep_the_selected_measurements(page):
            control = setup(page, [tray])
            custom(page)
            choose(page, tray, True)
            page.locator('#version-name').fill('Renamed café')
            page.locator('#rename-version').click()
            renamed = copy.deepcopy(tray)
            renamed['name'] = 'Renamed café'
            choose(page, renamed, True)
            page.locator('#param-length').fill('190.555')
            page.locator('#replace-version').click()
            replaced = copy.deepcopy(renamed)
            replaced['dimensions']['parameters']['length'] = 190.555
            choose(page, replaced, True)
            before, library = snapshot(page), stored(page)
            page.evaluate('''()=>{window.failMeasurementWrites=true;const write=Storage.prototype.setItem;
              Storage.prototype.setItem=function(key,value){if(key==='everyday-prints-versions'&&window.failMeasurementWrites)throw new DOMException('Full','QuotaExceededError');return write.call(this,key,value);};}''')
            page.locator('#version-name').fill('Failed rename')
            page.locator('#rename-version').click()
            expect(page.locator('#version-message')).to_contain_text('could not be renamed')
            assert stored(page) == library
            page.locator(SUMMARY).click()
            page.locator(SUMMARY).click()
            expect(page.locator('#undo-version')).to_be_enabled()
            expect(page.locator('#version-measurements-fields dd').first).to_have_text('190.555 mm')
            assert {key:value for key,value in snapshot(page).items() if key != 'name'} == {key:value for key,value in before.items() if key != 'name'}
            page.evaluate('window.failMeasurementWrites=false')
            page.locator('#undo-version').click()
            choose(page, renamed, True)
            expect(page.locator('#param-length')).to_have_value('190.555')
            page.locator('#remove-version').click()
            expect(page.locator('#version-measurements')).not_to_be_visible()
            assert page.locator('#version-measurements-name').text_content() == '' and page.locator('#version-measurements-fields').inner_html() == ''
            page.locator('#undo-version').click()
            choose(page, renamed, True)
            retained(page, control)
            cases.append({'check': 'edits', 'rename_and_replace_updated': True, 'unchanged_inspection_kept_undo': True, 'quota_kept_saved_measurements': True,
                'undo_restored_values_and_selection': True, 'removed_details_cleared': True, 'exact_cached_files': True, 'native_jobs': 2})

        def imported_and_exported_versions_remain_portable_for_explicit_opening(page):
            control = setup(page, [tray])
            custom(page)
            invalid_draft(page)
            choose(page, tray, True)
            before = snapshot(page)
            page.locator('#versions-file').set_input_files({'name':'portable.json','mimeType':'application/json','buffer':b'\xef\xbb\xbf' + backup([cable])})
            expect(page.locator('#version-backup-message')).to_contain_text('Imported 1')
            assert snapshot(page) == before and page.locator('#version-measurements').evaluate('node=>node.open')
            imported = json.loads(stored(page))[0]
            choose(page, imported, True)
            name, body = download(page, 'export-version')
            assert name == 'everyday-prints-version.json' and json.loads(body)['versions'][0] == {'name':cable['name'],'dimensions':cable['dimensions']}
            session = context()
            try:
                other = session.new_page()
                other_control = setup(other)
                other.locator('#param-length').fill('190.55')
                result = other.evaluate(DROP, {'files':[{'name':name,'mime':'application/json','body':base64.b64encode(body).decode()}], 'event':'drop','target':'#viewer','text':None,'related':None})
                assert result['prevented']
                expect(other.locator('#version-backup-message')).to_contain_text('Imported 1')
                portable = json.loads(stored(other))[0]
                choose(other, portable, True)
                expect(other.locator('#param-length')).to_have_value('190.55')
                assert not other_control['jobs']
                other.locator('#load-version').click()
                expect(other.locator('#model-title')).to_have_text(catalog['cable_comb']['title'])
                other.locator('#rebuild').click()
                expect(other.locator('#download-cad')).to_be_enabled()
                assert download(other,'download')[1] == fixtures['cable_comb'][2] and download(other,'download-cad')[1] == fixtures['cable_comb'][0]
                assert len(other_control['jobs']) == 2
            finally:
                session.close()
            page.locator('#undo-version').click()
            choose(page, tray, True)
            assert snapshot(page) == before and len(json.loads(stored(page))) == 1
            retained(page, control)
            cases.append({'check':'portable','bom_import':True,'native_export_matches_display':True,'drop_restored_name_and_list':True,
                'inspection_did_not_apply_fields':True,'explicit_open_built_exact_list_files':True,'undo_restored_original_selection':True,'native_jobs_in_new_browser':2})

        def inspection_keeps_pending_json_imports_and_their_deadlines(page):
            for channel in ['dimensions_chooser','backup_chooser','dimensions_drop','backup_drop']:
                session = context()
                try:
                    other = session.new_page()
                    control = setup(other, [tray,cable])
                    other.locator('#param-length').fill('190.55')
                    choose(other, tray)
                    incoming = record('cable_comb','Imported after inspection',3)
                    body = backup([incoming]) if 'backup' in channel else json.dumps({'model':'parts_tray','units':'mm','parameters':{'length':180.5}}).encode()
                    other.evaluate('window.watchVersionReadTimer=true')
                    if 'chooser' in channel:
                        other.locator('#versions-file' if 'backup' in channel else '#dimensions-file').set_input_files({'name':'slow-inspection.json','mimeType':'application/json','buffer':body})
                    else:
                        other.evaluate(DROP, {'files':[{'name':'slow-inspection.json','mime':'application/json','body':base64.b64encode(body).decode()}], 'event':'drop','target':SUMMARY,'text':None,'related':None})
                    other.wait_for_function('()=>window.pendingDimensionReads.length===1&&window.versionReadTimers.size===1')
                    choose(other, cable, True)
                    other.locator(SUMMARY).click()
                    other.locator(SUMMARY).click()
                    assert other.evaluate('window.versionReadTimers.size') == 1 and other.locator('#param-length').input_value() == '190.55'
                    other.evaluate('window.pendingDimensionReads[0]()')
                    expect(other.locator('#version-backup-message' if 'backup' in channel else '#form-message')).to_contain_text('Imported 1' if 'backup' in channel else 'Saved dimensions')
                    assert other.evaluate('window.versionReadTimers.size') == 0 and other.evaluate('window.fileReads') == 1
                    choose(other,cable,True)
                    assert other.locator('#param-length').input_value() == ('190.55' if 'backup' in channel else '180.5') and not control['jobs']
                    assert not other.evaluate('window.measurementErrors')
                    cases.append({'check':'pending_read','channel':channel,'inspection_kept_read_and_deadline':True,'raw_reads':1,'accepted_after_inspection':True,'native_jobs':0})
                finally:
                    session.close()

        def cross_tab_replacements_removals_and_corruption_keep_reachable_focus(page):
            control = setup(page,[tray,cable])
            custom(page)
            invalid_draft(page)
            choose(page,tray,True)
            other = peer(page)
            before = snapshot(page)
            updated = copy.deepcopy(tray)
            updated['name'] = 'Updated elsewhere'
            updated['dimensions']['parameters']['length'] = 180.555
            page.locator(SUMMARY).focus()
            update(other,[updated,cable])
            expect(page.locator('#version-measurements-name')).to_contain_text('Updated elsewhere')
            expect(page.locator('#version-measurements-fields dd').first).to_have_text('180.555 mm')
            expect(page.locator(SUMMARY)).to_be_focused()
            assert snapshot(page) == before
            update(other,[cable])
            expect(page.locator('#version-measurements')).not_to_be_visible()
            expect(page.locator('#version-choice')).to_be_focused()
            assert page.locator('#version-measurements-fields').inner_html() == '' and snapshot(page) == before
            choose(page,cable,True)
            page.locator(SUMMARY).focus()
            update(other,'broken storage')
            expect(page.locator('#versions-sync-message')).to_have_class('error')
            expect(page.locator('#version-measurements')).not_to_be_visible()
            expect(page.locator('#version-choice')).to_be_focused()
            assert stored(page) == 'broken storage' and snapshot(page) == before
            update(other,[updated,cable])
            expect(page.locator('#versions-sync-message')).to_contain_text('available again')
            choose(page,updated,True)
            page.locator(SUMMARY).focus()
            page.evaluate('''()=>{window.denyMeasurementRead=true;const read=Storage.prototype.getItem;
              Storage.prototype.getItem=function(key){if(key==='everyday-prints-versions'&&window.denyMeasurementRead)throw new DOMException('Denied','SecurityError');return read.call(this,key);};}''')
            update(other,[cable])
            expect(page.locator('#versions-sync-message')).to_contain_text('unavailable')
            expect(page.locator('#version-measurements')).not_to_be_visible()
            expect(page.locator('#version-choice')).to_be_focused()
            page.evaluate('window.denyMeasurementRead=false')
            update(other,[updated,cable])
            expect(page.locator('#versions-sync-message')).to_contain_text('available again')
            choose(page,cable,True)
            assert snapshot(page) == before
            other.close()
            retained(page,control)
            cases.append({'check':'sync','fresh_replacement_displayed':True,'removed_or_unreadable_details_cleared':True,
                'hidden_summary_focus_returned_to_choice':True,'corrupt_raw_storage_kept':True,'denied_read_recovered':True,'editor_and_cached_files_kept':True,'native_jobs':2})

        def opening_and_selection_read_fresh_storage_before_queued_events(page):
            page.add_init_script('''window.holdMeasurementEvents=true;window.measurementEvents=[];
              const addMeasurementListener=window.addEventListener.bind(window);
              window.addEventListener=(type,listener,...options)=>addMeasurementListener(type,type==='storage'?event=>{
                if(event.key==='everyday-prints-versions'&&window.holdMeasurementEvents){window.measurementEvents.push(()=>listener(event));return;}listener(event);
              }:listener,...options);''')
            control = setup(page,[tray,cable])
            page.locator('#param-length').fill('190.55')
            choose(page,tray)
            page.locator('#version-name').fill('Local rename')
            page.locator('#rename-version').click()
            expect(page.locator('#undo-version')).to_be_enabled()
            page.locator('#version-name').fill('Unfinished')
            before,writes = snapshot(page),page.evaluate('window.measurementWrites')
            page.locator(SUMMARY).click()
            expect(page.locator('#undo-version')).to_be_enabled()
            page.locator(SUMMARY).click()
            other = peer(page)
            fresh = copy.deepcopy(tray)
            fresh['name'] = 'Fresh before event'
            fresh['dimensions']['parameters']['length'] = 180.555
            update(other,[fresh,cable])
            page.wait_for_function('()=>window.measurementEvents.length>0')
            expect(page.locator('#version-measurements-name')).to_contain_text('Local rename')
            page.locator(SUMMARY).focus()
            page.locator(SUMMARY).press('Enter')
            expect(page.locator('#version-measurements-name')).to_contain_text('Fresh before event')
            expect(page.locator('#version-measurements-fields dd').first).to_have_text('180.555 mm')
            expect(page.locator('#undo-version')).not_to_be_visible()
            assert snapshot(page) == before and page.evaluate('window.measurementWrites') == writes
            update(other,[cable])
            page.locator('#version-choice').select_option(tray['id'])
            expect(page.locator('#version-measurements')).not_to_be_visible()
            expect(page.locator('#version-choice')).to_have_value('')
            assert snapshot(page) == before
            page.evaluate('()=>{window.holdMeasurementEvents=false;window.measurementEvents.splice(0).forEach(release=>release());}')
            choose(page,cable,True)
            assert not control['jobs'] and page.evaluate('window.measurementWrites') == writes
            other.close()
            cases.append({'check':'fresh_reads','opening_read_latest_name_and_decimal':True,'selection_cleared_removed_record':True,
                'unchanged_read_kept_undo':True,'newer_records_cleared_stale_undo':True,'queued_events_did_not_apply_fields':True,'inspection_writes':0,'native_jobs':0})

        def read_only_inspection_during_cad_keeps_exact_delivery_and_focus(page):
            control = setup(page,[tray,cable])
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            expect(page.locator('#download-cad')).to_be_enabled()
            control['hold'] = True
            page.locator('#download-cad').click()
            page.wait_for_function('()=>window.measurementBuildHeld===true')
            expect(page.locator('#stop-build')).to_be_focused()
            before = snapshot(page)
            choose(page,cable,True)
            page.locator(SUMMARY).focus()
            expect(page.locator('#load-version')).to_be_disabled()
            expect(page.locator('#export-version')).to_be_disabled()
            assert snapshot(page) == before and len(control['waiting']) == 1
            other = peer(page)
            update(other,[tray])
            expect(page.locator('#version-measurements')).not_to_be_visible()
            expect(page.locator('#version-choice')).to_be_focused()
            assert snapshot(page) == before and len(control['waiting']) == 1
            with page.expect_download() as event:
                control['waiting'].pop().fulfill(body=fixtures['parts_tray'][0],headers=headers(fixtures['parts_tray'][1]))
            assert Path(event.value.path()).read_bytes() == fixtures['parts_tray'][0] and '180.5x100x24mm' in event.value.suggested_filename
            expect(page.locator('#version-choice')).to_be_focused()
            assert download(page,'download')[1] == fixtures['parts_tray'][2] and download(page,'download-cad')[1] == fixtures['parts_tray'][0] and len(control['jobs']) == 2
            other.close()
            cases.append({'check':'busy','inspection_did_not_apply_or_abort':True,'mutation_and_export_controls_guarded':True,
                'disappearing_summary_kept_reachable_focus':True,'exact_pending_and_cached_cad':True,'dimension_names_kept':True,'native_jobs':2})

        def keyboard_inspection_wraps_long_names_and_lists_without_graphics(page):
            for viewport in [{'width':320,'height':568},{'width':390,'height':600},{'width':390,'height':844},{'width':1440,'height':600}]:
                session = context()
                try:
                    other = session.new_page()
                    other.set_viewport_size(viewport)
                    other.add_init_script('''const canvas=HTMLCanvasElement.prototype.getContext;
                      HTMLCanvasElement.prototype.getContext=function(type,...args){return type.startsWith('webgl')?null:canvas.call(this,type,...args);};''')
                    long = copy.deepcopy(cable)
                    long['name'] = 'É' * 80
                    long['dimensions']['parameters']['cable_diameters'] = [9,2.5,4,3,3.5,4.5,5,5.5,6,6.5,7,7.5,8,8.5,9.5,10]
                    control = setup(other,[tray,long])
                    invalid_draft(other)
                    before,library = snapshot(other),stored(other)
                    choose(other,long)
                    other.locator(SUMMARY).focus()
                    other.locator(SUMMARY).press('Enter')
                    expect(other.locator('#version-measurements')).to_have_attribute('open','')
                    choose(other,long,True)
                    other.locator(SUMMARY).scroll_into_view_if_needed()
                    box = other.locator(SUMMARY).bounding_box()
                    assert box['height'] >= 44 and 0 <= box['y'] <= viewport['height'] - box['height']
                    assert other.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    assert other.locator('.parameters-panel').evaluate('node=>node.scrollWidth<=node.clientWidth')
                    assert snapshot(other) == before and stored(other) == library and not control['jobs']
                    if viewport == {'width':390,'height':600}:
                        other.screenshot(path=str(ROOT / 'review/cloud_version_measurements_mobile.png'))
                    other.locator(SUMMARY).press('Tab')
                    expect(other.locator('#load-version')).to_be_focused()
                    other.locator('#load-version').press('Shift+Tab')
                    expect(other.locator(SUMMARY)).to_be_focused()
                    other.locator(SUMMARY).press('Enter')
                    assert not other.locator('#version-measurements').evaluate('node=>node.open') and snapshot(other) == before
                    other.locator('#revert-parameters').click()
                    assert download(other,'download')[1] == (ASSETS / 'models/parts_tray.stl').read_bytes()
                    assert not other.evaluate('window.measurementErrors')
                    cases.append({'check':'keyboard_layout','viewport':viewport,'summary_target_height':box['height'],'keyboard_toggle_and_tab':True,
                        'long_name_and_16_values_wrapped':True,'invalid_draft_and_storage_kept':True,'exact_original_stl':True,'graphics_required':False,'native_jobs':0})
                finally:
                    session.close()

        tests = [inspection_keeps_invalid_drafts_and_exact_cached_downloads,
                 every_model_shows_ordered_units_and_canonical_kit_inventory,
                 local_edits_undo_and_failed_writes_keep_the_selected_measurements,
                 imported_and_exported_versions_remain_portable_for_explicit_opening,
                 inspection_keeps_pending_json_imports_and_their_deadlines,
                 cross_tab_replacements_removals_and_corruption_keep_reachable_focus,
                 opening_and_selection_read_fresh_storage_before_queued_events,
                 read_only_inspection_during_cad_keeps_exact_delivery_and_focus,
                 keyboard_inspection_wraps_long_names_and_lists_without_graphics]
        for test in tests:
            session = context()
            page = session.new_page()
            errors = []
            page.on('pageerror',lambda error:errors.append(str(error)))
            try:
                print('START',test.__name__,flush=True)
                test(page)
                assert not errors and not page.evaluate('window.measurementErrors || []'), errors
                passed.append(test.__name__)
                print('PASS',test.__name__,flush=True)
            except Exception:
                failures.append({'check':test.__name__,'error':traceback.format_exc(),'browser_errors':errors})
                print('FAIL',test.__name__,failures[-1]['error'],flush=True)
            finally:
                session.close()
        browser.close()
    report = {'endpoint':BASE,'passed':passed,'failures':failures,'cases':cases,
        'transport':'Compiled production CSP/assets, all 53 canonical schemas, actual two-tab storage events and queued reads, native version exports and exact CAD fixtures, bounded local reads, and keyboard inspection with and without graphics.'}
    (ROOT / 'review/cloud_version_measurements_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
