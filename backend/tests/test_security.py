"""Acceptance 1.9: request hardening, filename/path safety, no network client code."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import spectra
from spectra.api.middleware import _host_without_port
from spectra.core.errors import ForbiddenError
from spectra.core.security import declared_extension, resolve_within, sanitize_filename
from spectra.main import create_app
from tests.conftest import upload


# ---- pure helpers -----------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("normal.png", "normal.png"),
        ("../../x.bin", "x.bin"),
        ("..\\..\\x.bin", "x.bin"),
        ("a/b/c.txt", "c.txt"),
        ("", "unnamed"),
        (None, "unnamed"),
        (".", "unnamed"),
        ("  spaced.png  ", "spaced.png"),
        ("nul\x00byte.png", "nulbyte.png"),
        ("a‮b.png", "ab.png"),
        ("tab\tname.png", "tabname.png"),
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_truncates_but_keeps_extension():
    out = sanitize_filename("a" * 400 + ".png")
    assert len(out) <= 255 and out.endswith(".png")


@pytest.mark.parametrize(
    "name,ext", [("a.PNG", "png"), ("a.tar.gz", "gz"), ("noext", None), ("a.", None), ("a.b c", None)]
)
def test_declared_extension(name, ext):
    assert declared_extension(name) == ext


def test_resolve_within_blocks_escapes(tmp_path):
    assert resolve_within(tmp_path, "a", "b") == (tmp_path / "a" / "b").resolve()
    with pytest.raises(ForbiddenError):
        resolve_within(tmp_path, "..", "etc")
    with pytest.raises(ForbiddenError):
        resolve_within(tmp_path, "/etc/passwd")
    (tmp_path / "link").symlink_to("/etc")
    with pytest.raises(ForbiddenError):
        resolve_within(tmp_path, "link", "passwd")


@pytest.mark.parametrize(
    "header,host",
    [
        ("localhost:8000", "localhost"),
        ("127.0.0.1", "127.0.0.1"),
        ("[::1]:8000", "[::1]"),
        ("[::1]", "[::1]"),
        ("EXAMPLE.com:1", "example.com"),
    ],
)
def test_host_parsing(header, host):
    assert _host_without_port(header) == host


# ---- HTTP hardening -----------------------------------------------------------
def test_foreign_host_header_is_rejected(client):
    r = client.get("/api/health", headers={"Host": "evil.example"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "host_not_allowed"


def test_foreign_origin_cannot_change_state(client):
    for origin in ("http://evil.example", "null", "http://testserver.evil.example"):
        r = client.post("/api/cases", json={"name": "csrf"}, headers={"Origin": origin})
        assert r.status_code == 403, origin
        assert r.json()["error"]["code"] == "origin_not_allowed"
    assert client.get("/api/cases").json() == []


def test_foreign_origin_cannot_upload_evidence(client, case):
    r = client.post(
        f"/api/cases/{case['id']}/evidence",
        params={"filename": "x.bin"},
        content=b"abc",
        headers={"Origin": "http://evil.example"},
    )
    assert r.status_code == 403
    assert client.get(f"/api/cases/{case['id']}/evidence").json() == []


def test_same_origin_and_allow_listed_origins_work(client):
    assert (
        client.post("/api/cases", json={"name": "same"}, headers={"Origin": "http://testserver"}).status_code
        == 201
    )
    assert (
        client.post(
            "/api/cases", json={"name": "dev"}, headers={"Origin": "http://localhost:5173"}
        ).status_code
        == 201
    )
    # reads are never blocked by Origin (CORS already stops foreign pages from reading the response)
    assert client.get("/api/cases", headers={"Origin": "http://evil.example"}).status_code == 200


def test_security_headers_present(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "script-src 'self'" in csp
    rej = client.get("/api/health", headers={"Host": "evil.example"})
    assert rej.headers["x-content-type-options"] == "nosniff"  # rejections are hardened too


def test_swagger_ui_with_cdn_assets_is_disabled_but_schema_is_available(client):
    assert client.get("/docs").status_code == 404
    spec = client.get("/api/openapi.json").json()
    assert "/api/cases/{case_id}/evidence" in spec["paths"]


def test_validation_errors_use_the_error_envelope(client):
    r = client.post("/api/cases", json={"name": 5})
    body = r.json()
    assert r.status_code == 422 and body["error"]["code"] == "validation_error"
    assert body["error"]["details"][0]["loc"]


# ---- frontend hosting -----------------------------------------------------------
@pytest.fixture
def spa_client(settings, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>SPECTRA-SPA</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    settings.serve_frontend = True
    settings.frontend_dist = dist
    with TestClient(create_app(settings)) as tc:
        yield tc


def test_default_frontend_location_is_the_repo_frontend_directory():
    from spectra.config import default_frontend_dist

    dist = default_frontend_dist()
    assert dist.name == "dist" and (dist.parent / "package.json").is_file(), dist


def test_spa_fallback_serves_index_for_client_routes(spa_client):
    assert "SPECTRA-SPA" in spa_client.get("/").text
    assert "SPECTRA-SPA" in spa_client.get("/investigations/abc").text
    assert spa_client.get("/assets/app.js").text == "console.log(1)"


def test_spa_cannot_be_used_to_read_arbitrary_files(spa_client):
    for path in (
        "/..%2F..%2F..%2Fetc%2Fpasswd",
        "/%2e%2e/%2e%2e/etc/passwd",
        "/assets/..%2f..%2f..%2fetc%2fpasswd",
    ):
        r = spa_client.get(path)
        assert "root:" not in r.text, path


def test_unknown_api_paths_stay_json_404_even_with_spa(spa_client):
    r = spa_client.get("/api/nonexistent")
    assert r.status_code == 404 and r.json()["error"]["code"] == "endpoint_not_found"


# ---- offline guarantee ------------------------------------------------------------
FORBIDDEN_MODULES = {
    "socket",
    "ssl",
    "urllib.request",
    "http.client",
    "ftplib",
    "smtplib",
    "telnetlib",
    "imaplib",
    "poplib",
    "xmlrpc.client",
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "websocket",
}


def test_backend_contains_no_network_client_code():
    root = Path(spectra.__file__).parent
    offenders = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            for n in names:
                if n in FORBIDDEN_MODULES or n.split(".")[0] in {
                    "requests",
                    "httpx",
                    "aiohttp",
                    "urllib3",
                    "socket",
                    "ssl",
                }:
                    offenders.append(f"{path.relative_to(root)}: {n}")
    assert not offenders, offenders


def test_evidence_upload_unaffected_by_helper(client, case):
    # sanity check that the helper used across modules behaves
    assert upload(client, case["id"], b"ok", "ok.bin").status_code == 201


def test_plugin_sdk_and_worker_import_no_web_framework():
    """Analysis workers must stay light and away from HTTP code: the SDK may not pull in the web stack."""
    code = (
        "import sys, spectra.plugins.base, spectra.jobs.worker\n"
        "web = {'fastapi', 'starlette', 'uvicorn', 'sqlalchemy'}\n"
        "bad = sorted({m.split('.')[0] for m in sys.modules} & web)\n"
        "print(','.join(bad))\n"
    )
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", f"worker/SDK import chain loads: {out.stdout.strip()}"


def test_only_the_http_layer_imports_the_web_framework():
    """Layering rule from docs/ARCHITECTURE.md: domain code never depends on FastAPI/Starlette."""
    root = Path(spectra.__file__).parent
    allowed = {root / "main.py"}
    offenders = []
    for path in root.rglob("*.py"):
        if path in allowed or (root / "api") in path.parents:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            offenders += [
                f"{path.relative_to(root)}: {n}" for n in names if n.split(".")[0] in {"fastapi", "starlette"}
            ]
    assert offenders == []
