from __future__ import annotations

import logging
import time

import pytest
from fastapi.testclient import TestClient

from spectra.config import Settings
from spectra.container import build_container
from spectra.main import create_app
from tests.plugins_for_tests import ALL_TEST_PLUGINS

logging.getLogger("httpx").setLevel(logging.WARNING)

TERMINAL = {"succeeded", "failed", "cancelled"}


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        allowed_hosts=["testserver"],
        serve_frontend=False,
        min_free_disk_bytes=0,
        max_concurrent_jobs=2,
        default_job_timeout_seconds=60,
        max_upload_bytes=64 * 1024 * 1024,
        log_level="WARNING",
    )


@pytest.fixture
def container(settings):
    c = build_container(settings, load_entry_points=False)
    for plugin in ALL_TEST_PLUGINS:
        c.registry.register(plugin)
    yield c
    c.close()


@pytest.fixture
def client(settings, container):
    app = create_app(settings, container=container)
    with TestClient(app) as tc:
        yield tc


@pytest.fixture
def case(client):
    r = client.post("/api/cases", json={"name": "Test case", "description": "fixture"})
    assert r.status_code == 201, r.text
    return r.json()


def upload(client, case_id: str, data: bytes, name: str = "sample.bin"):
    return client.post(f"/api/cases/{case_id}/evidence", params={"filename": name}, content=data)


@pytest.fixture
def evidence(client, case):
    r = upload(client, case["id"], b"SPECTRA-evidence-" + bytes(range(256)) * 4, "sample.bin")
    assert r.status_code == 201, r.text
    return r.json()


def wait_for_job(client, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in TERMINAL:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s: {job}")


def wait_for_status(client, job_id: str, status: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] == status:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} never reached {status}: {job}")


def run_job(client, evidence_id: str, plugin_id: str, config: dict | None = None, **kw) -> dict:
    r = client.post(
        "/api/jobs", json={"evidence_id": evidence_id, "plugin_id": plugin_id, "config": config or {}, **kw}
    )
    assert r.status_code == 202, r.text
    return r.json()
