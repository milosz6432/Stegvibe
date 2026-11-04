"""Acceptance 1.3 and 1.4: streamed ingest, hashes, immutability, safe naming, downloads, hex view."""

from __future__ import annotations

import hashlib
import io
import random
import stat

from PIL import Image

from tests.conftest import upload


def _stored(settings, case_id, evidence_id):
    return settings.cases_dir / case_id / "originals" / evidence_id


def test_hashes_equal_independent_computation_and_bytes_are_identical(client, case, settings):
    data = random.Random(7).randbytes(5 * 1024 * 1024 + 123)  # several upload buffers, odd tail
    r = upload(client, case["id"], data, "big.bin")
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["size_bytes"] == len(data)
    assert ev["md5"] == hashlib.md5(data).hexdigest()
    assert ev["sha1"] == hashlib.sha1(data).hexdigest()
    assert ev["sha256"] == hashlib.sha256(data).hexdigest()
    stored = _stored(settings, case["id"], ev["id"])
    assert stored.read_bytes() == data
    assert list(settings.tmp_dir.iterdir()) == []  # staging area is clean


def test_original_is_stored_read_only_under_its_id_not_the_user_filename(client, case, settings):
    ev = upload(client, case["id"], b"payload", "evil name.png").json()
    stored = _stored(settings, case["id"], ev["id"])
    assert stat.S_IMODE(stored.stat().st_mode) == 0o444
    names = [p.name for p in (settings.cases_dir / case["id"] / "originals").iterdir()]
    assert names == [ev["id"]]


def test_oversize_chunked_upload_is_rejected_and_leaves_no_residue(client, case, settings):
    settings.max_upload_bytes = 1000

    def body():  # generator => chunked transfer encoding, no Content-Length
        for _ in range(10):
            yield b"a" * 300

    r = client.post(f"/api/cases/{case['id']}/evidence", params={"filename": "big.bin"}, content=body())
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"
    assert list(settings.tmp_dir.iterdir()) == []
    assert list((settings.cases_dir / case["id"] / "originals").iterdir()) == []
    assert client.get(f"/api/cases/{case['id']}/evidence").json() == []


def test_oversize_declared_length_is_rejected_up_front(client, case, settings):
    settings.max_upload_bytes = 1000
    r = upload(client, case["id"], b"z" * 2000, "big.bin")
    assert r.status_code == 413
    assert list(settings.tmp_dir.iterdir()) == []


def test_empty_upload_is_rejected(client, case, settings):
    r = upload(client, case["id"], b"", "empty.bin")
    assert r.status_code == 422 and r.json()["error"]["code"] == "empty_file"
    assert list(settings.tmp_dir.iterdir()) == []


def test_upload_to_unknown_case_is_404(client):
    assert upload(client, "does-not-exist", b"abc", "a.bin").status_code == 404


def test_hostile_filenames_are_neutralised(client, case, settings):
    cases = {
        "../../etc/passwd": "passwd",
        "C:\\evil\\payload.exe": "payload.exe",
        "invoice\u202egnp.exe": "invoicegnp.exe",  # RTL override stripped
        "ctrl\x01char.bin": "ctrlchar.bin",
        "..": "unnamed",
    }
    for raw, expected in cases.items():
        ev = upload(client, case["id"], raw.encode("utf-8", "ignore") + b"!", raw).json()
        assert ev["original_filename"] == expected, raw
    assert not (settings.data_dir.parent / "passwd").exists()
    trail = client.get(
        "/api/audit", params={"case_id": case["id"], "action_prefix": "evidence.imported"}
    ).json()
    assert any(e["details"]["raw_filename"] == "../../etc/passwd" for e in trail)  # the raw name is on record


def test_declared_extension_and_mime_hint(client, case):
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(buf, "PNG")
    ev = upload(client, case["id"], buf.getvalue(), "Photo.PNG").json()
    assert ev["declared_extension"] == "png"
    assert ev["mime_hint"] == "image/png"
    assert ev["detected_format"] is None  # identification is Phase 2: nothing is claimed yet
    assert upload(client, case["id"], b"abc", "noext").json()["declared_extension"] is None


def test_duplicates_are_flagged_not_blocked(client, case):
    first = upload(client, case["id"], b"same bytes", "one.bin").json()
    second = upload(client, case["id"], b"same bytes", "two.bin")
    assert second.status_code == 201
    assert second.json()["duplicate_of"] == [first["id"]]
    listing = {e["id"]: e for e in client.get(f"/api/cases/{case['id']}/evidence").json()}
    assert listing[first["id"]]["duplicate_of"] == [second.json()["id"]]


def test_download_returns_exact_bytes_as_a_non_renderable_attachment(client, case):
    html = b"<html><script>alert(1)</script></html>"
    ev = upload(client, case["id"], html, "page.html").json()
    r = client.get(f"/api/evidence/{ev['id']}/download")
    assert r.status_code == 200 and r.content == html
    assert r.headers["content-type"].startswith("application/octet-stream")
    assert r.headers["content-disposition"].startswith("attachment")
    assert r.headers["x-content-type-options"] == "nosniff"
    actions = [e["action"] for e in client.get("/api/audit", params={"evidence_id": ev["id"]}).json()]
    assert "evidence.downloaded" in actions  # reads of raw evidence are logged


def test_hex_view(client, case):
    data = bytes(range(64)) + b"Hello, SPECTRA!"
    ev = upload(client, case["id"], data, "h.bin").json()
    v = client.get(f"/api/evidence/{ev['id']}/hex", params={"offset": 0, "length": 32}).json()
    assert v["total_size"] == len(data) and v["length"] == 32 and len(v["rows"]) == 2
    assert v["rows"][0]["hex"].startswith("00 01 02 03")
    assert v["rows"][0]["ascii"] == "." * 16
    tail = client.get(f"/api/evidence/{ev['id']}/hex", params={"offset": 64, "length": 64}).json()
    assert tail["length"] == 15 and tail["rows"][0]["ascii"] == "Hello, SPECTRA!"
    assert tail["rows"][0]["offset"] == 64


def test_hex_view_limits(client, case, settings):
    settings.max_hex_read_bytes = 128
    ev = upload(client, case["id"], b"A" * 1000, "a.bin").json()
    v = client.get(f"/api/evidence/{ev['id']}/hex", params={"offset": 0, "length": 100000}).json()
    assert v["length"] == 128  # clamped by the server
    assert client.get(f"/api/evidence/{ev['id']}/hex", params={"offset": 5000}).status_code == 422
    assert client.get(f"/api/evidence/{ev['id']}/hex", params={"offset": -1}).status_code == 422
    assert client.get("/api/evidence/unknown/hex").status_code == 404


def test_missing_file_on_disk_is_reported_not_crashed(client, case, settings):
    ev = upload(client, case["id"], b"data", "gone.bin").json()
    _stored(settings, case["id"], ev["id"]).unlink()
    r = client.get(f"/api/evidence/{ev['id']}/download")
    assert r.status_code == 404 and r.json()["error"]["code"] == "evidence_file_missing"
