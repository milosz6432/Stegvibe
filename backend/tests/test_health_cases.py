"""Acceptance 1.1 (startup/health) and 1.2 (case lifecycle)."""

from __future__ import annotations

from sqlalchemy import select

from spectra.container import build_container
from spectra.db.models import AuditEntry
from tests.conftest import upload


def test_startup_creates_storage_and_reports_health(client, settings):
    assert settings.db_path.is_file()
    assert settings.tmp_dir.is_dir() and settings.cases_dir.is_dir()
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["database"]["ok"] and body["storage"]["writable"]
    assert body["database"]["schema_version"] == 1


def test_startup_is_audited_and_restart_is_safe(settings):
    c1 = build_container(settings, load_entry_points=False)
    c1.close()
    c2 = build_container(settings, load_entry_points=False)  # reopening an existing database must work
    with c2.session_factory() as s:
        actions = [a for a in s.execute(select(AuditEntry.action)).scalars()]
    c2.close()
    assert actions.count("system.started") == 2


def test_system_info_is_honest_about_isolation(client):
    info = client.get("/api/system/info").json()
    assert info["offline"] is True
    assert info["isolation"]["worker_subprocess"] is True
    assert "limits" in info and info["plugins"] >= 1


def test_case_crud_and_counts(client):
    r = client.post("/api/cases", json={"name": "  Alpha  ", "description": "d"})
    assert r.status_code == 201
    case = r.json()
    assert case["name"] == "Alpha"  # trimmed
    assert case["evidence_count"] == 0

    assert client.get(f"/api/cases/{case['id']}").json()["name"] == "Alpha"
    assert [c["id"] for c in client.get("/api/cases").json()] == [case["id"]]

    upload(client, case["id"], b"x" * 100, "a.bin")
    upload(client, case["id"], b"y" * 50, "b.bin")
    got = client.get(f"/api/cases/{case['id']}").json()
    assert got["evidence_count"] == 2 and got["total_bytes"] == 150

    r = client.patch(f"/api/cases/{case['id']}", json={"name": "Beta", "description": "new"})
    assert r.status_code == 200 and r.json()["name"] == "Beta"


def test_blank_and_missing_inputs_are_rejected(client):
    assert client.post("/api/cases", json={"name": "   "}).status_code == 422
    assert client.post("/api/cases", json={}).status_code == 422
    r = client.get("/api/cases/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "case_not_found"


def test_archive_hides_case_and_makes_it_read_only(client, case):
    cid = case["id"]
    assert client.patch(f"/api/cases/{cid}", json={"archived": True}).json()["archived"] is True
    assert client.get("/api/cases").json() == []
    assert [c["id"] for c in client.get("/api/cases", params={"include_archived": True}).json()] == [cid]

    r = upload(client, cid, b"data", "x.bin")
    assert r.status_code == 409 and r.json()["error"]["code"] == "case_archived"
    assert client.post(f"/api/cases/{cid}/notes", json={"body": "hi"}).status_code == 409

    assert client.patch(f"/api/cases/{cid}", json={"archived": False}).json()["archived"] is False
    assert upload(client, cid, b"data", "x.bin").status_code == 201


def test_purge_requires_exact_name_and_keeps_audit_trail(client, case, settings):
    cid = case["id"]
    ev = upload(client, cid, b"secret evidence", "e.bin").json()
    original = settings.cases_dir / cid / "originals" / ev["id"]
    assert original.is_file()

    bad = client.post(f"/api/cases/{cid}/purge", json={"confirm_name": "wrong"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "confirmation_mismatch"
    assert original.is_file()

    ok = client.post(f"/api/cases/{cid}/purge", json={"confirm_name": case["name"]})
    assert ok.status_code == 204
    assert not (settings.cases_dir / cid).exists()
    assert client.get(f"/api/cases/{cid}").status_code == 404
    assert client.get(f"/api/evidence/{ev['id']}").status_code == 404

    trail = client.get("/api/audit", params={"case_id": cid, "limit": 100}).json()
    actions = [e["action"] for e in trail]
    assert "case.purged" in actions and "evidence.imported" in actions
    purged = next(e for e in trail if e["action"] == "case.purged")
    assert purged["details"]["evidence"][0]["sha256"] == ev["sha256"]  # what was destroyed stays on record
    assert client.get("/api/audit/verify").json()["valid"] is True


def test_stats(client, case, evidence):
    st = client.get("/api/stats").json()
    assert st["cases"] == 1 and st["evidence"] == 1 and st["evidence_bytes"] == evidence["size_bytes"]
    assert st["audit_entries"] >= 3
