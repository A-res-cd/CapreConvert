"""Spawn/frozen-safe CLI; exactly one Uvicorn process."""

import argparse
import multiprocessing
import threading
import webbrowser
from pathlib import Path


def main():
    multiprocessing.freeze_support()
    from . import APP_NAME, __version__

    parser = argparse.ArgumentParser(
        prog="capreconvert", description=f"{APP_NAME}: private local document and RAW image conversion"
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--libreoffice", type=Path, help="Path to a local LibreOffice executable")
    parser.add_argument("--port", type=int)
    parser.add_argument("--lan", action="store_true", default=None)
    parser.add_argument("--no-browser", action="store_true")
    arguments = parser.parse_args()
    from .config import Settings

    try:
        settings = Settings.load(
            arguments.config,
            workspace=arguments.workspace,
            port=arguments.port,
            lan=arguments.lan,
            libreoffice=arguments.libreoffice,
        )
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    import uvicorn

    # Source spawn children import this module without launching the CLI. Keep the
    # server graph out of those image workers, as the frozen entrypoint already does.
    from .app import create_app

    app = create_app(settings)

    def ready(server):
        security = server.state.security
        scheme = "https" if settings.tls_cert else "http"
        url = f"{scheme}://127.0.0.1:{settings.port}/#bootstrap={security.bootstrap}"
        # Deliberate host-console display; tokens never enter access/error logging.
        print(
            f"{APP_NAME} {__version__} ready. Local browser link (valid 2 minutes):\n{url}", flush=True
        )
        if settings.lan:
            for address in security.addresses:
                print(f"LAN: {scheme}://{address}:{settings.port}", flush=True)
            print(f"Pairing code (keep private): {security.pairing}", flush=True)
        if not arguments.no_browser:
            timer = threading.Timer(0.7, webbrowser.open, args=(url,))
            timer.daemon = True
            timer.start()

    app.state.on_ready = ready
    uvicorn.run(
        app,
        host="0.0.0.0" if settings.lan else "127.0.0.1",
        port=settings.port,
        workers=1,
        proxy_headers=False,
        access_log=False,
        ssl_certfile=str(settings.tls_cert) if settings.tls_cert else None,
        ssl_keyfile=str(settings.tls_key) if settings.tls_key else None,
    )


if __name__ == "__main__":
    main()
