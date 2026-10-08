"""Export one named version without changing drafts, files or library contents."""
import copy
import json
import os
from pathlib import Path
import sys
import traceback

from playwright.sync_api import expect, sync_playwright
from browser_assets import ASSETS, OFFLINE_BASE, attach_assets
from verify_dimensions_ui import FILES
from verify_export_ui import fixture, headers
from verify_version_backups_ui import TIMERS

CLOUD=Path(__file__).resolve().parent
ROOT=CLOUD.parent
BASE=OFFLINE_BASE
KEY='everyday-prints-versions'
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(ROOT.parent/'.cad-cache/browsers'))


def main():
    models=json.loads((ASSETS/'catalog.json').read_text(encoding='utf-8'))['models']
    catalog={row['name']:row for row in models}
    fixtures={name:fixture(name) for name in ['parts_tray','cable_comb']}
    passed,failures,cases=[],[],[]

    def record(model,name,number=1,parameters=None):
        return {'id':f'00000000-0000-4000-8000-{number:012x}','name':name,
                'dimensions':{'model':model,'units':'mm','parameters':copy.deepcopy(parameters or catalog[model]['defaults'])}}

    wide=record('parts_tray','Wide tray',parameters=fixtures['parts_tray'][1]['parameters'])
    routing=record('cable_comb','Routing <wide> ✓',2,fixtures['cable_comb'][1]['parameters'])
    rows=[wide,routing]

    def backup(records):
        return json.dumps({'format':'everyday-prints-versions','version':1,
                           'versions':[{'name':row['name'],'dimensions':row['dimensions']} for row in records]},ensure_ascii=False).encode()

    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])

        def context():
            result=browser.new_context(viewport={'width':1440,'height':1080},accept_downloads=True)
            result.set_default_timeout(20000)
            attach_assets(result)
            return result

        def setup(page,records=rows):
            page.add_init_script(FILES+TIMERS)
            if records is not None:
                page.add_init_script('localStorage.setItem('+json.dumps(KEY)+','+json.dumps(json.dumps(records))+');')
            control={'jobs':[],'hold':False,'waiting':[]}
            def generate(route):
                payload=route.request.post_data_json
                control['jobs'].append(payload)
                if control['hold']:
                    control['waiting'].append(route)
                    return
                archive,metadata,mesh=fixtures[payload['model']]
                assert payload['parameters']==metadata['parameters'],payload
                route.fulfill(body=archive if payload.get('format')=='cad' else mesh,
                              headers=headers(metadata) if payload.get('format')=='cad' else
                              headers({**metadata,'format':'stl','file_sha256':metadata['mesh_sha256']},'model/stl'))
            page.route('**/api/generate',generate)
            page.goto(BASE)
            page.locator('[data-model="parts_tray"]').click()
            expect(page.locator('#download-cad')).to_be_enabled()
            page.locator('.saved-dimensions > summary').click()
            return control

        def choose(page,row=wide):
            page.locator('#version-choice').select_option(row['id'])

        def download(page,button):
            with page.expect_download() as event:
                page.locator('#'+button).click()
            return event.value.suggested_filename,Path(event.value.path()).read_bytes()

        def selected(page,keyboard=False):
            with page.expect_download() as event:
                page.locator('#export-version').press('Enter') if keyboard else page.locator('#export-version').click()
            file=event.value
            assert file.suggested_filename=='everyday-prints-version.json'
            body=Path(file.path()).read_bytes()
            assert body.endswith(b'\n')
            value=json.loads(body)
            assert value['format']=='everyday-prints-versions' and value['version']==1 and len(value['versions'])==1
            assert 'id' not in value['versions'][0]
            return value['versions'][0],body

        def snapshot(page):
            return page.evaluate('''key=>({model:document.querySelector('#model-title').textContent,
              fields:Array.from(document.querySelectorAll('[data-parameter]'),el=>[el.dataset.parameter,el.value,el.getAttribute('aria-invalid')]),
              name:document.querySelector('#version-name').value,message:document.querySelector('#form-message').textContent,
              href:location.href,history:history.length,storage:localStorage.getItem(key)})''',KEY)

        def custom(page):
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            expect(page.locator('#download-cad')).to_be_enabled()
            assert download(page,'download-cad')[1]==fixtures['parts_tray'][0]

        def invalid_draft_exports_other_model_without_touching_cached_files(page):
            control=setup(page)
            custom(page)
            page.locator('#param-length').fill('')
            page.locator('#save-dimensions').click()
            expect(page.locator('#param-length')).to_have_attribute('aria-invalid','true')
            page.locator('#version-name').fill('Unfinished name')
            choose(page,routing)
            before=snapshot(page)
            row,_=selected(page)
            assert row=={'name':routing['name'],'dimensions':routing['dimensions']}
            assert snapshot(page)==before and page.locator('#download').is_disabled()
            expect(page.locator('#version-backup-message')).to_contain_text('Selected version exported')
            page.screenshot(path=str(ROOT/'review/cloud_selected_version_desktop.png'))
            page.locator('#revert-parameters').click()
            assert download(page,'download')[1]==fixtures['parts_tray'][2]
            assert download(page,'download-cad')[1]==fixtures['parts_tray'][0] and len(control['jobs'])==2
            cases.append({'check':'invalid_draft','selected_model':'cable_comb','draft_and_history_preserved':True,
                          'exact_cached_stl_and_cad':True,'native_jobs':2})

        def portable_selected_file_restores_only_one_version_and_builds_exact_list_files(page):
            control=setup(page)
            choose(page,routing)
            _,body=selected(page)
            other_context=context()
            try:
                other=other_context.new_page()
                other_control=setup(other,None)
                other.locator('#param-length').fill('190.55')
                other.locator('#versions-file').set_input_files({'name':'selected.json','mimeType':'application/json','buffer':body})
                expect(other.locator('#version-backup-message')).to_contain_text('Imported 1')
                expect(other.locator('#param-length')).to_have_value('190.55')
                saved=other.evaluate('key=>JSON.parse(localStorage.getItem(key))',KEY)
                assert len(saved)==1 and saved[0]['name']==routing['name'] and saved[0]['id']!=routing['id']
                other.locator('#version-choice').select_option(saved[0]['id'])
                other.locator('#load-version').click()
                expect(other.locator('#model-title')).to_have_text(catalog['cable_comb']['title'])
                other.locator('#rebuild').click()
                expect(other.locator('#download-cad')).to_be_enabled()
                assert download(other,'download')[1]==fixtures['cable_comb'][2]
                assert download(other,'download-cad')[1]==fixtures['cable_comb'][0] and len(other_control['jobs'])==2
                assert not control['jobs']
                cases.append({'check':'portable','entries':1,'name':saved[0]['name'],'fresh_identity':True,'exact_list_stl_and_cad':True})
            finally:
                other_context.close()

        def all_six_assembly_exports_use_canonical_inventory_without_switching_models(page):
            assemblies=[record(item['name'],item['title'],number) for number,item in enumerate(models,1) if item['kind']=='assembly']
            for row in assemblies:
                row['dimensions'].update(kit=[{'model':'parts_tray','quantity':999}],bounds_mm=[999,999,999],mesh_sha256='untrusted')
            control=setup(page,assemblies)
            page.locator('#param-length').fill('190.55')
            before=snapshot(page)
            for saved in assemblies:
                choose(page,saved)
                row,_=selected(page)
                item=catalog[saved['dimensions']['model']]
                assert row['name']==saved['name'] and row['dimensions']=={
                    'model':item['name'],'units':'mm','parameters':item['defaults'],'kit':item['kit']}
                assert snapshot(page)==before
            assert len(assemblies)==6 and not control['jobs']
            cases.append({'check':'assemblies','canonical_kit_count':6,'editor_unchanged':True,'native_jobs':0})

        def stale_selection_reads_fresh_storage_and_never_exports_all_records(page):
            page.add_init_script('''window.holdSelectedStorage=true;window.selectedStorageEvents=[];
              const addSelectedListener=window.addEventListener.bind(window);
              window.addEventListener=(type,listener,...options)=>addSelectedListener(type,type==='storage'?event=>{
                if(event.key==='everyday-prints-versions'&&window.holdSelectedStorage){window.selectedStorageEvents.push(()=>listener(event));return;}
                listener(event);
              }:listener,...options);''')
            control=setup(page)
            choose(page)
            page.locator('#param-length').fill('190.55')
            other=page.context.new_page()
            other.goto(BASE)
            changed=copy.deepcopy(rows)
            changed[0]['name']='Renamed elsewhere'
            changed[0]['dimensions']['parameters']['length']=190.555
            other.evaluate('args=>localStorage.setItem(...args)',[KEY,json.dumps(changed)])
            page.wait_for_function('()=>window.selectedStorageEvents.length>0')
            before=snapshot(page)
            row,_=selected(page)
            assert row['name']=='Renamed elsewhere' and row['dimensions']['parameters']['length']==190.555
            assert snapshot(page)==before
            downloads=[]
            page.on('download',lambda file:downloads.append(file))
            other.evaluate('args=>localStorage.setItem(...args)',[KEY,json.dumps([routing])])
            page.locator('#export-version').click()
            expect(page.locator('#version-backup-message')).to_contain_text('no longer saved')
            assert not downloads and not control['jobs']
            page.evaluate('()=>{window.holdSelectedStorage=false;window.selectedStorageEvents.splice(0).forEach(release=>release());}')
            expect(page.locator('#export-version')).to_be_disabled()
            expect(page.locator('#version-choice')).to_be_focused()
            expect(page.locator('#param-length')).to_have_value('190.55')
            cases.append({'check':'fresh_selection','fresh_name_and_decimal':True,'removed_selection_downloads':0,'whole_library_fallback':False})

        def storage_failures_preserve_data_and_read_only_exports_work_when_writes_fail(page):
            control=setup(page)
            choose(page)
            good=page.evaluate('key=>localStorage.getItem(key)',KEY)
            downloads=[]
            page.on('download',lambda file:downloads.append(file))
            for text in ['broken','x'*65537]:
                page.evaluate('args=>localStorage.setItem(...args)',[KEY,text])
                page.locator('#export-version').click()
                expect(page.locator('#version-backup-message')).to_have_class('error')
                assert page.evaluate('key=>localStorage.getItem(key)',KEY)==text and not downloads
            page.evaluate('args=>localStorage.setItem(...args)',[KEY,good])
            page.evaluate('''()=>{window.denySelectedRead=true;
              const read=Storage.prototype.getItem,write=Storage.prototype.setItem;
              Storage.prototype.getItem=function(key){if(key==='everyday-prints-versions'&&window.denySelectedRead)throw new DOMException('Denied','SecurityError');return read.call(this,key);};
              Storage.prototype.setItem=function(key,value){if(key==='everyday-prints-versions')throw new DOMException('Full','QuotaExceededError');return write.call(this,key,value);};}''')
            page.locator('#export-version').click()
            expect(page.locator('#version-backup-message')).to_contain_text('unavailable in this browser')
            assert not downloads
            page.evaluate('window.denySelectedRead=false')
            row,_=selected(page)
            assert row=={'name':wide['name'],'dimensions':wide['dimensions']}
            assert page.evaluate('key=>localStorage.getItem(key)',KEY)==good and not control['jobs']
            cases.append({'check':'storage','failure_downloads':0,'quota_independent_export':True,'storage_unchanged':True})

        def export_stops_pending_backups_keeps_dimensions_reads_and_preserves_undo(page):
            control=setup(page)
            custom(page)
            choose(page)
            page.locator('#version-name').fill('Renamed')
            page.locator('#rename-version').click()
            page.locator('#param-length').fill('190.55')
            page.evaluate('window.watchVersionReadTimer=true')
            page.locator('#versions-file').set_input_files({'name':'slow-backup.json','mimeType':'application/json',
                                                           'buffer':backup([record('cable_comb','Obsolete',3)])})
            page.wait_for_function('()=>window.pendingDimensionReads.length===1&&window.versionReadTimers.size===1')
            dimensions={**wide['dimensions'],'parameters':{**wide['dimensions']['parameters'],'length':201.25}}
            page.locator('#dimensions-file').set_input_files({'name':'slow-dimensions.json','mimeType':'application/json','buffer':json.dumps(dimensions).encode()})
            page.wait_for_function('()=>window.pendingDimensionReads.length===2')
            before=snapshot(page)
            row,_=selected(page)
            assert row['name']=='Renamed' and snapshot(page)==before
            page.wait_for_function('()=>window.versionReadTimers.size===0')
            page.evaluate('()=>window.pendingDimensionReads[0]()')
            assert snapshot(page)==before
            expect(page.locator('#version-backup-message')).to_contain_text('Selected version exported')
            page.evaluate('()=>window.pendingDimensionReads[1]()')
            expect(page.locator('#param-length')).to_have_value('201.25')
            expect(page.locator('#undo-version')).to_be_enabled()
            page.locator('#undo-version').click()
            expect(page.locator('#param-length')).to_have_value('201.25')
            assert page.evaluate('key=>JSON.parse(localStorage.getItem(key))[0].name',KEY)==wide['name']
            page.locator('#revert-parameters').click()
            assert download(page,'download')[1]==fixtures['parts_tray'][2]
            assert download(page,'download-cad')[1]==fixtures['parts_tray'][0] and len(control['jobs'])==2
            cases.append({'check':'pending_reads','backup_deadlines_after_export':0,'late_backup_ignored':True,'dimensions_read_kept':True,'undo_kept':True})

        def active_cad_guards_exports_and_keeps_stop_focus_and_exact_files(page):
            control=setup(page)
            choose(page)
            page.locator('#param-length').fill('180.5')
            page.locator('#rebuild').click()
            expect(page.locator('#download-cad')).to_be_enabled()
            control['hold']=True
            page.locator('#download-cad').click()
            expect(page.locator('#stop-build')).to_be_focused()
            expect(page.locator('#export-version')).to_be_disabled()
            downloads=[]
            page.on('download',lambda file:downloads.append(file))
            page.locator('#export-version').dispatch_event('click')
            assert not downloads
            expect(page.locator('#stop-build')).to_be_focused()
            page.wait_for_timeout(50)
            assert len(control['waiting'])==1
            with page.expect_download() as event:
                control['waiting'].pop().fulfill(body=fixtures['parts_tray'][0],headers=headers(fixtures['parts_tray'][1]))
            assert Path(event.value.path()).read_bytes()==fixtures['parts_tray'][0]
            expect(page.locator('#export-version')).to_be_enabled()
            row,_=selected(page)
            assert row['name']==wide['name'] and len(control['jobs'])==2
            assert download(page,'download-cad')[1]==fixtures['parts_tray'][0]
            cases.append({'check':'busy','forced_exports':0,'stop_focus_preserved':True,'exact_cad':True,'native_jobs':2})

        def short_phone_keyboard_export_has_visible_focus_without_graphics(page):
            page.set_viewport_size({'width':390,'height':600})
            page.add_init_script('''const context=HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext=function(type,...args){return type.startsWith('webgl')?null:context.call(this,type,...args);};''')
            control=setup(page)
            choose(page,routing)
            page.locator('#param-length').fill('')
            button=page.locator('#export-version')
            button.focus()
            expect(button).to_be_focused()
            row,_=selected(page,keyboard=True)
            expect(button).to_be_focused()
            box=button.bounding_box()
            header=page.locator('.editor-header').bounding_box()
            assert box['height']>=44 and box['width']>=44 and box['y']>=header['y']+header['height']
            assert box['y']+box['height']<=600 and page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert row['name']==routing['name'] and page.locator('#param-length').input_value()=='' and not control['jobs']
            page.screenshot(path=str(ROOT/'review/cloud_selected_version_mobile.png'))
            page.locator('#revert-parameters').click()
            assert download(page,'download')[1]==(ASSETS/'models/parts_tray.stl').read_bytes()
            cases.append({'check':'mobile','button':box,'keyboard_focus_visible':True,'graphics_required':False,'native_jobs':0})

        tests=[invalid_draft_exports_other_model_without_touching_cached_files,
               portable_selected_file_restores_only_one_version_and_builds_exact_list_files,
               all_six_assembly_exports_use_canonical_inventory_without_switching_models,
               stale_selection_reads_fresh_storage_and_never_exports_all_records,
               storage_failures_preserve_data_and_read_only_exports_work_when_writes_fail,
               export_stops_pending_backups_keeps_dimensions_reads_and_preserves_undo,
               active_cad_guards_exports_and_keeps_stop_focus_and_exact_files,
               short_phone_keyboard_export_has_visible_focus_without_graphics]
        for test in tests:
            session=context()
            page=session.new_page()
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            try:
                print('START',test.__name__,flush=True)
                test(page)
                assert not errors,errors
                passed.append(test.__name__)
                print('PASS',test.__name__,flush=True)
            except Exception:
                failures.append({'check':test.__name__,'error':traceback.format_exc(),'browser_errors':errors})
                print('FAIL',test.__name__,failures[-1]['error'],flush=True)
            finally:
                session.close()
        browser.close()
    report={'endpoint':BASE,'passed':passed,'failures':failures,'cases':cases,
            'transport':'compiled production assets, real CAD fixtures, native downloads and cross-tab storage events'}
    (ROOT/'review/cloud_selected_version_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if failures:
        raise SystemExit(1)


if __name__=='__main__':
    main()
