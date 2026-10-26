"""Native frozen-app browser previews/direct exports; no conversion doubles."""

import argparse
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx
from PIL import Image
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--libreoffice", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--memory-profile", choices=("default", "compact"), default="default")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Report exists; choose a new output")
    benchmark = module("memory_benchmark", "scripts/benchmark-memory.py")
    smoke = module("package_smoke", "scripts/smoke-package.py")
    report = {"version": "1.0.0", "checks": [], "memory_profile": args.memory_profile}
    options = argparse.Namespace(
        executable=args.executable.resolve(),
        source_root=ROOT,
        interval=0.1,
        timeout=300,
        stderr_path=ROOT / ".cache/v1-frozen-browser-server.log",
    )
    with tempfile.TemporaryDirectory(prefix="frozen-v1-", dir=ROOT / "test-results") as temporary:
        directory = Path(temporary)
        config = {"libreoffice": str(args.libreoffice.resolve())}
        if args.memory_profile == "compact":
            config.update(document_memory_bytes=384 * 1024**2, preview_memory_bytes=256 * 1024**2)
        with benchmark.Application(options, directory / "app", config) as app:
            assert app.capabilities["application_version"] == "1.0.0"
            # Finish native conversions before launching Chromium on this RAM-limited host.
            content = "Actual frozen DOCX content preview <script>safe text</script>"
            docx_id, job = smoke.upload_and_run(
                app.client, "source.pdf", smoke.minimal_pdf(content), "pdf_to_docx"
            )
            assert job["state"] == "completed"
            docx_item = app.files(docx_id)[0]
            docx = app.client.get(f"/api/v1/jobs/{docx_id}/results/{docx_item['output_id']}").content
            pdf_id, job = smoke.upload_and_run(app.client, "source.docx", docx, "docx_to_pdf")
            assert job["state"] == "completed", app.files(pdf_id)
            encoded = io.BytesIO()
            with Image.new("RGBA", (60, 40), (20, 70, 120, 40)) as image:
                image.save(encoded, format="PNG")
            paths = []
            for name in ("one.png", "two.png"):
                path = directory / name
                path.write_bytes(encoded.getvalue())
                paths.append(path)
            ids = [app.upload(path) for path in paths]
            response = app.client.post(
                "/api/v1/jobs",
                json={
                    "upload_ids": ids,
                    "settings": {"conversion": "png_to_webp", "raster": {"webp_lossless": True}},
                },
            )
            response.raise_for_status()
            image_id = response.json()["id"]
            job, _ = app.wait(image_id)
            assert job["state"] == "completed", app.files(image_id)
            files = app.files(image_id)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    accept_downloads=True, viewport={"width": 1280, "height": 950}
                )
                context.add_cookies(
                    [
                        {
                            "name": cookie.name,
                            "value": cookie.value,
                            "url": app.base,
                            "httpOnly": True,
                            "sameSite": "Strict",
                        }
                        for cookie in app.client.cookies.jar
                    ]
                )
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(app.base + "/#home")
                expect(page.locator("#picker-input")).to_be_enabled(timeout=20000)
                expect(page.locator("#picker-input optgroup")).to_have_count(2)
                page.locator("#picker-input").select_option("pdf")
                expect(page.locator("#picker-output")).to_have_value("docx")
                page.locator("#open-converter").click()

                expect(page.locator("#docx-content")).to_contain_text(content, timeout=20000)
                expect(page.locator("#docx-content script")).to_have_count(0)
                with page.expect_download() as download:
                    page.locator("#download-primary").click()
                destination = directory / "actual.docx"
                download.value.save_as(destination)
                assert destination.read_bytes() == docx
                page.screenshot(path=str(ROOT / "test-results/v1-frozen-docx.png"), full_page=True)
                report["checks"].append(
                    "actual PDF-to-DOCX, safe content preview, primary direct DOCX bytes"
                )
                page.goto(app.base + "/#convert=docx_to_pdf")
                expect(page.locator("#active-preview")).to_be_visible(timeout=20000)
                expect(page.locator("#pdf-page-status")).to_have_text("Page 1 of 1")
                with page.expect_download() as download:
                    page.locator("#preview-download").click()
                download.value.save_as(directory / "actual.pdf")
                assert (directory / "actual.pdf").read_bytes().startswith(b"%PDF-")
                page.screenshot(path=str(ROOT / "test-results/v1-frozen-pdf.png"), full_page=True)
                report["checks"].append(
                    "actual external LibreOffice PDF, bundled PDFium visual preview, direct PDF"
                )
                page.get_by_role("link", name="CapreConvert home", exact=True).click()
                page.locator("#picker-input").select_option("png")
                page.locator("#picker-output").select_option("webp")
                page.locator("#open-converter").click()
                expect(page.locator("#active-preview")).to_be_visible(timeout=20000)
                page.get_by_role("checkbox", name="Export files/one.webp as WEBP", exact=True).check()
                with page.expect_download() as download:
                    page.locator("#export-selected").click()
                path = directory / "one.webp"
                download.value.save_as(path)
                assert (
                    path.read_bytes()
                    == app.client.get(f"/api/v1/jobs/{image_id}/results/{files[0]['output_id']}").content
                )
                page.locator("#select-all-previews").click()
                with page.expect_download() as download:
                    page.locator("#export-selected").click()
                path = directory / "selected.zip"
                download.value.save_as(path)
                with zipfile.ZipFile(path) as archive:
                    assert archive.namelist() == ["files/one.webp", "files/two.webp"]
                    assert archive.testzip() is None
                    for item in files:
                        assert (
                            hashlib.sha256(archive.read(item["output_name"])).hexdigest()
                            == item["sha256"]
                        )
                page.reload()
                expect(
                    page.get_by_role("checkbox", name="Export files/one.webp as WEBP", exact=True)
                ).to_be_checked()
                context.close()
                browser.close()
                report["checks"].append(
                    "actual lossless WebP/alpha previews, one-selected actual file, exact multi-file ZIP, refresh selection"
                )
                assert not errors, errors
            with httpx.Client(base_url=app.base, trust_env=False) as foreign:
                for route in (
                    f"/api/v1/jobs/{image_id}/results/{files[0]['output_id']}",
                    f"/api/v1/jobs/{image_id}/previews/{files[0]['output_id']}",
                    f"/api/v1/jobs/{pdf_id}/output-preview/{app.files(pdf_id)[0]['output_id']}",
                ):
                    assert foreign.get(route).status_code == 401
            report["checks"].append("unauthorized result/image/PDF-preview requests denied")
            assert not list(app.workspace.rglob("*.part"))
            assert app.client.get("/health").json() == {"status": "ok"}
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
