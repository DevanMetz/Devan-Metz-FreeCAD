"""Load dimensions directly from real CAD/kit ZIPs with bounded, atomic imports."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import traceback
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

from playwright.sync_api import expect, sync_playwright
from browser_assets import ASSETS, OFFLINE_BASE, attach_assets
from verify_export_ui import fixture, headers

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = '--offline' in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5178')
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))

READS = """window.zipSlices=0; window.zipReadsByName={}; window.pendingZipReads=[]; window.holdZipReads=false;
const fileSlice=File.prototype.slice;
File.prototype.slice=function(...args){
  const blob=fileSlice.apply(this,args);
  if(!this.name.toLowerCase().endsWith('.zip')) return blob;
  window.zipSlices++;
  window.zipReadsByName[this.name]=(window.zipReadsByName[this.name]||0)+1;
  const arrayBuffer=blob.arrayBuffer.bind(blob);
  if(this.name==='unreadable.zip') blob.arrayBuffer=()=>Promise.reject(new DOMException('Controlled unreadable ZIP','NotReadableError'));
  else if(this.name.startsWith('slow') && window.holdZipReads)
    blob.arrayBuffer=()=>new Promise(resolve=>window.pendingZipReads.push(()=>arrayBuffer().then(resolve)));
  return blob;
};
window.copies=[];
Object.defineProperty(navigator,'clipboard',{value:{writeText:text=>{window.copies.push(text);return Promise.resolve();}}});
"""


def zip_records(records, compression=ZIP_DEFLATED):
    output = io.BytesIO()
    with ZipFile(output, 'w', compression=compression) as archive:
        for name, record in records:
            body = record if isinstance(record, (str, bytes)) else json.dumps(record)
            archive.writestr(name, body)
    return output.getvalue()


def main():
    names = ['parts_tray', 'cable_comb', 'soap_dish_assembly', 'sanding_assembly',
             'sliding_box_assembly', 'ruler_stop_assembly', 'strap_clamp_assembly', 'divider_joint_assembly']
    fixtures = {name: fixture(name) for name in names}
    archive, metadata, mesh = fixtures['parts_tray']
    catalog = {item['name']: item for item in json.loads((ASSETS/'catalog.json').read_text(encoding='utf-8'))['models']}
    csp = next(line.split(':',1)[1].strip() for line in (CLOUD/'public/_headers').read_text().splitlines() if 'Content-Security-Policy:' in line)
    passed, failures, cases, discarded_reads, pending_routes = [], [], [], [], {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        context = browser.new_context(viewport={'width':1440,'height':1080}, accept_downloads=True)
        context.set_default_timeout(20000)
        if OFFLINE:
            attach_assets(context)

        def setup(page, hold_module=False, fail_module=False, clock=False, fail_original=False):
            page.add_init_script(READS)
            if clock:
                page.clock.install()
            jobs, modules, waiting = [], [], []
            pending_routes[page] = waiting

            def module(route):
                modules.append(route.request.url)
                if hold_module:
                    waiting.append(route)
                elif fail_module:
                    route.abort()
                else:
                    route.fallback()

            page.route('**/assets/zip-*.js' if OFFLINE else '**/web/zip.js*', module)

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload)
                body, details, preview = fixtures[payload['model']]
                assert payload['parameters'] == details['parameters'], payload
                if payload.get('format') == 'cad':
                    route.fulfill(body=body, headers=headers(details))
                else:
                    details = {**details, 'format':'stl', 'file_sha256':details['mesh_sha256']}
                    route.fulfill(body=preview, headers=headers(details, 'model/stl'))

            page.route('**/api/generate', generate)
            if fail_original:
                page.route('**/models/parts_tray.stl', lambda route: route.fulfill(status=503,body='Controlled missing preview'))
            if OFFLINE:
                page.route(BASE+'/', lambda route: route.fulfill(body=(ASSETS/'index.html').read_bytes(), headers={'Content-Type':'text/html', 'Content-Security-Policy':csp}))
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length===53")
            page.locator('[data-model="parts_tray"]').click()
            if fail_original:
                expect(page.locator('#retry-original')).to_be_visible()
            else:
                ready(page)
            page.locator('.saved-dimensions summary').click()
            assert not modules, 'Opening the editor loaded the optional ZIP module'
            return jobs, modules, waiting

        def ready(page):
            expect(page.locator('#download-cad')).to_be_enabled()

        def select(page, body=archive, name='dimensions.zip', chooser=False):
            chosen = {'name':name, 'mimeType':'application/zip', 'buffer':body}
            if chooser:
                with page.expect_file_chooser() as event:
                    page.locator('#load-dimensions').click()
                event.value.set_files(chosen)
            else:
                page.locator('#dimensions-file').set_input_files(chosen)

        def select_json(page, length=170.25):
            body = json.dumps({'model':'parts_tray','units':'mm','parameters':{'length':length}}).encode()
            page.locator('#dimensions-file').set_input_files({'name':'parameters.json','mimeType':'application/json','buffer':body})
            expect(page.locator('#param-length')).to_have_value(str(length))

        def loaded(page, matches=False):
            expect(page.locator('#form-message')).to_contain_text('match the verified' if matches else 'loaded. Update')
            expect(page.locator('#dimensions-error')).to_be_hidden()

        def download(page, button):
            with page.expect_download() as event:
                page.locator('#'+button).click()
            return event.value.suggested_filename, Path(event.value.path()).read_bytes()

        def custom(page):
            select(page)
            loaded(page)
            page.locator('#rebuild').click()
            ready(page)

        def release_file(page):
            page.evaluate('''() => {window.holdZipReads=false; window.pendingZipReads.splice(0).forEach(release=>release());}''')
            page.evaluate('() => new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')

        def read_count(page, name):
            return page.evaluate('name=>window.zipReadsByName[name]||0', name)

        def release_module(waiting):
            for route in waiting[:]:
                if OFFLINE:
                    route.fulfill(body=(ASSETS/'assets'/Path(route.request.url).name).read_bytes(), content_type='text/javascript')
                else:
                    route.fulfill(response=route.fetch())
                waiting.remove(route)

        def real_zip_chooser_builds_exact_custom_files(page):
            jobs, modules, _ = setup(page)
            assert '.zip' in page.locator('#dimensions-file').get_attribute('accept')
            assert 'CAD or kit ZIP' in page.locator('#dimensions-file').get_attribute('aria-label')
            select(page, chooser=True)
            loaded(page)
            expect(page.locator('#param-length')).to_have_value('180.5')
            expect(page.locator('#param-length')).to_be_focused()
            assert page.locator('#model-size').inner_text() == '150 × 100 × 24'
            assert page.locator('#download').is_disabled() and not jobs and len(modules)==1
            page.locator('#rebuild').click()
            ready(page)
            filename, body = download(page,'download')
            assert '-180.5x100x24mm-' in filename and body==mesh
            filename, body = download(page,'download-cad')
            assert '-180.5x100x24mm-' in filename and body==archive
            assert download(page,'download-cad')[1]==archive
            assert [job.get('format','stl') for job in jobs]==['stl','cad']
            cases.append({'check':'real_zip','zip_bytes':len(archive),'mesh_sha256':hashlib.sha256(mesh).hexdigest(),'jobs':['stl','cad']})
            page.screenshot(path=str(ROOT/'review/cloud_zip_dimensions_desktop.png'))

        def matching_zip_repairs_invalid_drafts_and_keeps_cached_files(page):
            jobs, modules, _ = setup(page)
            custom(page)
            assert download(page,'download-cad')[1]==archive
            page.locator('#param-length').fill('')
            select(page)
            loaded(page,matches=True)
            assert download(page,'download')[1]==mesh and download(page,'download-cad')[1]==archive
            assert len(jobs)==2 and len(modules)==1

        def list_zip_switches_models_and_restores_history(page):
            jobs, _, _ = setup(page)
            page.locator('#param-length').fill('190.55')
            select(page,fixtures['cable_comb'][0],'cable_comb.ZIP')
            loaded(page)
            expect(page.locator('#param-cable_diameters')).to_have_value('2, 3.5, 9')
            assert json.loads(page.evaluate("new URL(location.href).searchParams.get('p')"))['cable_diameters']==[2,3.5,9]
            page.go_back()
            expect(page.locator('#param-length')).to_have_value('190.55')
            page.go_forward()
            expect(page.locator('#param-cable_diameters')).to_have_value('2, 3.5, 9')
            page.locator('#rebuild').click()
            ready(page)
            assert download(page,'download')[1]==fixtures['cable_comb'][2]
            assert download(page,'download-cad')[1]==fixtures['cable_comb'][0]
            assert len(jobs)==2

        def all_six_kit_zips_load_canonical_inventories_without_building(page):
            jobs, _, _ = setup(page)
            checked=[]
            for name in names[2:]:
                select(page,fixtures[name][0],name+'.zip')
                expect(page.locator('#model-title')).to_have_text(catalog[name]['title'])
                expect(page.locator('#form-message')).to_contain_text('Saved dimensions')
                assert page.locator('#download').is_hidden()
                if not page.locator('.saved-dimensions').evaluate('element=>element.open'):
                    page.locator('.saved-dimensions summary').click()
                record=json.loads(download(page,'save-dimensions')[1])
                assert record['parameters']==fixtures[name][1]['parameters'] and record['kit']==catalog[name]['kit']
                assert page.locator('#part-links button').count()==len(catalog[name]['kit'])
                checked.append(name)
            record={**fixtures[names[-1]][1], 'kit':[{'model':'wrong','quantity':99}], 'bounds_mm':[1,1,1], 'mesh_sha256':'bad'}
            select(page,zip_records([('parameters.json',record)]))
            expect(page.locator('#dimensions-error')).to_be_hidden()
            assert json.loads(download(page,'save-dimensions')[1])['kit']==catalog[names[-1]]['kit']
            assert not jobs
            cases.append({'check':'kits','models':checked,'native_jobs':0})

        def malformed_zips_preserve_current_model_and_exact_cached_files(page):
            jobs, _, _ = setup(page)
            custom(page)
            assert download(page,'download-cad')[1]==archive
            stored=zip_records([('parameters.json',metadata)],ZIP_STORED)
            corrupt=stored.replace(b'180.5',b'190.5',1)
            assert corrupt!=stored
            invalid=[('not-zip.zip',b'not a ZIP'),('truncated.zip',archive[:-7]),('crc.zip',corrupt),
                     ('nested.zip',zip_records([('nested/parameters.json',metadata)])),
                     ('duplicate.zip',zip_records([('parameters.json',metadata),('dimensions.json',metadata)]).replace(b'dimensions.json',b'parameters.json')),
                     ('unknown.zip',zip_records([('parameters.json',{**metadata,'model':'missing'})])),
                     ('range.zip',zip_records([('parameters.json',{**metadata,'parameters':{'length':251}})])),
                     ('encoding.zip',zip_records([('parameters.json',b'\xff\xfe{')])),
                     ('unreadable.zip',archive)]
            for name,body in invalid:
                select(page,body,name)
                expect(page.locator('#dimensions-error')).to_be_visible()
                assert page.locator('#param-length').input_value()=='180.5' and page.locator('#model-title').inner_text()==catalog['parts_tray']['title']
                assert download(page,'download')[1]==mesh and download(page,'download-cad')[1]==archive
            assert len(jobs)==2
            cases.append({'check':'malformed','rejected':[name for name,_ in invalid],'jobs':['stl','cad']})

        def zip_limits_preserve_measurements_and_json_recovery(page):
            jobs, _, _ = setup(page)
            page.evaluate("""() => {const size=Object.getOwnPropertyDescriptor(Blob.prototype,'size').get;
              Object.defineProperty(File.prototype,'size',{get(){return this.name==='oversized.zip'?8*1024*1024+1:size.call(this);}}); }""")
            select(page,archive,'oversized.zip')
            expect(page.locator('#dimensions-error')).to_contain_text('exceeds 8 MiB')
            assert page.evaluate('window.zipSlices')==0
            invalid=[(zip_records([('parameters.json',json.dumps(metadata)+' '*16384)]),'record exceeds 16 KiB'),
                     (zip_records([('parameters.json',metadata)]+[(f'file{i}','x') for i in range(128)]),'too many files'),
                     (zip_records([('parameters.json',metadata),('large.txt',' '*(24*1024*1024))]),'contents exceed 24 MiB')]
            for body,error in invalid:
                select(page,body)
                expect(page.locator('#dimensions-error')).to_contain_text(error)
                assert page.locator('#param-length').input_value()=='150' and page.locator('#download').is_enabled()
            select_json(page)
            assert not jobs

        def newer_edit_save_copy_reset_and_revert_supersede_held_zip_reads(page):
            jobs, _, _ = setup(page)
            custom(page)
            assert download(page,'download-cad')[1]==archive
            for action in ('edit','save','copy','reset','revert'):
                select(page)
                loaded(page,matches=True)
                page.locator('#param-length').fill('190.55')
                page.evaluate('window.holdZipReads=true')
                select(page,fixtures['cable_comb'][0],'slow-'+action+'.zip')
                page.wait_for_function('() => window.pendingZipReads.length>0')
                before = read_count(page,'slow-'+action+'.zip')
                if action=='edit':
                    page.locator('#param-length').fill('200.25')
                elif action=='save':
                    assert json.loads(download(page,'save-dimensions')[1])['parameters']['length']==190.55
                elif action=='copy':
                    page.locator('#share').click()
                    expect(page.locator('#share-message')).to_contain_text('Link copied')
                else:
                    page.locator('#reset-parameters' if action=='reset' else '#revert-parameters').click()
                expected={'edit':'200.25','save':'190.55','copy':'190.55','reset':'150','revert':'180.5'}[action]
                page.locator('#param-width').focus()
                release_file(page)
                after = read_count(page,'slow-'+action+'.zip')
                assert before == after == 1, (action,before,after)
                discarded_reads.append({'action':action,'reads_before_discard':before,'reads_after_late_bytes':after})
                expect(page.locator('#param-width')).to_be_focused()
                assert page.locator('#param-length').input_value()==expected
                assert page.locator('#model-title').inner_text()==catalog['parts_tray']['title']
                expect(page.locator('#dimensions-error')).to_be_hidden()
            assert len(jobs)==2 and download(page,'download')[1]==mesh and download(page,'download-cad')[1]==archive

        def discarded_zip_reads_stop_for_new_files_builds_retry_and_close(page):
            for action in ['new_file','close','build','retry','field_revert']:
                other = page if action=='new_file' else context.new_page()
                errors=[]
                other.on('pageerror',lambda error:errors.append(str(error)))
                try:
                    jobs,_,_=setup(other,fail_original=action=='retry')
                    if action!='retry':
                        custom(other)
                        assert download(other,'download-cad')[1]==archive
                    if action=='build':
                        select_json(other,180.5)
                        loaded(other,matches=True)
                    if action!='build':
                        other.locator('#param-length').fill('190.55')
                    other.evaluate('window.holdZipReads=true')
                    name='slow-'+action+'.zip'
                    select(other,fixtures['cable_comb'][0],name)
                    other.wait_for_function('() => window.pendingZipReads.length>0')
                    before=read_count(other,name)
                    if action=='new_file':
                        select_json(other,180.5)
                        loaded(other,matches=True)
                    elif action=='close':
                        other.locator('#close-editor').click()
                        other.wait_for_function("() => !document.querySelector('#editor').open")
                        select(other,name='late-closed.zip')
                        assert read_count(other,'late-closed.zip')==0
                    elif action=='build':
                        other.locator('#rebuild').click()
                        ready(other)
                    elif action=='retry':
                        other.locator('#retry-original').click()
                        expect(other.locator('#retry-original')).to_be_visible()
                    else:
                        other.locator('#revert-field-length').click()
                    release_file(other)
                    after=read_count(other,name)
                    assert before==after==1,(action,before,after)
                    assert other.locator('#model-title').inner_text()==catalog['parts_tray']['title']
                    expected='190.55' if action in ['close','retry'] else '180.5'
                    expect(other.locator('#param-length')).to_have_value(expected)
                    assert not errors and other.locator('#dimensions-error').is_hidden()
                    if action not in ['close','retry']:
                        assert download(other,'download')[1]==mesh and download(other,'download-cad')[1]==archive
                    assert len(jobs)==(0 if action=='retry' else 2),(action,jobs)
                    discarded_reads.append({'action':action,'reads_before_discard':before,'reads_after_late_bytes':after,
                                            'native_jobs':len(jobs),'late_closed_chooser_reads':0 if action=='close' else None})
                finally:
                    if other is not page:
                        other.close()

        def zip_read_deadline_and_newer_json_discard_late_metadata(page):
            jobs, _, _ = setup(page,clock=True)
            try:
                page.clock.pause_at(page.evaluate('Date.now()')+100)
                page.evaluate('window.holdZipReads=true')
                select(page,name='slow-deadline.zip')
                page.wait_for_function('() => window.pendingZipReads.length>0')
                before = read_count(page,'slow-deadline.zip')
                page.clock.fast_forward(14999)
                expect(page.locator('#form-message')).to_have_text('Loading saved dimensions…')
                page.clock.fast_forward(2)
                expect(page.locator('#dimensions-error')).to_contain_text('took too long')
                page.clock.resume()
                select_json(page)
                page.locator('#param-width').focus()
                release_file(page)
                after = read_count(page,'slow-deadline.zip')
                assert before==after==1
                discarded_reads.append({'action':'deadline','reads_before_discard':before,'reads_after_late_bytes':after})
                expect(page.locator('#param-width')).to_be_focused()
                assert page.locator('#param-length').input_value()=='170.25' and not jobs
            finally:
                page.clock.resume()

        def pending_cad_ignores_zip_selection_and_keeps_its_exact_download(page):
            jobs, _, _ = setup(page)
            custom(page)
            waiting=[]
            page.route('**/api/generate',lambda route: waiting.append(route))
            page.locator('#download-cad').click()
            expect(page.locator('#stop-build')).to_be_visible()
            slices=page.evaluate('window.zipSlices')
            select(page,fixtures['cable_comb'][0])
            assert page.evaluate('window.zipSlices')==slices and page.locator('#param-length').input_value()=='180.5'
            assert page.locator('#load-dimensions').is_disabled()
            assert len(waiting)==1
            jobs.append(waiting[0].request.post_data_json)
            with page.expect_download() as event:
                waiting.pop().fulfill(body=archive,headers=headers(metadata))
            assert Path(event.value.path()).read_bytes()==archive
            assert download(page,'download-cad')[1]==archive and len(jobs)==2

        def zip_loading_and_verified_downloads_work_without_graphics(page):
            page.add_init_script("""const context=HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext=function(type,...args){return type.startsWith('webgl')?null:context.call(this,type,...args);};""")
            jobs, _, _ = setup(page)
            custom(page)
            assert page.locator('#fallback-image').is_visible()
            assert download(page,'download')[1]==mesh and download(page,'download-cad')[1]==archive and len(jobs)==2

        def unavailable_or_delayed_zip_reader_keeps_json_and_newer_actions(page):
            jobs, modules, waiting = setup(page,hold_module=True,clock=True)
            try:
                page.clock.pause_at(page.evaluate('Date.now()')+100)
                select(page)
                page.wait_for_function("() => document.querySelector('#form-message').textContent==='Loading saved dimensions…'")
                assert len(waiting)==1
                page.clock.fast_forward(15001)
                expect(page.locator('#dimensions-error')).to_contain_text('took too long')
                page.clock.resume()
                select_json(page)
                page.locator('#param-width').focus()
                release_module(waiting)
                expect(page.locator('#param-width')).to_be_focused()
                assert page.locator('#param-length').input_value()=='170.25' and not jobs and len(modules)==1
            finally:
                page.clock.resume()
            for mode in ('module','decompression'):
                other=context.new_page()
                try:
                    if mode=='decompression':
                        other.add_init_script('window.DecompressionStream=undefined')
                    other_jobs, _, _ = setup(other,fail_module=mode=='module')
                    select(other)
                    expect(other.locator('#dimensions-error')).to_contain_text('ZIP reading is unavailable')
                    assert other.locator('#download').is_enabled()
                    select_json(other)
                    expect(other.locator('#dimensions-error')).to_be_hidden()
                    assert not other_jobs
                finally:
                    other.close()

        def mobile_keyboard_zip_chooser_keeps_visible_focus_and_exact_files(page):
            page.set_viewport_size({'width':390,'height':600})
            jobs, _, _ = setup(page)
            page.bring_to_front()
            button=page.locator('#load-dimensions')
            button.focus()
            expect(button).to_be_focused()
            with page.expect_file_chooser() as event:
                button.press('Enter')
            event.value.set_files({'name':'tray-cad.zip','mimeType':'application/zip','buffer':archive})
            loaded(page)
            expect(page.locator('#param-length')).to_be_focused()
            rect=page.locator('#param-length').bounding_box()
            assert rect['y']>=0 and rect['y']+rect['height']<=600.01
            page.locator('#rebuild').focus()
            page.keyboard.press('Enter')
            ready(page)
            filename,body=download(page,'download')
            assert '-180.5x100x24mm-' in filename and body==mesh
            filename,body=download(page,'download-cad')
            assert '-180.5x100x24mm-' in filename and body==archive
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert download(page,'download-cad')[1]==archive and len(jobs)==2
            cases.append({'check':'mobile','viewport':{'width':390,'height':600},'focused_input':rect,'jobs':['stl','cad']})
            page.screenshot(path=str(ROOT/'review/cloud_zip_dimensions_mobile.png'))

        tests = [real_zip_chooser_builds_exact_custom_files,matching_zip_repairs_invalid_drafts_and_keeps_cached_files,
                 list_zip_switches_models_and_restores_history,all_six_kit_zips_load_canonical_inventories_without_building,
                 malformed_zips_preserve_current_model_and_exact_cached_files,zip_limits_preserve_measurements_and_json_recovery,
                 newer_edit_save_copy_reset_and_revert_supersede_held_zip_reads,zip_read_deadline_and_newer_json_discard_late_metadata,
                 discarded_zip_reads_stop_for_new_files_builds_retry_and_close,
                 pending_cad_ignores_zip_selection_and_keeps_its_exact_download,zip_loading_and_verified_downloads_work_without_graphics,
                 unavailable_or_delayed_zip_reader_keeps_json_and_newer_actions,mobile_keyboard_zip_chooser_keeps_visible_focus_and_exact_files]
        for test in tests:
            page=context.new_page()
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            try:
                print('START',test.__name__,flush=True)
                test(page)
                assert not errors,errors
                passed.append(test.__name__)
                print('PASS',test.__name__,flush=True)
            except Exception:
                failures.append({'check':test.__name__,'error':traceback.format_exc()})
                print('FAIL',test.__name__,failures[-1]['error'],flush=True)
            finally:
                release_module(pending_routes.get(page,[]))
                page.close()
        browser.close()
    report={'endpoint':BASE,'passed':passed,'failures':failures,'cases':cases,'discarded_reads':discarded_reads,
            'archive_sha256':hashlib.sha256(archive).hexdigest(),'transport':'compiled assets and real exported CAD ZIP fixtures'}
    (ROOT/'review/cloud_zip_dimensions_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if failures:
        raise SystemExit(1)


if __name__=='__main__':
    main()
