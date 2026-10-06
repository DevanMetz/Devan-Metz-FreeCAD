"""Browser checks: catalog discovery, true geometry edits, matching downloads, mobile."""
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import unquote

from playwright.sync_api import sync_playwright
from browser_assets import ASSETS, OFFLINE_BASE, attach_assets

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = "--offline" in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5178")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT.parent / ".cad-cache/browsers"))


def main():
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1080}, accept_downloads=True)
        if OFFLINE:
            attach_assets(context)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE)
        page.wait_for_function("() => document.querySelectorAll('.card').length===53")
        catalog = json.loads((ASSETS / "catalog.json").read_text()) if OFFLINE else page.request.get(BASE + "/catalog.json").json()
        for model in catalog["models"]:
            if OFFLINE:
                assert page.evaluate("async url => (await fetch(url)).ok", model["image"]), model["name"]
            else:
                assert page.request.get(BASE + model["image"]).ok, model["name"]
        page.locator("#search").fill("organzer")
        assert page.locator(".card").count() >= 3
        page.locator("#reset-search").click()
        page.locator('[data-kind="assembly"]').click()
        assert page.locator(".card").count() == 6
        page.locator("#reset-search").click()
        page.screenshot(path=str(ROOT / "review/cloud_library_desktop.png"), full_page=False)
        page.locator('[data-model="parts_tray"]').click()
        page.wait_for_function("() => !document.querySelector('#download').disabled")
        page.wait_for_function("() => document.querySelector('#viewer').getAttribute('aria-busy') === 'false' && document.querySelector('#viewer canvas')")
        assert page.locator("#viewer canvas").count() == 1
        assert page.locator("#model-size").inner_text() == "150 × 100 × 24"
        page.locator('[data-parameter="length"]').fill("180")
        page.locator('[data-parameter="height"]').fill("30")
        page.locator('[data-parameter="columns"]').fill("4")
        page.locator('[data-parameter="rows"]').fill("3")
        assert page.locator("#download").is_disabled()
        with page.expect_response(lambda response: "/api/generate" in response.url, timeout=600000) as generated:
            page.locator("#rebuild").click()
        response = generated.value
        assert response.status == 200, response.text()
        metadata = json.loads(unquote(response.headers["x-model-metadata"]))
        page.wait_for_function("() => !document.querySelector('#download').disabled", timeout=600000)
        assert page.locator("#model-size").inner_text() == "180 × 100 × 30"
        with page.expect_download() as event:
            page.locator("#download").click()
        download = event.value
        assert download.suggested_filename == f"parts_tray-custom-180x100x30mm-{metadata['mesh_sha256'][:12]}.stl"
        assert hashlib.sha256(Path(download.path()).read_bytes()).hexdigest() == metadata["mesh_sha256"]
        page.screenshot(path=str(ROOT / "review/cloud_custom_preview.png"), full_page=False)
        page.locator('[data-parameter="pocket_radius"]').fill("0.1")
        page.locator("#rebuild").click()
        page.wait_for_function("() => document.querySelector('#form-message').classList.contains('error')", timeout=600000)
        assert page.locator("#download").is_disabled()
        page.locator("#reset-parameters").click()
        assert page.locator('[data-parameter="length"]').input_value() == "150.0" or page.locator('[data-parameter="length"]').input_value() == "150"
        page.locator("#close-editor").click()
        page.locator('[data-model="divider_joint"]').click()
        page.wait_for_function("() => !document.querySelector('#download').disabled")
        page.locator('[data-parameter="ports"]').fill("0, 90, 180")
        page.locator("#rebuild").click()
        page.wait_for_function("() => document.querySelector('#form-message').textContent.includes('Preview updated')", timeout=600000)
        assert not page.locator("#download").is_disabled()
        page.locator("#close-editor").click()
        page.locator('[data-model="soap_dish_assembly"]').click()
        page.wait_for_function("() => document.querySelector('#preview-loading').hidden")
        assert page.locator("#download").is_hidden()
        assert page.locator("#part-links button").count() == 2
        page.locator('[data-parameter="length"]').fill("140")
        page.locator('[data-part="soap_dish_tray"]').click()
        assert page.locator('[data-parameter="length"]').input_value() == "140"
        assert page.locator("#download").is_disabled()
        shared_url = page.url
        page.reload()
        page.wait_for_function("() => document.querySelector('#editor').open")
        assert page.locator('[data-parameter="length"]').input_value() == "140"
        page.locator("#close-editor").click()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(ROOT / "review/cloud_library_mobile.png"), full_page=False)
        page.locator('[data-model="phone_stand"]').click()
        page.wait_for_function("() => !document.querySelector('#download').disabled")
        assert page.evaluate("document.querySelector('#editor').scrollWidth <= document.querySelector('#editor').clientWidth")
        page.screenshot(path=str(ROOT / "review/cloud_editor_mobile.png"), full_page=False)
        assert not errors, errors
        browser.close()
    report = dict(endpoint=BASE, model_count=53, images_loaded=53, search="fuzzy organizer + assembly filter",
                  parameter_rebuilds=["parts_tray", "divider_joint"], matching_download_sha256=metadata["mesh_sha256"],
                  rejected_invalid_geometry=True, shared_link=shared_url, mobile_width=390, browser_errors=errors,
                  transport="compiled assets and native jobs through Playwright routes" if OFFLINE else "local HTTP bridge")
    (ROOT / "review/cloud_ui_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Browser passed: all models/images, fuzzy search, 3D edits, matching STL, invalid geometry, assemblies, shared parameters, mobile.")


if __name__ == "__main__":
    main()
