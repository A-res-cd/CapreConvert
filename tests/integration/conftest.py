import pytest
from fastapi.testclient import TestClient

from localraw.app import create_app
from tests.support import controlled_worker, login

BASE = "http://127.0.0.1:8765"


@pytest.fixture
def api(settings, ample_memory):
    settings.lan = True
    app = create_app(settings, worker_target=controlled_worker)
    with TestClient(app, base_url=BASE, client=("127.0.0.1", 50000), headers={"Origin": BASE}) as client:
        login(client, app)
        yield client, app
