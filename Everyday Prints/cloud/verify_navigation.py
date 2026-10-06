"""Exercise native Back/Forward, preserved drafts, and recent CAD previews."""
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from browser_transfers import DEFERRED_BODY
from validation_job import native_request

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = "--offline" in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5178")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT.parent / ".cad-cache/browsers"))


def main():
    passed, failures = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1080}, accept_downloads=True)
        context.set_default_timeout(10000)
        if OFFLINE:
            attach_assets(context)
            status, custom_mesh, headers = native_request({"model": "parts_tray", "parameters": {"length": 180}})
            assert status == 200
        else:
            response = context.request.post(BASE + "/api/generate", data={"model": "parts_tray", "parameters": {"length": 180}}, timeout=120000)
            assert response.ok, response.text()
            custom_mesh = response.body()
            headers = {"Content-Type": "model/stl", "X-Model-Metadata": response.headers["x-model-metadata"]}

        def library(page):
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")

        def wait_model(page, name):
            page.wait_for_function("name => new URL(location.href).searchParams.get('model') === name && document.querySelector('#editor')?.open && document.querySelector('#preview-loading').hidden", arg=name)

        def open_model(page, name):
            count = page.evaluate("history.length")
            page.locator(f'[data-model="{name}"]').click()
            wait_model(page, name)
            assert page.evaluate("history.length") == count + 1, "Opening a model replaced the library's history entry"

        def back(page):
            page.go_back()
            assert page.url.startswith(BASE), "Back left the library instead of restoring the previous view"

        def forward(page):
            page.go_forward()
            assert page.url.startswith(BASE), "Forward left the library"

        def back_forward_library(page):
            library(page)
            page.locator("#search").fill("phone")
            open_model(page, "phone_stand")
            back(page)
            page.wait_for_function("() => !document.querySelector('#editor').open")
            assert page.locator("#search").input_value() == "phone"
            assert page.locator(".card").count() == 1
            assert page.locator('[data-model="phone_stand"]').evaluate("element => element === document.activeElement")
            forward(page)
            wait_model(page, "phone_stand")
            assert not page.locator("#download").is_disabled()
            page.wait_for_function("() => document.querySelector('#viewer').getAttribute('aria-busy') === 'false'")
            assert page.locator("#viewer canvas").count() == 1

        def assembly_component_drafts(page):
            library(page)
            open_model(page, "soap_dish_assembly")
            page.locator('[data-parameter="length"]').fill("140")
            page.locator('[data-part="soap_dish_tray"]').click()
            wait_model(page, "soap_dish_tray")
            back(page)
            wait_model(page, "soap_dish_assembly")
            assert page.locator('[data-parameter="length"]').input_value() == "140"
            assert page.locator("#download").is_hidden()
            forward(page)
            wait_model(page, "soap_dish_tray")
            assert page.locator('[data-parameter="length"]').input_value() == "140"
            assert page.locator("#download").is_disabled()

        def invalid_draft_restoration(page):
            library(page)
            open_model(page, "parts_tray")
            page.locator('[data-parameter="length"]').fill("")
            back(page)
            page.wait_for_function("() => !document.querySelector('#editor').open")
            forward(page)
            wait_model(page, "parts_tray")
            assert page.locator('[data-parameter="length"]').input_value() == ""
            assert page.locator("#download").is_disabled()
            assert "enter a number" in page.locator("#form-message").inner_text()
            assert page.locator("#model-size").inner_text() == "150 × 100 × 24"

        def custom_preview_restoration(page):
            jobs = []

            def generate(route):
                jobs.append(route.request.post_data_json)
                route.fulfill(body=custom_mesh, headers=headers)

            page.route("**/api/generate", generate)
            library(page)
            open_model(page, "parts_tray")
            page.locator('[data-parameter="length"]').fill("180")
            page.locator("#rebuild").click()
            page.wait_for_function("() => !document.querySelector('#download').disabled")
            back(page)
            page.wait_for_function("() => !document.querySelector('#editor').open")
            forward(page)
            wait_model(page, "parts_tray")
            assert page.locator("#model-size").inner_text() == "180 × 100 × 24"
            assert not page.locator("#download").is_disabled()
            assert len(jobs) == 1, "Restoring a cached preview started another CAD build"
            with page.expect_download() as event:
                page.locator("#download").click()
            assert hashlib.sha256(Path(event.value.path()).read_bytes()).digest() == hashlib.sha256(custom_mesh).digest()
            page.screenshot(path=str(ROOT / "review/cloud_history_custom_preview.png"), full_page=False)

        def nested_close_returns_library(page):
            library(page)
            page.locator("#search").fill("soap")
            open_model(page, "soap_dish_assembly")
            page.locator('[data-parameter="length"]').fill("140")
            page.locator('[data-part="soap_dish_tray"]').click()
            wait_model(page, "soap_dish_tray")
            page.locator("#close-editor").click()
            page.wait_for_function("() => !new URL(location.href).searchParams.has('model') && !document.querySelector('#editor').open")
            assert page.locator("#search").input_value() == "soap"
            forward(page)
            wait_model(page, "soap_dish_assembly")
            assert page.locator('[data-parameter="length"]').input_value() == "140"
            forward(page)
            wait_model(page, "soap_dish_tray")
            assert page.locator('[data-parameter="length"]').input_value() == "140"

        def deep_link_close_stays_on_site(page):
            query = urlencode({"model": "soap_dish_assembly", "p": json.dumps({"length": 140})})
            page.goto(BASE + "/?" + query)
            wait_model(page, "soap_dish_assembly")
            page.locator('[data-part="soap_dish_tray"]').click()
            wait_model(page, "soap_dish_tray")
            page.locator("#close-editor").click()
            page.wait_for_function("() => !new URL(location.href).searchParams.has('model') && !document.querySelector('#editor').open")
            assert page.url.startswith(BASE)
            assert page.locator(".card").count() == 53
            back(page)
            wait_model(page, "soap_dish_tray")
            assert page.locator('[data-parameter="length"]').input_value() == "140"

        def late_build_after_navigation(page):
            page.add_init_script(DEFERRED_BODY + """const originalFetch = window.fetch;
              window.fetch = async (...args) => {
                const response = await originalFetch(...args);
                if (String(args[0]).endsWith('/api/generate') && !window.deferredOnce) {
                  window.deferredOnce = true;
                  const buffer = await response.arrayBuffer();
                  window.deferFileBody(response, buffer, () => new Promise(resolve => {
                    window.releaseBuild = resolve;
                  }));
                }
                return response;
              };""")
            page.route("**/api/generate", lambda route: route.fulfill(body=custom_mesh, headers=headers))
            library(page)
            open_model(page, "parts_tray")
            page.locator('[data-parameter="length"]').fill("180")
            page.locator("#rebuild").click()
            page.wait_for_function("() => typeof window.releaseBuild === 'function'")
            back(page)
            page.wait_for_function("() => !document.querySelector('#editor').open")
            forward(page)
            wait_model(page, "parts_tray")
            page.evaluate("window.releaseBuild()")
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            assert page.locator("#model-size").inner_text() == "150 × 100 × 24"
            assert page.locator('[data-parameter="length"]').input_value() == "180"
            assert page.locator("#download").is_disabled()
            assert page.locator("#rebuild").is_enabled()

        def mobile_escape_and_backdrop(page):
            page.set_viewport_size({"width": 390, "height": 844})
            library(page)
            assert not page.locator("#search").evaluate("element => element === document.activeElement"), "Initial loading focused the mobile search box"
            open_model(page, "phone_stand")
            page.keyboard.press("Escape")
            page.wait_for_function("() => !new URL(location.href).searchParams.has('model') && !document.querySelector('#editor').open")
            assert page.locator('[data-model="phone_stand"]').evaluate("element => element === document.activeElement")
            forward(page)
            wait_model(page, "phone_stand")
            page.mouse.click(2, 2)
            page.wait_for_function("() => !new URL(location.href).searchParams.has('model') && !document.querySelector('#editor').open")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

        def reload_preserves_route(page):
            jobs = []

            def generate(route):
                jobs.append(route.request.post_data_json)
                route.fulfill(body=custom_mesh, headers=headers)

            page.route("**/api/generate", generate)
            library(page)
            open_model(page, "parts_tray")
            page.locator('[data-parameter="length"]').fill("180")
            page.locator("#rebuild").click()
            page.wait_for_function("() => !document.querySelector('#download').disabled")
            page.reload()
            wait_model(page, "parts_tray")
            assert page.locator('[data-parameter="length"]').input_value() == "180"
            assert page.locator("#download").is_disabled(), "Reload offered the original mesh for custom dimensions"
            page.locator("#close-editor").click()
            page.wait_for_function("() => !new URL(location.href).searchParams.has('model') && !document.querySelector('#editor').open")
            assert page.locator(".card").count() == 53
            forward(page)
            wait_model(page, "parts_tray")
            assert page.locator('[data-parameter="length"]').input_value() == "180"
            assert len(jobs) == 1, "Reload or navigation started an unsolicited CAD build"

        for test in (back_forward_library, assembly_component_drafts, invalid_draft_restoration,
                     custom_preview_restoration, nested_close_returns_library,
                     deep_link_close_stays_on_site, late_build_after_navigation,
                     mobile_escape_and_backdrop, reload_preserves_route):
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                test(page)
                assert not errors, errors
                passed.append(test.__name__)
                print(f"PASS {test.__name__}", flush=True)
            except Exception as error:
                details = traceback.format_exc()
                failures.append(dict(test=test.__name__, error=str(error), traceback=details,
                                     url=page.url, browser_errors=errors))
                print(f"FAIL {test.__name__}: {details}", flush=True)
            finally:
                page.close()
        context.close()
        browser.close()
    report = dict(endpoint=BASE, passed=passed, failures=failures,
                  fixture="Real 180-mm parts_tray CAD build replayed locally",
                  mesh_sha256=hashlib.sha256(custom_mesh).hexdigest(),
                  transport="compiled assets and native jobs through Playwright routes" if OFFLINE else "local HTTP bridge")
    (ROOT / "review/cloud_navigation_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert not failures, report


if __name__ == "__main__":
    main()
