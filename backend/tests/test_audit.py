"""Acceptance 1.5: complete, ordered, tamper-evident audit trail."""

from __future__ import annotations

import threading

from sqlalchemy import delete, update

from spectra.core.audit import compute_entry_hash
from spectra.db.models import AuditEntry
from tests.conftest import run_job, upload, wait_for_job


def test_every_mutation_is_audited_in_order(client, case):
    cid = case["id"]
    ev = upload(client, cid, b"data", "a.bin").json()
    note = client.post(f"/api/cases/{cid}/notes", json={"body": "look here", "evidence_id": ev["id"]}).json()
    client.patch(f"/api/notes/{note['id']}", json={"body": "edited"})
    client.delete(f"/api/notes/{note['id']}")
    client.patch(f"/api/cases/{cid}", json={"description": "changed"})
    client.patch(f"/api/cases/{cid}", json={"archived": True})
    client.patch(f"/api/cases/{cid}", json={"archived": False})

    trail = client.get("/api/audit", params={"case_id": cid, "limit": 100}).json()
    actions = [e["action"] for e in reversed(trail)]  # API returns newest first
    assert actions == [
        "case.created",
        "evidence.imported",
        "note.created",
        "note.updated",
        "note.deleted",
        "case.updated",
        "case.archived",
        "case.unarchived",
    ]
    seqs = [e["seq"] for e in trail]
    assert seqs == sorted(seqs, reverse=True)
    assert client.get("/api/audit/verify").json()["valid"] is True


def test_job_lifecycle_is_audited(client, evidence):
    job = run_job(client, evidence["id"], "test.noop")
    wait_for_job(client, job["id"])
    actions = [e["action"] for e in reversed(client.get("/api/audit", params={"job_id": job["id"]}).json())]
    assert actions == ["job.created", "job.started", "job.succeeded"]
    created = client.get("/api/audit", params={"job_id": job["id"]}).json()[-1]
    assert created["details"]["plugin_id"] == "test.noop" and created["details"]["config"] == {}


def test_filters_and_pagination(client, case):
    for i in range(5):
        upload(client, case["id"], f"file{i}".encode(), f"f{i}.bin")
    page1 = client.get("/api/audit", params={"limit": 3}).json()
    page2 = client.get("/api/audit", params={"limit": 3, "before_seq": page1[-1]["seq"]}).json()
    assert len(page1) == 3 and page2 and page2[0]["seq"] < page1[-1]["seq"]
    only_imports = client.get("/api/audit", params={"action_prefix": "evidence."}).json()
    assert len(only_imports) == 5 and all(e["action"] == "evidence.imported" for e in only_imports)


def test_chain_links_and_verifies(client, container, case, evidence):
    v = client.get("/api/audit/verify").json()
    assert v["valid"] and v["entries_checked"] >= 3 and len(v["head_hash"]) == 64
    with container.session_factory() as s:
        rows = list(s.query(AuditEntry).order_by(AuditEntry.seq))
    for prev, cur in zip(rows, rows[1:], strict=False):
        assert cur.prev_hash == prev.entry_hash and cur.seq == prev.seq + 1


def test_editing_an_entry_is_detected(client, container, case, evidence):
    with container.session_factory() as s:
        s.execute(update(AuditEntry).where(AuditEntry.seq == 2).values(details_json='{"forged":true}'))
        s.commit()
    v = client.get("/api/audit/verify").json()
    assert v["valid"] is False and v["first_invalid_seq"] == 2
    assert "hash" in v["reason"]


def test_deleting_an_entry_is_detected(client, container, case, evidence):
    with container.session_factory() as s:
        s.execute(delete(AuditEntry).where(AuditEntry.seq == 2))
        s.commit()
    v = client.get("/api/audit/verify").json()
    assert v["valid"] is False and v["first_invalid_seq"] == 3 and "gap" in v["reason"]


def test_rehashing_one_entry_without_fixing_successors_is_detected(client, container, case, evidence):
    with container.session_factory() as s:
        row = s.get(AuditEntry, 2)
        row.details_json = '{"forged":true}'
        row.entry_hash = compute_entry_hash(
            row.prev_hash,
            row.seq,
            row.ts,
            row.actor,
            row.action,
            row.case_id,
            row.evidence_id,
            row.job_id,
            row.details_json,
        )
        s.commit()
    v = client.get("/api/audit/verify").json()
    assert v["valid"] is False and v["first_invalid_seq"] == 3 and "link" in v["reason"]


def test_concurrent_writers_keep_the_chain_intact(container):
    errors: list[Exception] = []

    def worker(n: int):
        try:
            for i in range(10):
                container.audit.record("test.concurrent", actor="test", details={"thread": n, "i": i})
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    v = container.audit.verify()
    assert v.valid, v.reason
    rows = container.audit.list(action_prefix="test.concurrent", limit=1000)
    assert len(rows) == 60 and len({r.seq for r in rows}) == 60
