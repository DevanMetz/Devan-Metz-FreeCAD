"""Verify that optional 3D loading never blocks verified mesh/CAD downloads.

Real exported CAD fixtures and compiled viewer code are replayed with controlled
delays and failures. Run verify_exports.py first; use --offline without a server.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import traceback
from urllib.parse import unquote, urlparse
from zipfile import ZipFile

from playwright.sync_api import sync_playwright
from browser_assets import ASSETS, OFFLINE_BASE, attach_assets
from verify_export_ui import fixture, headers
from validation_job import native_request

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = "--offline" in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5178")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT.parent / ".cad-cache/browsers"))


def main():
    original, custom = fixture("parts_tray_original"), fixture("parts_tray")
    passed, failures = [], []
    pending_by_page = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1080}, accept_downloads=True)
        context.set_default_timeout(20000)
        if OFFLINE:
            attach_assets(context)

        def deliver(route):
            body = (ASSETS / urlparse(route.request.url).path.lstrip("/")).read_bytes() if OFFLINE else route.fetch().body()
            # Observe module evaluation separately from creating its renderer.
            route.fulfill(body=body + b"\nwindow.viewerModuleLoaded = true;", content_type="text/javascript")

        def setup(page, hold_viewer=True):
            waiting, modules, jobs = [], [], []
            pending_by_page[page] = waiting

            def module(route):
                modules.append(route.request.url)
                if hold_viewer:
                    waiting.append(route)
                else:
                    deliver(route)

            page.route("**/assets/viewer-*.js" if OFFLINE else "**/web/viewer.js*", module)

            def generate(route):
                payload = route.request.post_data_json
                jobs.append(payload.get("format", "stl"))
                body, metadata, mesh = custom if payload["parameters"]["length"] == 180.5 else original
                if payload.get("format") == "cad":
                    route.fulfill(body=body, headers=headers(metadata))
                else:
                    metadata = {**metadata, "format": "stl", "file_sha256": metadata["mesh_sha256"]}
                    route.fulfill(body=mesh, headers=headers(metadata, "model/stl"))

            page.route("**/api/generate", generate)
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")
            page.locator('[data-model="parts_tray"]').click()
            return waiting, modules, jobs

        def ready(page):
            page.wait_for_function("() => !document.querySelector('#download').disabled")

        def viewer_ready(page):
            page.wait_for_function("() => document.querySelector('#viewer').getAttribute('aria-busy') === 'false' && document.querySelector('#viewer canvas')")
            assert page.locator("#viewer canvas").count() == 1
            assert page.locator("#fallback-image").is_hidden()
            assert page.locator(".view-tools").is_visible()

        def fallback(page, loading=False):
            assert page.locator("#fallback-image").is_visible()
            badge = page.locator("#preview-badge").text_content()
            assert badge == "Original catalog image", badge
            assert page.locator(".view-tools").is_hidden()
            assert page.locator("#viewer").get_attribute("aria-busy") == str(loading).lower()
            assert 'The catalog image shows original dimensions.' in page.locator('.viewer-help').inner_text()
            note = page.locator('#download-note').inner_text()
            assert ('original model' if page.locator('#download').is_visible() else 'Print the kit components separately') in note

        def download(page, button="download"):
            with page.expect_download() as event:
                page.locator("#" + button).click()
            return Path(event.value.path()).read_bytes()

        def open_custom(page):
            ready(page)
            page.locator('[data-parameter="length"]').fill("180.5")
            page.locator("#rebuild").click()
            ready(page)

        def release(page, waiting):
            assert len(waiting) == 1, "Model changes started duplicate viewer downloads"
            deliver(waiting.pop())
            page.wait_for_function("() => window.viewerModuleLoaded === true")
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")

        def graphics(page, lost):
            page.evaluate("""lost => {
              const canvas = document.querySelector('#viewer canvas');
              if (lost) {
                window.graphicsExtension = canvas.getContext('webgl2').getExtension('WEBGL_lose_context');
                if (!window.graphicsExtension) throw new Error('Missing real WebGL context-loss extension');
              }
              const name = lost ? 'webglcontextlost' : 'webglcontextrestored';
              window.graphicsEvent = null;
              canvas.addEventListener(name, () => { window.graphicsEvent = name; }, { once: true });
              window.graphicsExtension[lost ? 'loseContext' : 'restoreContext']();
            }""", lost)
            page.wait_for_function("name => window.graphicsEvent === name",
                arg="webglcontextlost" if lost else "webglcontextrestored", timeout=5000)
            assert page.evaluate("() => document.querySelector('#viewer canvas').getContext('webgl2').isContextLost()") == lost

        def observe_rendered_model(page, url):
            page.evaluate("""async url => {
              const { ModelViewer } = await import(url);
              const render = ModelViewer.prototype.render;
              ModelViewer.prototype.render = function() {
                const result = render.call(this);
                if (this.mesh && !this.renderer.getContext().isContextLost()) {
                  window.graphicsRenders = (window.graphicsRenders || 0) + 1;
                  const box = this.mesh.geometry.boundingBox;
                  window.renderedPreview = {
                    size: ['x', 'y', 'z'].map(axis => Math.round((box.max[axis] - box.min[axis]) * 100) / 100),
                    camera: this.camera.position.toArray(), target: this.controls.target.toArray(),
                    center: this.target.toArray(), radius: this.radius,
                    near: this.camera.near, far: this.camera.far,
                    edges: this.mesh.material.wireframe,
                  };
                }
                return result;
              };
            }""", url)

        def same_framing(page, before):
            after = page.evaluate('window.renderedPreview')
            for key in ('camera', 'target'):
                expected = [(value - center) / before['radius']
                            for value, center in zip(before[key], before['center'])]
                actual = [(value - center) / after['radius']
                          for value, center in zip(after[key], after['center'])]
                assert all(math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-8)
                           for a, b in zip(expected, actual)), (key, before, after)
            for key in ('near', 'far'):
                assert math.isclose(before[key] / before['radius'], after[key] / after['radius'],
                                    rel_tol=1e-8, abs_tol=1e-8), (key, before, after)
            assert before['edges'] == after['edges'], (before, after)
            assert page.locator('#wireframe').get_attribute('aria-pressed') == str(after['edges']).lower()
            return after

        def named_views_survive_original_cad_refresh_and_rebuild(page):
            _, modules, jobs = setup(page, hold_viewer=False)
            ready(page)
            viewer_ready(page)
            observe_rendered_model(page, modules[0])
            page.locator('[data-view="top"]').click()
            page.locator('#wireframe').click()
            top = page.evaluate('window.renderedPreview')
            assert abs(top['camera'][0]) < 1e-8 and top['edges']
            assert download(page, 'download-cad') == original[0]
            ready(page)
            same_framing(page, top)
            assert download(page) == original[2]
            assert download(page, 'download-cad') == original[0]
            assert jobs == ['stl', 'cad'], 'Original CAD refresh discarded its files'
            page.locator('[data-view="front"]').click()
            front = page.evaluate('window.renderedPreview')
            assert abs(front['camera'][0]) < 1e-8 and front['camera'][1] < -1
            open_custom(page)
            same_framing(page, front)
            assert page.evaluate('window.renderedPreview.size') == [180.5, 100, 24]
            assert download(page) == custom[2]
            assert download(page, 'download-cad') == custom[0]
            same_framing(page, front)
            assert jobs == ['stl', 'cad', 'stl', 'cad']

        def manual_orbit_zoom_and_pan_survive_larger_and_smaller_meshes(page):
            taller_parameters = {**custom[1]['parameters'], 'height': 48}
            status, taller_mesh, response_headers = native_request({
                'model': 'parts_tray', 'parameters': taller_parameters})
            assert status == 200, (status, taller_mesh[:250])
            taller_metadata = json.loads(unquote(response_headers['X-Model-Metadata']))
            _, modules, jobs = setup(page, hold_viewer=False)
            ready(page)
            viewer_ready(page)
            observe_rendered_model(page, modules[0])
            page.locator('[data-view="iso"]').click()
            initial = page.evaluate('window.renderedPreview')
            canvas = page.locator('#viewer canvas')
            canvas.scroll_into_view_if_needed()
            box = canvas.bounding_box()
            x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x + 65, y - 45, steps=6)
            page.mouse.up()
            orbited = page.evaluate('window.renderedPreview')
            assert orbited['camera'] != initial['camera'], 'Real pointer orbit did not change the camera'
            renders = page.evaluate('window.graphicsRenders')
            page.mouse.wheel(0, -240)
            page.wait_for_function('before => window.graphicsRenders > before', arg=renders)
            zoomed = page.evaluate('window.renderedPreview')
            distance = lambda pose: math.dist(pose['camera'], pose['target'])
            assert distance(zoomed) < distance(orbited), 'Real wheel zoom did not move closer'
            page.mouse.move(x, y)
            page.mouse.down(button='right')
            page.mouse.move(x + 40, y + 25, steps=6)
            page.mouse.up(button='right')
            page.locator('#wireframe').click()
            before = page.evaluate('window.renderedPreview')
            assert math.dist(before['target'], before['center']) > 1, 'Real right-drag did not pan'

            def taller(route):
                payload = route.request.post_data_json
                assert payload['parameters'] == taller_parameters and payload.get('format', 'stl') == 'stl'
                jobs.append('stl')
                route.fulfill(body=taller_mesh, headers=headers(taller_metadata, 'model/stl'))

            page.route('**/api/generate', taller)
            page.locator('[data-parameter="length"]').fill('180.5')
            page.locator('[data-parameter="height"]').fill('48')
            page.locator('#rebuild').click()
            ready(page)
            larger = same_framing(page, before)
            assert larger['size'] == [180.5, 100, 48] and larger['center'] == [0, 0, 24]
            assert larger['radius'] > before['radius']
            assert download(page) == taller_mesh
            page.screenshot(path=str(ROOT / 'review/cloud_camera_update_desktop.png'))
            page.unroute('**/api/generate', taller)
            page.locator('[data-parameter="length"]').fill('150')
            page.locator('[data-parameter="height"]').fill('24')
            page.locator('#rebuild').click()
            ready(page)
            smaller = same_framing(page, before)
            assert smaller['size'] == [150, 100, 24] and smaller['center'] == [0, 0, 12]
            assert download(page) == original[2]
            assert download(page, 'download-cad') == original[0]
            same_framing(page, before)
            assert jobs == ['stl', 'stl', 'cad']

        def pending_preview_uses_latest_view_and_edges_choice(page):
            waiting, modules, jobs = setup(page, hold_viewer=False)
            ready(page)
            viewer_ready(page)
            observe_rendered_model(page, modules[0])
            page.locator('[data-view="top"]').click()
            page.locator('#wireframe').click()

            def hold_preview(route):
                assert route.request.post_data_json['parameters']['length'] == 180.5
                jobs.append('stl')
                waiting.append(route)

            page.route('**/api/generate', hold_preview)
            page.locator('[data-parameter="length"]').fill('180.5')
            page.locator('#rebuild').click()
            page.wait_for_function("() => !document.querySelector('#stop-build').hidden")
            assert len(waiting) == 1
            page.locator('[data-view="front"]').click()
            page.locator('#wireframe').click()
            latest = page.evaluate('window.renderedPreview')
            assert not latest['edges'] and latest['camera'][1] < -1
            metadata = {**custom[1], 'format': 'stl', 'file_sha256': custom[1]['mesh_sha256']}
            waiting.pop().fulfill(body=custom[2], headers=headers(metadata, 'model/stl'))
            ready(page)
            same_framing(page, latest)
            assert download(page) == custom[2]
            assert jobs == ['stl']

        def mobile_updates_keep_view_and_new_models_reset_it(page):
            page.set_viewport_size({'width': 390, 'height': 844})
            _, modules, jobs = setup(page, hold_viewer=False)
            ready(page)
            viewer_ready(page)
            observe_rendered_model(page, modules[0])
            page.locator('[data-view="iso"]').focus()
            page.keyboard.press('Space')
            initial = page.evaluate('window.renderedPreview')
            page.locator('[data-view="top"]').focus()
            page.keyboard.press('Space')
            page.locator('#wireframe').focus()
            page.keyboard.press('Space')
            before = page.evaluate('window.renderedPreview')
            open_custom(page)
            same_framing(page, before)
            assert download(page) == custom[2]
            assert download(page, 'download-cad') == custom[0]
            same_framing(page, before)
            assert jobs == ['stl', 'cad']
            page.locator('.editor-layout').evaluate('element => { element.scrollTop = 0; }')
            page.screenshot(path=str(ROOT / 'review/cloud_camera_update_mobile.png'))
            page.locator('#close-editor').click()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            page.locator('[data-model="cable_comb"]').click()
            ready(page)
            viewer_ready(page)
            reset = same_framing(page, initial)
            assert reset['size'] == [59, 32, 4] and not reset['edges']
            page.locator('[data-view="top"]').click()
            page.locator('#wireframe').click()
            page.locator('#close-editor').click()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            page.locator('[data-model="parts_tray"]').click()
            ready(page)
            viewer_ready(page)
            reopened = same_framing(page, initial)
            assert reopened['size'] == [150, 100, 24] and not reopened['edges']
            assert download(page) == (CLOUD / 'public/models/parts_tray.stl').read_bytes()
            assert jobs == ['stl', 'cad']

        def held_original_download_and_export(page):
            waiting, _, jobs = setup(page)
            ready(page)
            fallback(page, loading=True)
            assert download(page) == (CLOUD / "public/models/parts_tray.stl").read_bytes()
            assert download(page, "download-cad") == original[0]
            assert jobs == ["stl", "cad"]
            fallback(page, loading=True)
            release(page, waiting)
            viewer_ready(page)
            assert download(page) == original[2]
            assert download(page, "download-cad") == original[0]
            assert jobs == ["stl", "cad"], "Late 3D initialization discarded the verified CAD cache"

        def held_custom_files_and_late_upgrade(page):
            waiting, _, jobs = setup(page)
            open_custom(page)
            fallback(page, loading=True)
            assert page.locator("#rebuild").is_enabled()
            assert page.locator("#stop-build").is_hidden()
            assert page.locator("#model-size").inner_text() == "180.5 × 100 × 24"
            assert download(page) == custom[2]
            with page.expect_download() as event:
                page.locator("#download-cad").click()
            with ZipFile(event.value.path()) as archive:
                assert archive.read("parts_tray.stl") == custom[2]
                assert json.loads(archive.read("parameters.json"))["parameters"]["length"] == 180.5
            assert jobs == ["stl", "cad"]
            page.screenshot(path=str(ROOT / "review/cloud_viewer_loading_fallback.png"))
            release(page, waiting)
            viewer_ready(page)
            assert page.locator("#model-size").inner_text() == "180.5 × 100 × 24"
            assert "exact mesh" in page.locator("#download-note").inner_text()
            assert download(page) == custom[2]

        def close_before_module_initialization(page):
            waiting, _, _ = setup(page)
            ready(page)
            page.locator("#close-editor").click()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            release(page, waiting)
            assert page.locator("#viewer canvas").count() == 0, "A closed editor created an unused renderer"
            page.locator('[data-model="cable_comb"]').click()
            ready(page)
            viewer_ready(page)
            assert page.locator("#model-size").inner_text() == "59 × 32 × 4"

        def switch_models_during_load(page):
            waiting, _, _ = setup(page)
            ready(page)
            page.locator("#close-editor").click()
            page.wait_for_function("() => !new URL(location.href).searchParams.has('model')")
            page.locator('[data-model="cable_comb"]').click()
            ready(page)
            assert download(page) == (CLOUD / "public/models/cable_comb.stl").read_bytes()
            release(page, waiting)
            viewer_ready(page)
            assert page.locator("#model-size").inner_text() == "59 × 32 × 4"
            assert page.locator("#mesh-status").inner_text() == "Original dimensions"
            assert download(page) == (CLOUD / "public/models/cable_comb.stl").read_bytes()

        def failed_module_keeps_downloads(page):
            waiting, modules, _ = setup(page)
            open_custom(page)
            assert len(waiting) == 1
            waiting.pop().abort()
            page.wait_for_function("() => document.querySelector('#viewer').getAttribute('aria-busy') === 'false'")
            fallback(page)
            assert "unavailable" in page.locator(".viewer-help").inner_text()
            assert download(page) == custom[2]
            assert download(page, "download-cad") == custom[0]
            page.locator("#close-editor").click()
            page.wait_for_function("() => !new URL(location.href).searchParams.has('model')")
            page.locator('[data-model="cable_comb"]').click()
            ready(page)
            page.wait_for_function("() => document.querySelector('#viewer').getAttribute('aria-busy') === 'false'")
            fallback(page)
            assert len(modules) == 1

        def no_webgl_keeps_downloads(page):
            page.add_init_script("""const original = HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                return type.startsWith('webgl') ? null : original.call(this, type, ...args);
              };""")
            setup(page, hold_viewer=False)
            open_custom(page)
            page.wait_for_function("() => document.querySelector('#viewer').getAttribute('aria-busy') === 'false'")
            fallback(page)
            assert page.locator("#viewer canvas").count() == 0
            assert download(page) == custom[2]
            assert download(page, "download-cad") == custom[0]

        def failed_renderer_keeps_verified_files(page):
            _, modules, _ = setup(page, hold_viewer=False)
            ready(page)
            viewer_ready(page)
            page.evaluate("""async url => {
              const { ModelViewer } = await import(url);
              const load = ModelViewer.prototype.load, dispose = ModelViewer.prototype.dispose;
              ModelViewer.prototype.load = function(...args) {
                if (window.failViewerLoad) throw new Error('Controlled rendering failure');
                return load.apply(this, args);
              };
              ModelViewer.prototype.dispose = function() {
                window.viewerDisposals = (window.viewerDisposals || 0) + 1;
                return dispose.call(this);
              };
              window.failViewerLoad = true;
            }""", modules[0])
            open_custom(page)
            fallback(page)
            assert page.evaluate("window.viewerDisposals") == 1
            assert page.locator("#viewer canvas").count() == 0
            assert download(page) == custom[2]
            assert download(page, "download-cad") == custom[0]

        def lost_original_graphics_keep_exact_stl_and_view(page):
            _, modules, jobs = setup(page, hold_viewer=False)
            ready(page)
            viewer_ready(page)
            observe_rendered_model(page, modules[0])
            page.locator('[data-view="front"]').click()
            page.locator('#wireframe').click()
            before = page.evaluate('window.renderedPreview')
            renders = page.evaluate('window.graphicsRenders')
            graphics(page, True)
            fallback(page)
            assert download(page) == (CLOUD / 'public/models/parts_tray.stl').read_bytes()
            assert not jobs, 'Losing graphics started a CAD job'
            page.screenshot(path=str(ROOT / 'review/cloud_viewer_context_fallback.png'))
            graphics(page, False)
            viewer_ready(page)
            assert page.evaluate('window.graphicsRenders') > renders, 'Restored context did not redraw the model'
            assert page.evaluate('window.renderedPreview') == before, 'Graphics recovery changed the view or edges'
            assert page.locator('#wireframe').get_attribute('aria-pressed') == 'true'
            assert download(page) == (CLOUD / 'public/models/parts_tray.stl').read_bytes()
            assert not jobs

        def graphics_recovery_keeps_invalid_draft_and_cached_cad(page):
            _, _, jobs = setup(page, hold_viewer=False)
            open_custom(page)
            viewer_ready(page)
            assert download(page, 'download-cad') == custom[0]
            field = page.locator('[data-parameter="length"]')
            field.fill('')
            error = page.locator('#form-message').inner_text()
            graphics(page, True)
            fallback(page)
            assert field.evaluate('element => element === document.activeElement')
            assert page.locator('#download').is_disabled()
            assert page.locator('#download-cad').is_disabled()
            graphics(page, False)
            viewer_ready(page)
            assert field.input_value() == ''
            assert field.evaluate('element => element === document.activeElement')
            assert field.get_attribute('aria-invalid') == 'true'
            assert page.locator('#form-message').inner_text() == error
            assert page.locator('#download').is_disabled()
            page.locator('#revert-parameters').click()
            assert download(page) == custom[2]
            assert download(page, 'download-cad') == custom[0]
            assert jobs == ['stl', 'cad'], 'Graphics recovery discarded the matching CAD cache'

        def builds_while_graphics_lost_restore_latest_mesh(page):
            _, modules, jobs = setup(page, hold_viewer=False)
            ready(page)
            viewer_ready(page)
            observe_rendered_model(page, modules[0])
            page.locator('[data-view="top"]').click()
            page.locator('#wireframe').click()
            before = page.evaluate('window.renderedPreview')
            graphics(page, True)
            fallback(page)
            open_custom(page)
            fallback(page)
            assert page.locator('#model-size').inner_text() == '180.5 × 100 × 24'
            assert download(page) == custom[2]
            assert download(page, 'download-cad') == custom[0]
            assert jobs == ['stl', 'cad']
            graphics(page, False)
            viewer_ready(page)
            assert page.evaluate('window.renderedPreview.size') == [180.5, 100, 24]
            same_framing(page, before)
            assert download(page) == custom[2]
            assert download(page, 'download-cad') == custom[0]
            assert jobs == ['stl', 'cad']
            page.screenshot(path=str(ROOT / 'review/cloud_viewer_context_custom_restored.png'))

        def graphics_recovery_after_close_and_navigation(page):
            _, modules, jobs = setup(page, hold_viewer=False)
            ready(page)
            viewer_ready(page)
            observe_rendered_model(page, modules[0])
            graphics(page, True)
            page.locator('#close-editor').click()
            page.wait_for_function("() => !new URL(location.href).searchParams.has('model')")
            graphics(page, False)
            assert not page.locator('#editor').evaluate('element => element.open')
            page.locator('[data-model="cable_comb"]').click()
            ready(page)
            viewer_ready(page)
            assert page.evaluate('window.renderedPreview.size') == [59, 32, 4]
            graphics(page, True)
            page.locator('#close-editor').click()
            page.wait_for_function("() => !new URL(location.href).searchParams.has('model')")
            page.locator('[data-model="soap_dish_assembly"]').click()
            page.wait_for_function("() => !document.querySelector('#download-cad').disabled")
            fallback(page)
            assert page.locator('#download').is_hidden()
            graphics(page, False)
            viewer_ready(page)
            assert page.evaluate('window.renderedPreview.size') == [120, 84, 14]
            assert page.locator('#preview-badge').text_content() == 'Reference assembly'
            assert page.locator('#download-cad').inner_text().startswith('Download parts kit')
            assert not jobs

        def mobile_graphics_changes_keep_pending_cad_and_focus(page):
            page.set_viewport_size({'width': 390, 'height': 844})
            waiting, _, jobs = setup(page, hold_viewer=False)
            open_custom(page)
            viewer_ready(page)

            def hold_cad(route):
                assert route.request.post_data_json['format'] == 'cad'
                assert route.request.post_data_json['parameters']['length'] == 180.5
                jobs.append('cad')
                waiting.append(route)

            page.route('**/api/generate', hold_cad)
            with page.expect_download() as event:
                page.locator('#download-cad').focus()
                page.keyboard.press('Space')
                page.wait_for_function("() => !document.querySelector('#stop-build').hidden")
                assert len(waiting) == 1
                stop = page.locator('#stop-build')
                assert stop.evaluate('element => element === document.activeElement')
                graphics(page, True)
                fallback(page)
                assert stop.evaluate('element => element === document.activeElement')
                assert stop.is_visible() and stop.bounding_box()['height'] >= 44
                assert page.locator('#download').is_disabled()
                assert page.locator('#download-cad').is_disabled()
                page.locator('.editor-layout').evaluate('element => { element.scrollTop = 0; }')
                page.screenshot(path=str(ROOT / 'review/cloud_viewer_context_mobile.png'))
                graphics(page, False)
                viewer_ready(page)
                assert stop.evaluate('element => element === document.activeElement')
                assert stop.is_visible()
                assert page.locator('#download').is_disabled()
                assert page.locator('#download-cad').is_disabled()
                waiting.pop().fulfill(body=custom[0], headers=headers(custom[1]))
            assert Path(event.value.path()).read_bytes() == custom[0]
            ready(page)
            assert download(page) == custom[2]
            assert jobs == ['stl', 'cad']
            page.locator('.editor-layout').evaluate('element => { element.scrollTop = 0; }')
            page.screenshot(path=str(ROOT / 'review/cloud_viewer_context_mobile_restored.png'))

        def corrupt_mesh_stays_blocked(page):
            mesh = bytearray((CLOUD / "public/models/parts_tray.stl").read_bytes())
            mesh[0] ^= 1
            page.route("**/models/parts_tray.stl", lambda route: route.fulfill(body=bytes(mesh), content_type="model/stl"))
            _, modules, _ = setup(page)
            page.wait_for_function("() => document.querySelector('#form-message').classList.contains('error')")
            assert page.locator("#download").is_disabled()
            assert page.locator("#download-cad").is_disabled()
            assert page.locator("#viewer").get_attribute("aria-busy") == "false"
            assert not modules, "Unverified mesh started the optional viewer"

        for test in (held_original_download_and_export, held_custom_files_and_late_upgrade,
                     close_before_module_initialization, switch_models_during_load,
                     failed_module_keeps_downloads, no_webgl_keeps_downloads,
                     failed_renderer_keeps_verified_files, corrupt_mesh_stays_blocked,
                     lost_original_graphics_keep_exact_stl_and_view,
                     graphics_recovery_keeps_invalid_draft_and_cached_cad,
                     builds_while_graphics_lost_restore_latest_mesh,
                     graphics_recovery_after_close_and_navigation,
                     mobile_graphics_changes_keep_pending_cad_and_focus,
                     named_views_survive_original_cad_refresh_and_rebuild,
                     manual_orbit_zoom_and_pan_survive_larger_and_smaller_meshes,
                     pending_preview_uses_latest_view_and_edges_choice,
                     mobile_updates_keep_view_and_new_models_reset_it):
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                print(f"START {test.__name__}", flush=True)
                test(page)
                assert not errors, errors
                passed.append(test.__name__)
                print(f"PASS {test.__name__}", flush=True)
            except Exception as error:
                failures.append(dict(test=test.__name__, error=str(error), traceback=traceback.format_exc(), browser_errors=errors))
                print(f"FAIL {test.__name__}: {failures[-1]['traceback']}", flush=True)
            finally:
                for route in pending_by_page.pop(page, []):
                    route.abort()
                page.close()
        context.close()
        browser.close()
    report = dict(endpoint=BASE, passed=passed, failures=failures,
        fixture_archive_sha256=hashlib.sha256(custom[0]).hexdigest(),
        transport="compiled assets and real CAD fixtures with controlled viewer loading" if OFFLINE else "local HTTP bridge with controlled viewer loading")
    (ROOT / "review/cloud_viewer_loading_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert not failures, report


if __name__ == "__main__":
    main()
