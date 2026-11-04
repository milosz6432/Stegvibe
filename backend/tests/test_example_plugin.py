"""The example plugin documented in docs/PLUGINS.md must really work through the production job path."""

from __future__ import annotations

import csv
import io
from collections import Counter

import pytest

from examples.byte_entropy_plugin import ByteEntropyPlugin, shannon_entropy
from tests.conftest import run_job, upload, wait_for_job

PLUGIN_ID = "example.byte_entropy"


@pytest.fixture
def entropy_client(container, client):
    container.registry.register(ByteEntropyPlugin, source="example")
    return client


def _run(client, case_id: str, data: bytes, config: dict | None = None) -> dict:
    ev = upload(client, case_id, data, "entropy.bin")
    assert ev.status_code == 201, ev.text
    job = wait_for_job(client, run_job(client, ev.json()["id"], PLUGIN_ID, config)["id"])
    assert job["status"] == "succeeded", job
    return job


def _profile(client, job: dict) -> list[dict]:
    r = client.get(f"/api/jobs/{job['id']}/artifacts/entropy_profile.csv")
    assert r.status_code == 200
    return list(csv.DictReader(io.StringIO(r.text)))


def test_entropy_function_matches_known_values():
    assert shannon_entropy(Counter(b"\x00" * 100), 100) == 0.0
    assert shannon_entropy(Counter(b"ab" * 50), 100) == pytest.approx(1.0)
    assert shannon_entropy(Counter(bytes(range(256)) * 4), 1024) == pytest.approx(8.0)
    # 75% / 25% split: -(0.75*log2(0.75) + 0.25*log2(0.25)), computed independently
    assert shannon_entropy(Counter(b"aaab" * 16), 64) == pytest.approx(0.8112781244591328)
    assert shannon_entropy(Counter(), 0) == 0.0


def test_constant_data_has_zero_entropy_and_no_anomaly(entropy_client, case):
    job = _run(entropy_client, case["id"], b"\x00" * 8192)
    summary = job["result"]["summary"]
    assert summary["overall_entropy_bits"] == 0.0 and summary["windows"] == 2
    assert summary["high_entropy_regions"] == 0

    page = entropy_client.get("/api/findings", params={"job_id": job["id"]}).json()
    assert [f["kind"] for f in page["items"]] == ["info"]
    assert [row["entropy_bits"] for row in _profile(entropy_client, job)] == ["0.000000", "0.000000"]


def test_uniform_window_is_reported_as_a_low_confidence_region(entropy_client, case):
    data = b"\x00" * 4096 + bytes(range(256)) * 16 + b"\x00" * 4096  # constant | uniform | constant
    job = _run(entropy_client, case["id"], data)

    summary = job["result"]["summary"]
    assert summary["windows"] == 3 and summary["high_entropy_windows"] == 1
    assert summary["max_window_entropy_bits"] == 8.0 and summary["min_window_entropy_bits"] == 0.0

    items = entropy_client.get("/api/findings", params={"job_id": job["id"]}).json()["items"]
    anomalies = [f for f in items if f["kind"] == "statistical_anomaly"]
    assert len(anomalies) == 1
    f = anomalies[0]
    assert f["location"] == {"byte_offset": 4096, "length": 4096}
    assert f["confidence"] == "low"  # a heuristic is never presented as certain
    assert "compressed" in f["limitations"]

    rows = _profile(entropy_client, job)
    assert [(int(r["offset"]), float(r["entropy_bits"])) for r in rows] == [
        (0, 0.0),
        (4096, 8.0),
        (8192, 0.0),
    ]


def test_adjacent_high_entropy_windows_merge_and_partial_tail_is_disclosed(entropy_client, case):
    data = bytes(range(256)) * 32 + b"abc"  # two uniform 4096-byte windows + 3 trailing bytes
    job = _run(entropy_client, case["id"], data)

    assert job["result"]["summary"]["windows"] == 2
    assert job["result"]["summary"]["high_entropy_regions"] == 1
    items = entropy_client.get("/api/findings", params={"job_id": job["id"]}).json()["items"]
    region = next(f for f in items if f["kind"] == "statistical_anomaly")
    assert region["location"] == {"byte_offset": 0, "length": 8192}
    assert any("last 3 bytes" in w for w in job["result"]["warnings"])


def test_small_file_reports_that_no_window_could_be_analysed(entropy_client, case):
    job = _run(entropy_client, case["id"], b"tiny")
    assert job["result"]["summary"]["windows"] == 0
    assert job["result"]["summary"]["min_window_entropy_bits"] is None
    assert any("smaller than one window" in w for w in job["result"]["warnings"])


def test_region_cap_is_applied_and_disclosed(entropy_client, case):
    # alternate uniform / constant windows -> many separate regions
    block = bytes(range(64))
    data = b"".join((block if i % 2 == 0 else b"\x00" * 64) for i in range(10))
    job = _run(
        entropy_client,
        case["id"],
        data,
        {"window_bytes": 64, "high_threshold_bits": 6.0, "max_findings": 2},
    )
    assert job["result"]["summary"]["high_entropy_regions"] == 5
    items = entropy_client.get("/api/findings", params={"job_id": job["id"]}).json()["items"]
    assert len([f for f in items if f["kind"] == "statistical_anomaly"]) == 2
    assert any("only the first 2" in w for w in job["result"]["warnings"])


def test_invalid_config_is_rejected_before_any_job_is_created(entropy_client, evidence):
    r = entropy_client.post(
        "/api/jobs",
        json={"evidence_id": evidence["id"], "plugin_id": PLUGIN_ID, "config": {"window_bytes": 8}},
    )
    assert r.status_code == 422
    r = entropy_client.post(
        "/api/jobs", json={"evidence_id": evidence["id"], "plugin_id": PLUGIN_ID, "config": {"bogus": 1}}
    )
    assert r.status_code == 422


def test_plugin_metadata_is_exposed_with_schema_and_limitations(entropy_client):
    info = next(p for p in entropy_client.get("/api/plugins").json() if p["id"] == PLUGIN_ID)
    assert info["source"] == "example" and info["deterministic"] is False and info["available"] is True
    assert info["limitations"] and "window_bytes" in info["config_schema"]["properties"]
    assert info["summary_schema"]["properties"]["windows"]
