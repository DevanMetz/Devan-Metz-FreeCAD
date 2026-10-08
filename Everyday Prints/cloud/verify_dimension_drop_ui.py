"""Drop real dimensions JSON and CAD/kit ZIPs without losing verified downloads."""
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

from playwright.sync_api import expect, sync_playwright
from browser_assets import ASSETS, OFFLINE_BASE, attach_assets
from verify_export_ui import fixture, headers
from verify_zip_dimensions_ui import READS

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = '--offline' in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5178')
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT.parent / '.cad-cache/browsers'))

DROP = """arg => {
  const data = new DataTransfer();
  for (const file of arg.files) {
    const bytes = file.size === undefined ? Uint8Array.from(atob(file.body), c => c.charCodeAt(0)) : new Uint8Array(file.size);
    data.items.add(new File([bytes], file.name, {type:file.mime}));
  }
  if (arg.text) data.setData('text/plain', arg.text);
  const target = document.querySelector(arg.target);
  const event = new DragEvent(arg.event, {bubbles:true, cancelable:true, dataTransfer:data,
    relatedTarget:arg.related ? document.querySelector(arg.related) : null});
  target.dispatchEvent(event);
  return {prevented:event.defaultPrevented, effect:data.dropEffect,
    hovering:document.querySelector('#dimension-drop').classList.contains('is-dragging')};
}"""


def main():
    fixtures = {name: fixture(name) for name in ('parts_tray', 'cable_comb', 'soap_dish_assembly')}
    archive, metadata, mesh = fixtures['parts_tray']
    csp = next(line.split(':', 1)[1].strip() for line in (CLOUD/'public/_headers').read_text().splitlines() if 'Content-Security-Policy:' in line)
    passed, failures, cases, pending_routes = [], [], [], {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        context = browser.new_context(viewport={'width':1440, 'height':1080}, accept_downloads=True)
        context.set_default_timeout(20000)
        if OFFLINE:
            attach_assets(context)

        def setup(page):
            page.add_init_script(READS + """window.jsonReads=0;
              const readText=File.prototype.text;
              File.prototype.text=function(){window.jsonReads++;return readText.call(this);};""")
            jobs = []
            pending_routes[page] = []

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload)
                body, details, preview = fixtures[payload['model']]
                assert payload['parameters'] == details['parameters'], payload
                if payload.get('format') == 'cad':
                    route.fulfill(body=body, headers=headers(details))
                else:
                    assert preview is not None
                    route.fulfill(body=preview, headers=headers({**details, 'format':'stl', 'file_sha256':details['mesh_sha256']}, 'model/stl'))

            page.route('**/api/generate', generate)
            if OFFLINE:
                page.route(BASE+'/', lambda route: route.fulfill(body=(ASSETS/'index.html').read_bytes(), headers={'Content-Type':'text/html', 'Content-Security-Policy':csp}))
            page.goto(BASE)
            page.locator('[data-model="parts_tray"]').click()
            ready(page)
            page.locator('.saved-dimensions summary').click()
            return jobs

        def ready(page):
            expect(page.locator('#download-cad')).to_be_enabled()

        def chosen(body=archive, name='tray-cad.zip', mime='application/zip', size=None):
            return {'name':name, 'mime':mime, **({'size':size} if size is not None else {'body':base64.b64encode(body).decode()})}

        def dispatch(page, files=None, event='drop', target='#dimension-drop', text=None, related=None):
            return page.evaluate(DROP, {'files':files if files is not None else [chosen()],
                                       'event':event, 'target':target, 'text':text, 'related':related})

        def drop(page, body=archive, name='tray-cad.zip', mime='application/zip'):
            assert dispatch(page, [chosen(body, name, mime)]) == {'prevented':True, 'effect':'none', 'hovering':False}

        def loaded(page, matches=False):
            expect(page.locator('#form-message')).to_contain_text('match the verified' if matches else 'loaded. Update')
            expect(page.locator('#dimensions-error')).to_be_hidden()

        def download(page, button):
            with page.expect_download() as event:
                page.locator('#'+button).click()
            return event.value.suggested_filename, Path(event.value.path()).read_bytes()

        def custom(page):
            drop(page)
            loaded(page)
            page.locator('#rebuild').click()
            ready(page)

        def retained(page, jobs):
            assert download(page, 'download')[1] == mesh
            assert download(page, 'download-cad')[1] == archive
            assert len(jobs) == 2

        def json_file(length=180.5):
            return json.dumps({'model':'parts_tray', 'units':'mm', 'parameters':{'length':length}}).encode()

        def chooser(page, body=json_file(), name='parameters.json', mime='application/json'):
            page.bring_to_front()
            button = page.locator('#load-dimensions')
            button.focus()
            with page.expect_file_chooser() as event:
                button.press('Enter')
            event.value.set_files({'name':name, 'mimeType':mime, 'buffer':body})

        def release(page):
            page.evaluate('''() => {window.holdZipReads=false;window.pendingZipReads.splice(0).forEach(done=>done());}''')
            page.evaluate('() => new Promise(done=>requestAnimationFrame(()=>requestAnimationFrame(done)))')

        def desktop_zip_drop_builds_exact_downloads(page):
            jobs = setup(page)
            page.locator('#dimension-drop').scroll_into_view_if_needed()
            page.evaluate('''() => {
              window.dimensionDragEvents=[];
              for (const type of ['dragenter','dragover','dragleave','drop']) document.addEventListener(type,event=>{
                if (event.isTrusted) window.dimensionDragEvents.push({type, trusted:event.isTrusted,
                  types:[...event.dataTransfer.types], effect:event.dataTransfer.dropEffect,
                  files:[...event.dataTransfer.files].map(file=>({name:file.name,size:file.size}))});
              });
            }''')
            # Supply an on-disk ZIP to Chromium's trusted native file-drag pipeline.
            session=context.new_cdp_session(page)
            rect=page.locator('#dimension-drop-help').bounding_box()
            drag={'x':rect['x']+rect['width']/2,'y':rect['y']+rect['height']/2,
                  'data':{'items':[],'files':[str(ROOT/'review/cloud_export_samples/parts_tray/download.zip')],'dragOperationsMask':1}}
            try:
                for event in ('dragEnter','dragOver'):
                    session.send('Input.dispatchDragEvent',{'type':event,**drag})
                assert page.locator('#dimension-drop').evaluate("node=>node.classList.contains('is-dragging')")
                assert not page.evaluate('window.zipSlices')
                page.screenshot(path=str(ROOT/'review/cloud_dimension_drop_desktop.png'))
                # CDP dragCancel ends the source; leaving the target delivers dragleave.
                outside=page.locator('#param-length').bounding_box()
                session.send('Input.dispatchDragEvent',{'type':'dragOver',**drag,
                             'x':outside['x']+outside['width']/2,'y':outside['y']+outside['height']/2})
                assert not page.locator('#dimension-drop').evaluate("node=>node.classList.contains('is-dragging')")
                session.send('Input.dispatchDragEvent',{'type':'dragCancel',**drag})
                assert not page.locator('#dimension-drop').evaluate("node=>node.classList.contains('is-dragging')")
                for event in ('dragEnter','dragOver','drop'):
                    session.send('Input.dispatchDragEvent',{'type':event,**drag})
            finally:
                session.detach()
            loaded(page)
            native_events=page.evaluate('window.dimensionDragEvents')
            assert any(event['type']=='drop' and event['trusted'] and event['files']==[{'name':'download.zip','size':len(archive)}] for event in native_events),native_events
            assert any(event['type']=='dragover' and event['effect']=='copy' for event in native_events),native_events
            assert not page.locator('#dimension-drop').evaluate("node=>node.classList.contains('is-dragging')")
            expect(page.locator('#param-length')).to_have_value('180.5')
            expect(page.locator('#param-length')).to_be_focused()
            assert not jobs and page.locator('#download').is_disabled()
            page.locator('#rebuild').click()
            ready(page)
            for button, expected in [('download',mesh), ('download-cad',archive)]:
                filename, body = download(page, button)
                assert '-180.5x100x24mm-' in filename and body == expected
            retained(page, jobs)
            cases.append({'check':'desktop', 'zip_bytes':len(archive), 'jobs':['stl','cad'], 'mesh_sha256':hashlib.sha256(mesh).hexdigest(), 'native_drag_events':native_events})

        def json_drop_repairs_drafts_switches_models_and_history(page):
            jobs = setup(page)
            custom(page)
            assert download(page, 'download-cad')[1] == archive
            page.locator('#param-length').fill('')
            drop(page, json_file(), 'dimensions.json', 'application/json')
            loaded(page, matches=True)
            retained(page, jobs)
            record = fixtures['cable_comb'][1]
            drop(page, json.dumps(record).encode(), 'comb.json', 'application/json')
            expect(page.locator('#param-cable_diameters')).to_have_value('2, 3.5, 9')
            expect(page.locator('#form-message')).to_contain_text('Saved dimensions')
            assert 'model=cable_comb' in page.url and len(jobs)==2
            page.go_back()
            ready(page)
            expect(page.locator('#param-length')).to_have_value('180.5')
            retained(page, jobs)

        def kit_drop_loads_canonical_inventory_without_a_job(page):
            jobs = setup(page)
            body, details, _ = fixtures['soap_dish_assembly']
            drop(page, body, 'soap-kit.zip')
            expect(page.locator('#form-message')).to_contain_text('Saved dimensions')
            expect(page.locator('#param-length')).to_have_value(str(details['parameters']['length']))
            assert 'model=soap_dish_assembly' in page.url and not jobs
            kit = next(item for item in json.loads((ASSETS/'catalog.json').read_text())['models'] if item['name']=='soap_dish_assembly')['kit']
            assert page.locator('#part-links button').count() == len(kit)
            cases.append({'check':'kit', 'model':'soap_dish_assembly', 'native_jobs':0})

        def unsupported_and_multiple_drops_preserve_verified_files(page):
            jobs = setup(page)
            custom(page)
            assert download(page,'download-cad')[1] == archive
            drop(page,b'solid not-dimensions\nendsolid not-dimensions','tray.stl','model/stl')
            expect(page.locator('#dimensions-error')).to_contain_text('not valid JSON')
            retained(page,jobs)
            page.evaluate('window.holdZipReads=true')
            drop(page,fixtures['cable_comb'][0],'slow-comb.zip')
            page.wait_for_function('() => window.pendingZipReads.length>0')
            reads = page.evaluate('window.jsonReads+window.zipSlices')
            result = dispatch(page,[chosen(), chosen(json_file(),'measurements.json','application/json')])
            assert result['prevented'] and not result['hovering']
            expect(page.locator('#dimensions-error')).to_contain_text('Drop one')
            assert page.evaluate('window.jsonReads+window.zipSlices') == reads
            release(page)
            expect(page.locator('#param-length')).to_have_value('180.5')
            expect(page.locator('#dimensions-error')).to_contain_text('Drop one')
            retained(page,jobs)
            chooser(page)
            loaded(page,matches=True)
            retained(page,jobs)

        def oversized_and_corrupt_drops_recover_with_the_chooser(page):
            jobs = setup(page)
            custom(page)
            assert download(page,'download-cad')[1] == archive
            reads = page.evaluate('window.jsonReads+window.zipSlices')
            for name,mime,size,message in [('huge.json','application/json',16385,'exceeds 16 KiB'),
                                            ('huge.zip','application/zip',8*1024*1024+1,'exceeds 8 MiB')]:
                assert dispatch(page,[chosen(name=name,mime=mime,size=size)])['prevented']
                expect(page.locator('#dimensions-error')).to_contain_text(message)
                assert page.evaluate('window.jsonReads+window.zipSlices') == reads
                retained(page,jobs)
            drop(page,archive[:-5],'truncated.zip')
            expect(page.locator('#dimensions-error')).to_contain_text('could not be verified')
            retained(page,jobs)
            chooser(page,archive,'tray-cad.zip','application/zip')
            loaded(page,matches=True)
            retained(page,jobs)

        def busy_cad_drop_preserves_the_in_flight_download(page):
            jobs = setup(page)
            custom(page)
            waiting = pending_routes[page]
            def hold(route):
                jobs.append(route.request.post_data_json)
                waiting.append(route)
            page.route('**/api/generate',hold)
            page.locator('#download-cad').click()
            expect(page.locator('#stop-build')).to_be_focused()
            assert len(waiting)==1 and len(jobs)==2
            reads = page.evaluate('window.jsonReads+window.zipSlices')
            hover = dispatch(page,event='dragover')
            assert hover['prevented'] and hover['effect']=='none' and not hover['hovering']
            drop(page,fixtures['cable_comb'][0],'comb.zip')
            expect(page.locator('#form-message')).to_contain_text('Finish the current build')
            expect(page.locator('#stop-build')).to_be_focused()
            assert page.evaluate('window.jsonReads+window.zipSlices') == reads
            expect(page.locator('#param-length')).to_have_value('180.5')
            with page.expect_download() as event:
                waiting.pop().fulfill(body=archive,headers=headers(metadata))
            assert Path(event.value.path()).read_bytes()==archive
            retained(page,jobs)
            cases.append({'check':'busy_cad', 'jobs':['stl','cad'], 'focus':'stop-build'})

        def newer_actions_supersede_held_drops(page):
            for action in ('edit','chooser','close'):
                other=page if action=='edit' else context.new_page()
                try:
                    jobs=setup(other)
                    custom(other)
                    assert download(other,'download-cad')[1]==archive
                    other.evaluate('window.holdZipReads=true')
                    drop(other,fixtures['cable_comb'][0],'slow-comb.zip')
                    other.wait_for_function('() => window.pendingZipReads.length>0')
                    if action=='edit':
                        other.locator('#param-length').fill('171.25')
                        other.locator('#param-width').focus()
                    elif action=='chooser':
                        chooser(other)
                        loaded(other,matches=True)
                        other.locator('#param-width').focus()
                    else:
                        other.locator('#close-editor').click()
                    release(other)
                    if action=='edit':
                        expect(other.locator('#param-length')).to_have_value('171.25')
                        expect(other.locator('#param-width')).to_be_focused()
                        other.locator('#revert-parameters').click()
                    elif action=='chooser':
                        expect(other.locator('#param-width')).to_be_focused()
                    else:
                        expect(other.locator('#editor')).not_to_be_visible()
                        other.wait_for_function("() => !new URL(location.href).searchParams.has('model')")
                        other.go_forward()
                        ready(other)
                    expect(other.locator('#param-length')).to_have_value('180.5')
                    retained(other,jobs)
                finally:
                    if other is not page:
                        other.close()

        def file_hover_text_drag_and_editor_close_leave_no_drop_state(page):
            jobs=setup(page)
            initial=page.locator('#param-length').input_value()
            hover=dispatch(page,event='dragenter')
            assert hover['prevented'] and hover['hovering']
            nested=dispatch(page,event='dragleave',target='#load-dimensions',related='#save-dimensions')
            assert nested['hovering']
            assert not dispatch(page,event='dragleave')['hovering']
            for event in ('dragenter','dragover','drop'):
                result=dispatch(page,files=[],event=event,text='Some measurements')
                assert not result['prevented'] and not result['hovering']
            assert not page.evaluate('window.jsonReads+window.zipSlices') and not jobs
            expect(page.locator('#param-length')).to_have_value(initial)
            dispatch(page,event='dragenter')
            page.locator('#close-editor').click()
            page.wait_for_function("() => !document.querySelector('#dimension-drop').classList.contains('is-dragging')")
            page.locator('[data-model="parts_tray"]').click()
            ready(page)
            assert not page.locator('#dimension-drop').evaluate("node=>node.classList.contains('is-dragging')")
            dispatch(page,event='dragenter')
            page.evaluate("document.dispatchEvent(new DragEvent('dragend',{bubbles:true}))")
            assert not page.locator('#dimension-drop').evaluate("node=>node.classList.contains('is-dragging')")

        def mobile_keyboard_and_graphics_fallback_keep_the_load_action(page):
            page.set_viewport_size({'width':390,'height':600})
            page.add_init_script("""const getContext=HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext=function(type,...args){return type.startsWith('webgl')?null:getContext.call(this,type,...args);};""")
            jobs=setup(page)
            button=page.locator('#load-dimensions')
            assert button.bounding_box()['height']>=44
            assert 'dimension-drop-help' in button.get_attribute('aria-describedby')
            chooser(page,archive,'tray-cad.zip','application/zip')
            loaded(page)
            expect(page.locator('#param-length')).to_be_focused()
            page.locator('#rebuild').click()
            ready(page)
            assert page.locator('#fallback-image').is_visible()
            retained(page,jobs)
            drop(page,json_file(),'measurements.json','application/json')
            loaded(page,matches=True)
            retained(page,jobs)
            button.focus()
            expect(button).to_be_focused()
            rect=button.bounding_box()
            assert rect['y']>=0 and rect['y']+rect['height']<=600.01
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(ROOT/'review/cloud_dimension_drop_mobile.png'))
            cases.append({'check':'mobile', 'viewport':{'width':390,'height':600}, 'button':rect, 'jobs':['stl','cad']})

        tests=[desktop_zip_drop_builds_exact_downloads,json_drop_repairs_drafts_switches_models_and_history,
               kit_drop_loads_canonical_inventory_without_a_job,unsupported_and_multiple_drops_preserve_verified_files,
               oversized_and_corrupt_drops_recover_with_the_chooser,busy_cad_drop_preserves_the_in_flight_download,
               newer_actions_supersede_held_drops,file_hover_text_drag_and_editor_close_leave_no_drop_state,
               mobile_keyboard_and_graphics_fallback_keep_the_load_action]
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
                for route in pending_routes.get(page,[]):
                    route.fulfill(body=archive,headers=headers(metadata))
                page.close()
        browser.close()
    report={'endpoint':BASE,'passed':passed,'failures':failures,'cases':cases,
            'archive_sha256':hashlib.sha256(archive).hexdigest(),
            'transport':'compiled assets under the production CSP, real exported ZIPs and genuine File/DataTransfer objects'}
    (ROOT/'review/cloud_dimension_drop_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if failures:
        raise SystemExit(1)


if __name__=='__main__':
    main()
