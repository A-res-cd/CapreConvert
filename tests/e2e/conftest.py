import socket
import threading
import time

import pytest
import uvicorn
from playwright.sync_api import sync_playwright

from localraw.app import create_app
from tests.e2e.support import ui_conversion_worker


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def live_server(settings, ample_memory):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    settings.port = sock.getsockname()[1]
    settings.lan = True
    settings.cancel_grace_seconds = 0.1
    app = create_app(settings, worker_target=ui_conversion_worker)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=settings.port,
            log_level="error",
            access_log=False,
            proxy_headers=False,
        )
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("Test server did not start")
        time.sleep(0.02)
    try:
        yield app, f"http://127.0.0.1:{settings.port}"
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        sock.close()
        assert not thread.is_alive()
