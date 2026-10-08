"""Verify CAD downloads, stale edits, navigation and transfer failures in-browser.

Run verify_exports.py first to create real CAD ZIP fixtures. Controlled failure
checks replay those fixtures; the first check builds CAD through the real local
HTTP bridge or, with --offline, the native isolated job.
"""
import hashlib
import io
import json
import copy
import os
from pathlib import Path
import sys
import time
import traceback
from urllib.parse import quote, unquote
from zipfile import ZipFile

from playwright.sync_api import sync_playwright
from browser_assets import OFFLINE_BASE, attach_assets
from browser_transfers import DEFERRED_BODY
from validation_job import native_request

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
OFFLINE = "--offline" in sys.argv
BASE = OFFLINE_BASE if OFFLINE else (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5178")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT.parent / ".cad-cache/browsers"))


def fixture(name):
    body = (ROOT / "review/cloud_export_samples" / name / "download.zip").read_bytes()
    with ZipFile(io.BytesIO(body)) as archive:
        metadata = json.loads(archive.read("parameters.json"))
        mesh = archive.read(metadata["model"] + ".stl") if metadata["printable"] else None
    metadata["file_sha256"] = hashlib.sha256(body).hexdigest()
    return body, metadata, mesh


def headers(metadata, kind="application/zip"):
    return {"Content-Type": kind, "X-Model-Metadata": quote(json.dumps(metadata))}


def main():
    passed, failures = [], []
    custom_zip, custom_meta, custom_mesh = fixture("parts_tray")
    original_zip, original_meta, original_mesh = fixture("parts_tray_original")
    assembly_zip, assembly_meta, _ = fixture("soap_dish_assembly")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1080}, accept_downloads=True)
        context.set_default_timeout(20000 if OFFLINE else 10000)
        if OFFLINE:
            attach_assets(context)
            status, assembly_mesh, response_headers = native_request({"model": "soap_dish_assembly", "parameters": assembly_meta["parameters"]})
            assert status == 200, (status, assembly_mesh.decode('utf-8', errors='replace'))
            assembly_preview = json.loads(unquote(response_headers["X-Model-Metadata"]))
        else:
            response = context.request.post(BASE + "/api/generate",
                data={"model": "soap_dish_assembly", "parameters": assembly_meta["parameters"]}, timeout=120000)
            assert response.ok, response.text()
            assembly_mesh = response.body()
            assembly_preview = json.loads(unquote(response.headers["x-model-metadata"]))
        assert assembly_preview["mesh_sha256"] == assembly_meta["mesh_sha256"]

        def library(page):
            page.goto(BASE)
            page.wait_for_function("() => document.querySelectorAll('.card').length === 53")

        def ready(page, name="parts_tray"):
            page.locator(f'[data-model="{name}"]').click()
            page.wait_for_function("() => !document.querySelector('#download-cad').disabled")

        def reply(route, body, metadata):
            route.fulfill(body=body, headers=headers(metadata))

        def preview_reply(route, mesh=custom_mesh, metadata=custom_meta):
            value = {**metadata, "format": "stl", "file_sha256": metadata["mesh_sha256"]}
            route.fulfill(body=mesh, headers=headers(value, "model/stl"))

        def custom(page, handler=None):
            def route_handler(route):
                if route.request.post_data_json.get("format") == "cad":
                    if handler:
                        handler(route)
                    else:
                        reply(route, custom_zip, custom_meta)
                else:
                    preview_reply(route)
            page.route("**/api/generate", route_handler)
            library(page)
            ready(page)
            page.locator('[data-parameter="length"]').fill("180.5")
            page.locator("#rebuild").click()
            page.wait_for_function("() => !document.querySelector('#download-cad').disabled")

        def pending(page, waiting):
            deadline = time.monotonic() + 10
            while not waiting and time.monotonic() < deadline:
                page.wait_for_timeout(25)
            assert waiting, "Expected CAD export was not requested"
            return waiting.pop(0)

        def real_custom_download(page):
            library(page)
            ready(page)
            length = page.locator('[data-parameter="length"]')
            length.fill("180.55")
            assert length.evaluate("input => input.validity.valid"), "Fine dimensions were blocked by HTML step validation"
            page.locator("#rebuild").click()
            page.wait_for_function("() => !document.querySelector('#download-cad').disabled", timeout=120000)
            with page.expect_download(timeout=120000) as export_event:
                page.locator("#download-cad").click()
            download = export_event.value
            with ZipFile(download.path()) as archive:
                assert archive.testzip() is None
                metadata = json.loads(archive.read("parameters.json"))
                assert metadata["parameters"]["length"] == 180.55
                assert abs(metadata["bounds_mm"][0] - 180.55) < .001
                mesh = archive.read("parts_tray.stl")
            archive_hash = hashlib.sha256(Path(download.path()).read_bytes()).hexdigest()
            assert download.suggested_filename == f"parts_tray-custom-180.55x100x24mm-{archive_hash[:12]}-cad.zip"
            with page.expect_download() as mesh_event:
                page.locator("#download").click()
            assert Path(mesh_event.value.path()).read_bytes() == mesh
            page.screenshot(path=str(ROOT / "review/cloud_cad_download.png"))

        def integer_counts_remain_whole(page):
            jobs = []
            page.route("**/api/generate", lambda route: jobs.append(route))
            library(page)
            ready(page)
            columns = page.locator('[data-parameter="columns"]')
            original = columns.input_value()
            columns.fill("2.5")
            assert not columns.evaluate("input => input.validity.valid")
            assert "whole number" in page.locator("#form-message").inner_text()
            page.locator("#rebuild").click()
            assert not jobs, "Fractional count reached the CAD builder"
            assert page.locator("#download").is_disabled()
            assert page.locator("#download-cad").is_disabled()
            columns.fill(original)
            assert columns.evaluate("input => input.validity.valid")
            assert not page.locator("#download").is_disabled()
            assert not page.locator("#download-cad").is_disabled()

        def original_refreshes_once(page):
            jobs = []
            def generate(route):
                value = route.request.post_data_json
                jobs.append(value.get("format", "stl"))
                body, metadata, mesh = (original_zip, original_meta, original_mesh) if value["parameters"]["length"] == 150 else (custom_zip, custom_meta, custom_mesh)
                if value.get("format") == "cad":
                    reply(route, body, metadata)
                else:
                    preview_reply(route, mesh, metadata)
            page.route("**/api/generate", generate)
            library(page)
            ready(page)
            with page.expect_download() as event:
                page.locator("#download-cad").click()
            assert event.value.suggested_filename == "parts_tray-cad.zip"
            assert jobs == ["stl", "cad"], jobs
            assert page.locator("#model-size").inner_text() == "150 × 100 × 24"
            assert not page.locator("#download").is_disabled()
            with page.expect_download() as event:
                page.locator("#download-cad").click()
            assert Path(event.value.path()).read_bytes() == original_zip
            assert jobs == ["stl", "cad"], "Repeated download rebuilt already verified CAD files"
            page.locator('[data-parameter="length"]').fill("180.5")
            assert page.locator("#download-cad").is_disabled()
            page.locator("#rebuild").click()
            page.wait_for_function("() => !document.querySelector('#download-cad').disabled")
            with page.expect_download() as event:
                page.locator("#download-cad").click()
            assert Path(event.value.path()).read_bytes() == custom_zip, "A new preview reused the old CAD download"
            assert jobs == ["stl", "cad", "stl", "cad"]
            page.locator('[data-parameter="length"]').fill("")
            assert page.locator("#download-cad").is_disabled()
            page.locator('[data-parameter="length"]').fill("180.5")
            with page.expect_download() as event:
                page.locator("#download-cad").click()
            assert Path(event.value.path()).read_bytes() == custom_zip
            assert jobs == ["stl", "cad", "stl", "cad"], "Returning to verified dimensions rebuilt the CAD files"
            page.locator("#close-editor").click()
            page.wait_for_function("() => !new URL(location.href).searchParams.has('model')")
            ready(page)
            with page.expect_download() as event:
                page.locator("#download-cad").click()
            assert Path(event.value.path()).read_bytes() == original_zip, "A reopened model retained another preview's CAD download"
            assert jobs == ["stl", "cad", "stl", "cad", "stl", "cad"]

        def dirty_and_invalid(page):
            jobs = []
            page.route("**/api/generate", lambda route: jobs.append(route))
            library(page)
            ready(page)
            for value in ("180.5", ""):
                page.locator('[data-parameter="length"]').fill(value)
                assert page.locator("#download-cad").is_disabled()
                assert page.locator("#download").is_disabled()
            assert not jobs

        def edits_during_export(page):
            waiting, downloads = [], []
            page.on("download", lambda item: downloads.append(item))
            custom(page, waiting.append)
            for value in ("190.5", ""):
                page.locator('[data-parameter="length"]').fill("180.5")
                page.locator("#download-cad").click()
                route = pending(page, waiting)
                assert page.locator("#rebuild").is_disabled()
                assert page.locator("#download").is_disabled()
                page.locator('[data-parameter="length"]').fill(value)
                reply(route, custom_zip, custom_meta)
                page.wait_for_function("() => !document.querySelector('#rebuild').disabled")
                assert not downloads, "Unapplied or invalid edits triggered an obsolete CAD download"
                assert page.locator("#download-cad").is_disabled()
                assert page.locator("#model-size").inner_text() == "180.5 × 100 × 24"

        def navigation_during_export(page):
            downloads = []
            page.on("download", lambda item: downloads.append(item))
            page.add_init_script(DEFERRED_BODY + """const fetchOriginal = window.fetch;
              window.fetch = async (...args) => {
                const response = await fetchOriginal(...args);
                if (String(args[0]).includes('/api/generate') && JSON.parse(args[1].body).format === 'cad') {
                  const bytes = await response.arrayBuffer();
                  window.deferFileBody(response, bytes, () => new Promise(resolve => { window.releaseExport = resolve; }));
                }
                return response;
              };""")
            custom(page)
            page.locator("#download-cad").click()
            page.wait_for_function("() => typeof window.releaseExport === 'function'")
            page.go_back()
            page.wait_for_function("() => !document.querySelector('#editor').open")
            ready(page, "cable_comb")
            page.evaluate("window.releaseExport()")
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            assert not downloads
            assert "Building" not in page.locator("#form-message").inner_text()
            assert page.locator("#model-title").inner_text() != "Divided parts tray"

        def transfer_and_metadata_failures(page):
            failures_to_send, downloads = [], []
            def handler(route):
                body, metadata = failures_to_send.pop(0)
                reply(route, body, metadata)
            custom(page, handler)
            page.on("download", lambda item: downloads.append(item))
            corrupted = bytearray(custom_zip)
            corrupted[-1] ^= 1
            for body, metadata in [
                (bytes(corrupted), custom_meta),
                (custom_zip, {**custom_meta, "mesh_sha256": "0" * 64}),
                (custom_zip, {**custom_meta, "model": "cable_comb"}),
                (b"not a zip", {**custom_meta, "file_sha256": hashlib.sha256(b"not a zip").hexdigest()}),
            ]:
                failures_to_send.append((body, metadata))
                page.locator("#download-cad").click()
                page.wait_for_function("() => !document.querySelector('#rebuild').disabled")
                assert "error" in page.locator("#form-message").get_attribute("class")
                assert not downloads
                assert not page.locator("#download").is_disabled(), "Export failure discarded the verified preview"

        def service_failure_and_retry(page):
            jobs = []
            def handler(route):
                jobs.append(route)
                if len(jobs) == 1:
                    route.fulfill(status=503, json={"error": "The CAD builder is busy. Try again shortly."})
                else:
                    reply(route, custom_zip, custom_meta)
            custom(page, handler)
            page.locator("#download-cad").click()
            page.wait_for_function("() => document.querySelector('#form-message').classList.contains('error')")
            assert "busy" in page.locator("#form-message").inner_text()
            assert not page.locator("#download-cad").is_disabled()
            with page.expect_download() as event:
                page.locator("#download-cad").click()
            assert Path(event.value.path()).read_bytes() == custom_zip
            assert len(jobs) == 2

        def reference_assembly(page):
            jobs = []
            def generate(route):
                jobs.append(route.request.post_data_json.get("format", "stl"))
                if route.request.post_data_json.get("format") == "cad":
                    reply(route, assembly_zip, assembly_meta)
                else:
                    preview_reply(route, assembly_mesh, assembly_preview)
            page.route("**/api/generate", generate)
            library(page)
            ready(page, "soap_dish_assembly")
            assert page.locator("#download").is_hidden()
            page.locator('[data-parameter="length"]').fill("160")
            page.locator("#rebuild").click()
            page.wait_for_function("() => !document.querySelector('#download-cad').disabled")
            with page.expect_download() as event:
                page.locator("#download-cad").click()
            with ZipFile(event.value.path()) as archive:
                assert "soap_dish_assembly.step" in archive.namelist()
                assert "soap_dish_assembly.stl" not in archive.namelist()
                assert "soap_dish_assembly.3mf" not in archive.namelist()
                for part in assembly_meta["kit"]:
                    for extension in ("step", "stl", "3mf"):
                        assert f"parts/{part['model']}/{part['model']}.{extension}" in archive.namelist()
                assert event.value.suggested_filename == f"soap_dish_assembly-custom-160x84x14mm-{assembly_meta['file_sha256'][:12]}-kit.zip"
            assert "Print the components separately" in page.locator("#form-message").inner_text()
            with page.expect_download() as event:
                page.locator("#download-cad").click()
            assert Path(event.value.path()).read_bytes() == assembly_zip
            assert jobs == ["stl", "cad"], "Repeated kit download started another CAD build"

        def kit_quantities_and_fit_coupons(page):
            library(page)
            for name, model, text in (("sanding_assembly", "sanding_wedge", "× 2"),
                                      ("strap_clamp_assembly", "strap_corner", "× 4"),
                                      ("sliding_box_assembly", "sliding_fit_channel", "Fit coupon")):
                ready(page, name)
                assert "Download parts kit" in page.locator("#download-cad").inner_text()
                assert text in page.locator(f'[data-part="{model}"]').inner_text()
                assert page.locator("#download").is_hidden()
                if name == "sliding_box_assembly":
                    assert "Fit coupon" in page.locator('[data-part="sliding_fit_slider"]').inner_text()
                    assert "× 1" in page.locator('[data-part="sliding_box"]').inner_text()
                page.locator("#close-editor").click()
                page.wait_for_function("() => !new URL(location.href).searchParams.has('model')")
            ready(page, "sanding_assembly")
            page.locator("#parts").scroll_into_view_if_needed()
            page.screenshot(path=str(ROOT / "review/cloud_assembly_kit.png"))

        def mismatched_kit_inventory(page):
            replies, downloads = [], []
            page.on("download", lambda item: downloads.append(item))
            def generate(route):
                if route.request.post_data_json.get("format") == "cad":
                    reply(route, assembly_zip, replies.pop(0))
                else:
                    preview_reply(route, assembly_mesh, assembly_preview)
            page.route("**/api/generate", generate)
            library(page)
            ready(page, "soap_dish_assembly")
            page.locator('[data-parameter="length"]').fill("160")
            page.locator("#rebuild").click()
            page.wait_for_function("() => !document.querySelector('#download-cad').disabled")
            for kit in (None, [None, None],
                        [assembly_meta["kit"][0], assembly_meta["kit"][0]],
                        [{**part, "quantity": part["quantity"] + 1} for part in assembly_meta["kit"]]):
                replies.append({**assembly_meta, "kit": kit})
                page.locator("#download-cad").click()
                page.wait_for_function("() => !document.querySelector('#rebuild').disabled")
                assert "parts kit does not match" in page.locator("#form-message").inner_text()
                assert not downloads
                assert not page.locator("#download-cad").is_disabled()

        def malformed_kit_catalog(page):
            catalog = json.loads((CLOUD / "public/catalog.json").read_text())
            examples = []
            for value in (0, 1.5, "2"):
                data = copy.deepcopy(catalog)
                assembly = next(model for model in data["models"] if model["name"] == "sanding_assembly")
                assembly["kit"][0]["quantity"] = value
                examples.append(data)
            data = copy.deepcopy(catalog)
            assembly = next(model for model in data["models"] if model["name"] == "sanding_assembly")
            assembly["parts"][0] = "soap_dish_assembly"
            assembly["kit"][0]["model"] = "soap_dish_assembly"
            examples.append(data)
            for data in examples:
                def respond(route):
                    route.fulfill(json=data)
                page.route("**/catalog.json", respond)
                page.goto(BASE)
                page.wait_for_function("() => !document.querySelector('#catalog-failure').hidden")
                assert page.locator(".card").count() == 0, "Malformed inventory published printable kit cards"
                page.unroute("**/catalog.json")

        def scrolled_editor_close_control(page):
            for width, height in ((1440, 1080), (390, 844)):
                page.set_viewport_size({"width": width, "height": height})
                library(page)
                ready(page, "sanding_assembly")
                page.locator("#parts").scroll_into_view_if_needed()
                close = page.locator("#close-editor")
                rect = close.bounding_box()
                assert 0 <= rect["x"] and rect["x"] + rect["width"] <= width, rect
                assert 0 <= rect["y"] and rect["y"] + rect["height"] <= height, rect
                assert close.evaluate("element => { const r=element.getBoundingClientRect(); return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest('#close-editor') === element; }")
                if width == 390:
                    page.screenshot(path=str(ROOT / "review/cloud_assembly_kit_mobile.png"))
                close.click()
                page.wait_for_function("() => !document.querySelector('#editor').open && !new URL(location.href).searchParams.has('model')")

        def mobile_and_no_webgl(page):
            page.set_viewport_size({"width": 390, "height": 844})
            page.add_init_script("""const originalContext = HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                if (type.startsWith('webgl')) return null;
                return originalContext.call(this, type, ...args);
              };""")
            custom(page)
            page.wait_for_function("() => document.querySelector('#viewer').getAttribute('aria-busy') === 'false'")
            assert page.locator("#preview-badge").text_content() == "Original catalog image"
            page.locator("#download-cad").scroll_into_view_if_needed()
            assert page.evaluate("document.querySelector('#editor').scrollWidth <= document.querySelector('#editor').clientWidth")
            with page.expect_download() as event:
                page.locator("#download-cad").click()
            assert Path(event.value.path()).read_bytes() == custom_zip
            page.screenshot(path=str(ROOT / "review/cloud_cad_download_mobile.png"))

        for test in (real_custom_download, integer_counts_remain_whole, original_refreshes_once, dirty_and_invalid,
                     edits_during_export, navigation_during_export, transfer_and_metadata_failures,
                     service_failure_and_retry, reference_assembly, mobile_and_no_webgl,
                     kit_quantities_and_fit_coupons, mismatched_kit_inventory, malformed_kit_catalog,
                     scrolled_editor_close_control):
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
                failures.append(dict(test=test.__name__, error=str(error), traceback=details, url=page.url, browser_errors=errors))
                print(f"FAIL {test.__name__}: {details}", flush=True)
            finally:
                page.close()
        context.close()
        browser.close()
    report = dict(endpoint=BASE, passed=passed, failures=failures,
        custom_archive_sha256=hashlib.sha256(custom_zip).hexdigest(),
        custom_mesh_sha256=custom_meta["mesh_sha256"], real_cad_download=True,
        transport="compiled assets and native jobs through Playwright routes" if OFFLINE else "local HTTP bridge")
    (ROOT / "review/cloud_export_ui_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert not failures, report


if __name__ == "__main__":
    main()
