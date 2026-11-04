"""Acceptance 1.4 (originals untouched) and 1.6 (job isolation, cancellation, limits, recovery)."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import pytest
from sqlalchemy import select

from spectra.db.base import utcnow
from spectra.db.models import Evidence, Job
from tests.conftest import run_job, upload, wait_for_job, wait_for_status

posix_only = pytest.mark.skipif(
    not hasattr(os, "killpg"), reason="process groups / rlimits are POSIX features"
)


def _original(settings, ev) -> Path:
    return settings.cases_dir / ev["case_id"] / "originals" / ev["id"]


# ---- success path ---------------------------------------------------------------
def test_job_runs_in_a_subprocess_persists_findings_and_leaves_the_original_untouched(
    client, evidence, settings
):
    path = _original(settings, evidence)
    before = (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)

    job = run_job(client, evidence["id"], "test.noop")
    assert job["status"] in {"queued", "running"} and job["plugin_version"] == "1.0.0"
    done = wait_for_job(client, job["id"])

    assert done["status"] == "succeeded" and done["progress"] == 1.0 and done["error_code"] is None
    assert done["result"]["summary"]["size"] == evidence["size_bytes"]
    assert done["result"]["warnings"] == ["a warning"] and done["result"]["finding_count"] == 1
    assert done["started_at"] and done["finished_at"]

    page = client.get("/api/findings", params={"job_id": job["id"]}).json()
    assert page["total"] == 1
    f = page["items"][0]
    assert (
        f["plugin_id"] == "test.noop"
        and f["kind"] == "info"
        and f["location"] == {"byte_offset": 0, "length": 1}
    )
    assert f["evidence_sha256"] == evidence["sha256"] and f["config"] == job["config"]  # reproducible context

    assert (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode) == before
    assert hashlib.sha256(path.read_bytes()).hexdigest() == evidence["sha256"]


def test_progress_is_reported_while_running(client, evidence):
    job = run_job(client, evidence["id"], "test.slow", {"seconds": 6})
    wait_for_status(client, job["id"], "running")
    seen = 0.0
    msg = ""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and seen <= 0:
        cur = client.get(f"/api/jobs/{job['id']}").json()
        seen, msg = cur["progress"], cur["progress_message"]
        time.sleep(0.1)
    assert 0 < seen < 1 and msg.endswith("s")
    client.post(f"/api/jobs/{job['id']}/cancel")


def test_job_listing_and_filters(client, evidence):
    a = run_job(client, evidence["id"], "test.noop")
    wait_for_job(client, a["id"])
    b = run_job(client, evidence["id"], "test.raise")
    wait_for_job(client, b["id"])
    assert {j["id"] for j in client.get("/api/jobs", params={"evidence_id": evidence["id"]}).json()} == {
        a["id"],
        b["id"],
    }
    assert [j["id"] for j in client.get("/api/jobs", params={"status": "failed"}).json()] == [b["id"]]
    assert client.get("/api/jobs", params={"status": "bogus"}).status_code == 422
    assert client.get("/api/jobs/unknown").status_code == 404


# ---- integrity plugin ---------------------------------------------------------------
def test_integrity_verification_confirms_untouched_evidence(client, evidence):
    done = wait_for_job(client, run_job(client, evidence["id"], "core.integrity_verify")["id"])
    assert done["status"] == "succeeded"
    s = done["result"]["summary"]
    assert (
        s["match"] is True
        and s["size_matches"]
        and s["read_only"]
        and s["bytes_hashed"] == evidence["size_bytes"]
    )
    f = client.get("/api/findings", params={"job_id": done["id"]}).json()["items"][0]
    assert f["kind"] == "integrity" and f["confidence"] == "verified" and "match" in f["title"]
    assert f["limitations"]  # even a positive result states what it does not prove


def test_integrity_verification_detects_modified_evidence(client, evidence, settings):
    path = _original(settings, evidence)
    path.chmod(0o644)
    with open(path, "ab") as fh:  # simulate tampering after import
        fh.write(b"X")
    done = wait_for_job(
        client, run_job(client, evidence["id"], "core.integrity_verify", {"chunk_size_kib": 4})["id"]
    )
    assert done["status"] == "succeeded"  # the job ran fine; it *found* a problem
    assert done["result"]["summary"]["match"] is False
    assert any("writable" in w for w in done["result"]["warnings"])
    f = client.get("/api/findings", params={"job_id": done["id"]}).json()["items"][0]
    assert f["title"].startswith("INTEGRITY FAILURE")
    assert set(f["data"]["mismatched_algorithms"]) == {"md5", "sha1", "sha256"}
    assert f["data"]["actual_size"] == evidence["size_bytes"] + 1


# ---- cancellation ---------------------------------------------------------------------
def test_cancel_running_job(client, evidence, settings):
    job = run_job(client, evidence["id"], "test.slow", {"seconds": 120})
    wait_for_status(client, job["id"], "running")
    t0 = time.monotonic()
    r = client.post(f"/api/jobs/{job['id']}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert time.monotonic() - t0 < 8
    assert r.json()["error_code"] == "cancelled" and r.json()["finished_at"]
    assert not (settings.cases_dir / evidence["case_id"] / "derived" / job["id"]).exists()
    actions = [e["action"] for e in client.get("/api/audit", params={"job_id": job["id"]}).json()]
    assert "job.cancelled" in actions
    # cancelling again is idempotent
    assert client.post(f"/api/jobs/{job['id']}/cancel").json()["status"] == "cancelled"


def test_cancel_queued_job_before_it_ever_runs(client, evidence):
    # the fixture pool has 2 workers: two slow jobs occupy it, the third must wait in the queue
    blockers = [run_job(client, evidence["id"], "test.slow", {"seconds": 120}) for _ in range(2)]
    for b in blockers:
        wait_for_status(client, b["id"], "running")
    queued = run_job(client, evidence["id"], "test.slow", {"seconds": 120})
    assert client.get(f"/api/jobs/{queued['id']}").json()["status"] == "queued"

    r = client.post(f"/api/jobs/{queued['id']}/cancel").json()
    assert r["status"] == "cancelled" and r["started_at"] is None  # never started

    for b in blockers:
        client.post(f"/api/jobs/{b['id']}/cancel")
    # the cancelled job must not start once a slot frees up
    time.sleep(1.0)
    assert client.get(f"/api/jobs/{queued['id']}").json()["status"] == "cancelled"
    assert client.get(f"/api/jobs/{queued['id']}").json()["started_at"] is None


def _alive(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] != "Z"  # zombies are dead


@posix_only
@pytest.mark.skipif(not Path("/proc").exists(), reason="needs /proc")
def test_cancel_kills_helper_processes_the_plugin_started(client, evidence, tmp_path):
    pid_file = tmp_path / "child.pid"
    job = run_job(client, evidence["id"], "test.spawn_child", {"pid_file": str(pid_file)})
    deadline = time.monotonic() + 15
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    time.sleep(0.2)
    child_pid = int(pid_file.read_text())
    assert _alive(child_pid)

    assert client.post(f"/api/jobs/{job['id']}/cancel").json()["status"] == "cancelled"
    deadline = time.monotonic() + 8
    while _alive(child_pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not _alive(child_pid), "helper process outlived its cancelled job"


# ---- limits ---------------------------------------------------------------------------
def test_timeout_terminates_the_job(client, evidence):
    job = run_job(client, evidence["id"], "test.slow", {"seconds": 120}, timeout_seconds=2)
    t0 = time.monotonic()
    done = wait_for_job(client, job["id"], timeout=20)
    assert done["status"] == "failed" and done["error_code"] == "timeout"
    assert "2 s" in done["error_message"] and time.monotonic() - t0 < 15


@posix_only
def test_memory_limit_is_enforced_and_reported(client, evidence):
    hog = wait_for_job(
        client, run_job(client, evidence["id"], "test.memory", {"mb": 3072}, memory_limit_mb=1024)["id"]
    )
    assert hog["status"] == "failed" and hog["error_code"] == "memory"
    ok = wait_for_job(
        client, run_job(client, evidence["id"], "test.memory", {"mb": 32}, memory_limit_mb=1024)["id"]
    )
    assert ok["status"] == "succeeded" and ok["result"]["summary"]["allocated"] == 32 * 1024 * 1024


def test_limit_parameters_are_validated(client, evidence):
    base = {"evidence_id": evidence["id"], "plugin_id": "test.noop"}
    assert client.post("/api/jobs", json={**base, "timeout_seconds": 999999}).status_code == 422
    assert client.post("/api/jobs", json={**base, "timeout_seconds": 0}).status_code == 422
    assert client.post("/api/jobs", json={**base, "memory_limit_mb": 10}).status_code == 422
    assert client.post("/api/jobs", json={**base, "memory_limit_mb": 0}).status_code == 202


# ---- failure modes ------------------------------------------------------------------------
def test_clean_exit_without_result_is_reported_as_a_crash(client, evidence):
    done = wait_for_job(client, run_job(client, evidence["id"], "test.exit")["id"])
    assert (
        done["status"] == "failed"
        and done["error_code"] == "crashed"
        and "exit code 3" in done["error_message"]
    )


@posix_only
def test_killed_worker_is_reported_with_its_signal(client, evidence):
    done = wait_for_job(client, run_job(client, evidence["id"], "test.kill_self")["id"])
    assert (
        done["status"] == "failed" and done["error_code"] == "crashed" and "SIGKILL" in done["error_message"]
    )


def test_plugin_exception_is_reported_with_traceback(client, evidence):
    done = wait_for_job(client, run_job(client, evidence["id"], "test.raise")["id"])
    assert done["status"] == "failed" and done["error_code"] == "plugin_error"
    assert "ValueError: boom from plugin" in done["error_message"]
    assert "Traceback" in done["result"]["diagnostics"]["traceback"]


def test_plugin_returning_the_wrong_type_fails_cleanly(client, evidence):
    done = wait_for_job(client, run_job(client, evidence["id"], "test.wrong_return")["id"])
    assert done["status"] == "failed" and "expected PluginResult" in done["error_message"]


def test_heuristic_plugins_cannot_claim_verified_findings(client, evidence):
    done = wait_for_job(client, run_job(client, evidence["id"], "test.overclaim")["id"])
    assert done["status"] == "failed" and done["error_code"] == "invalid_result"
    assert "verified" in done["error_message"]
    assert (
        client.get("/api/findings", params={"job_id": done["id"]}).json()["total"] == 0
    )  # nothing was stored


# ---- submission validation -----------------------------------------------------------------------
def test_submission_validation(client, evidence, case, container):
    ev = evidence["id"]
    r = client.post("/api/jobs", json={"evidence_id": ev, "plugin_id": "no.such_plugin"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "plugin_not_found"
    r = client.post("/api/jobs", json={"evidence_id": "nope", "plugin_id": "test.noop"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "evidence_not_found"

    r = client.post("/api/jobs", json={"evidence_id": ev, "plugin_id": "test.missing_dep"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "plugin_unavailable"
    assert "spectra-no-such-binary-xyz" in r.json()["error"]["message"]
    assert (
        client.post("/api/jobs", json={"evidence_id": ev, "plugin_id": "test.optional_dep"}).status_code
        == 202
    )

    r = client.post("/api/jobs", json={"evidence_id": ev, "plugin_id": "test.bounded", "config": {"n": 99}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_plugin_config"
    assert r.json()["error"]["details"][0]["loc"] == ["n"]
    r = client.post(
        "/api/jobs", json={"evidence_id": ev, "plugin_id": "test.bounded", "config": {"bogus": 1}}
    )
    assert r.status_code == 422
    ok = client.post("/api/jobs", json={"evidence_id": ev, "plugin_id": "test.bounded"}).json()
    assert ok["config"] == {"n": 1}  # defaults are stored, so the run is reproducible


def test_format_gating(client, evidence, container):
    r = client.post("/api/jobs", json={"evidence_id": evidence["id"], "plugin_id": "test.png_only"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "format_not_identified"

    def set_format(fmt):
        with container.session_factory() as s:
            s.get(Evidence, evidence["id"]).detected_format = fmt
            s.commit()

    set_format("jpeg")
    r = client.post("/api/jobs", json={"evidence_id": evidence["id"], "plugin_id": "test.png_only"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "format_not_supported"
    set_format("png")
    assert (
        client.post(
            "/api/jobs", json={"evidence_id": evidence["id"], "plugin_id": "test.png_only"}
        ).status_code
        == 202
    )


def test_archived_case_rejects_new_jobs(client, case, evidence):
    client.patch(f"/api/cases/{case['id']}", json={"archived": True})
    r = client.post("/api/jobs", json={"evidence_id": evidence["id"], "plugin_id": "test.noop"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "case_archived"


def test_purge_is_refused_while_jobs_are_active(client, case, evidence):
    job = run_job(client, evidence["id"], "test.slow", {"seconds": 120})
    wait_for_status(client, job["id"], "running")
    r = client.post(f"/api/cases/{case['id']}/purge", json={"confirm_name": case["name"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "jobs_active"
    client.post(f"/api/jobs/{job['id']}/cancel")
    assert (
        client.post(f"/api/cases/{case['id']}/purge", json={"confirm_name": case["name"]}).status_code == 204
    )


# ---- artifacts ----------------------------------------------------------------------------------------
def test_artifacts_are_stored_apart_from_originals_listed_hashed_and_downloadable(client, evidence, settings):
    done = wait_for_job(client, run_job(client, evidence["id"], "test.artifact")["id"])
    assert done["status"] == "succeeded"
    arts = {a["name"]: a for a in done["result"]["artifacts"]}
    assert set(arts) == {"report.txt", "nested/data.bin"}  # the symlink to /etc/passwd is ignored
    assert arts["report.txt"]["sha256"] == hashlib.sha256(b"hello artifact").hexdigest()

    derived = settings.cases_dir / evidence["case_id"] / "derived" / done["id"]
    assert derived.is_dir() and not str(derived).startswith(
        str(settings.cases_dir / evidence["case_id"] / "originals")
    )

    r = client.get(f"/api/jobs/{done['id']}/artifacts/nested/data.bin")
    assert r.status_code == 200 and r.content == b"\x00\x01\x02"
    assert r.headers["content-disposition"].startswith("attachment")

    assert client.get(f"/api/jobs/{done['id']}/artifacts/evil").status_code == 404
    assert (
        client.get(f"/api/jobs/{done['id']}/artifacts/..%2F..%2Foriginals%2F{evidence['id']}").status_code
        == 404
    )
    assert client.get(f"/api/jobs/{done['id']}/artifacts/not-listed.txt").status_code == 404
    actions = [e["action"] for e in client.get("/api/audit", params={"job_id": done["id"]}).json()]
    assert "artifact.downloaded" in actions


# ---- restart recovery ------------------------------------------------------------------------------------
def test_jobs_interrupted_by_a_restart_are_marked_failed_and_audited(client, container, evidence):
    with container.session_factory() as s:
        ghosts = []
        for status in ("queued", "running"):
            j = Job(
                case_id=evidence["case_id"],
                evidence_id=evidence["id"],
                plugin_id="test.noop",
                plugin_version="1.0.0",
                config={},
                status=status,
                timeout_seconds=60,
                memory_limit_mb=0,
                started_at=utcnow(),
            )
            s.add(j)
            ghosts.append(j)
        s.commit()
        ids = [g.id for g in ghosts]
    assert container.jobs.recover_interrupted() == 2
    for jid in ids:
        j = client.get(f"/api/jobs/{jid}").json()
        assert j["status"] == "failed" and j["error_code"] == "interrupted"
        assert "job.interrupted" in [
            e["action"] for e in client.get("/api/audit", params={"job_id": jid}).json()
        ]
    assert container.jobs.recover_interrupted() == 0


def test_db_rows_survive_container_restart(settings, client, evidence):
    # A fresh container on the same data dir sees the same evidence (persistence, not in-memory state).
    from spectra.container import build_container

    c2 = build_container(settings, load_entry_points=False)
    try:
        with c2.session_factory() as s:
            assert (
                s.scalar(select(Evidence.sha256).where(Evidence.id == evidence["id"])) == evidence["sha256"]
            )
    finally:
        c2.close()


def test_unused_upload_helper_import():
    assert callable(upload)
