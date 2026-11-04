"""Acceptance 1.7 (plugin registry) and 1.8 (dependency reporting)."""

from __future__ import annotations

import importlib.metadata
import subprocess

import pytest
from pydantic import ValidationError

from spectra.core.deps import KNOWN, DependencyChecker, DepSpec
from spectra.plugins.base import AnalysisPlugin, PluginMeta, PluginResult
from spectra.plugins.builtin import BUILTIN_PLUGINS
from spectra.plugins.registry import PluginRegistry
from tests.plugins_for_tests import NoopPlugin, PngOnlyPlugin, _meta

VALID = dict(
    id="vendor.thing",
    name="Thing",
    version="1.2.3",
    description="d",
    category="image",
    supported_formats=["png"],
    method="m",
    limitations=["l"],
)


# ---- metadata validation ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "override",
    [
        {"id": "NoDots"},
        {"id": "Vendor.Thing"},
        {"id": "vendor."},
        {"id": "1vendor.thing"},
        {"version": "1.2"},
        {"version": "latest"},
        {"supported_formats": []},
        {"supported_formats": ["pngg"]},
        {"supported_formats": ["audio:mp3"]},
        {"limitations": []},
        {"category": "magic"},
    ],
)
def test_invalid_metadata_is_rejected(override):
    with pytest.raises(ValidationError):
        PluginMeta(**{**VALID, **override})


@pytest.mark.parametrize("fmts", [["*"], ["png", "jpeg"], ["image:*"], ["audio:*", "wav"]])
def test_valid_format_tokens(fmts):
    assert PluginMeta(**{**VALID, "supported_formats": fmts}).supported_formats == fmts


def test_builtin_plugins_declare_everything_the_brief_requires():
    for cls in BUILTIN_PLUGINS:
        m = cls.meta
        assert m.id and m.name and m.version and m.description and m.method
        assert m.supported_formats and m.limitations, f"{m.id} must document limitations"
        assert cls.config_schema()["type"] == "object"


# ---- registry ----------------------------------------------------------------------------------------
@pytest.fixture
def registry():
    return PluginRegistry(DependencyChecker())


def test_register_rejects_bad_plugins(registry):
    registry.register(NoopPlugin)
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(NoopPlugin)
    with pytest.raises(TypeError):
        registry.register(dict)  # type: ignore[arg-type]

    class NoMeta(AnalysisPlugin):
        def run(self, ctx, config):
            return PluginResult()

    with pytest.raises(TypeError, match="PluginMeta"):
        registry.register(NoMeta)

    class Local(AnalysisPlugin):  # defined in a function: a worker process could never import it
        meta = _meta("test.local")

        def run(self, ctx, config):
            return PluginResult()

    with pytest.raises(ValueError, match="module level"):
        registry.register(Local)


def test_registry_records_the_import_path_used_by_workers(registry):
    entry = registry.register(NoopPlugin)
    assert entry.entrypoint == "tests.plugins_for_tests:NoopPlugin"


def test_format_filtering(registry):
    registry.register(NoopPlugin)
    registry.register(PngOnlyPlugin)
    ids = lambda fmt: {p.id for p in registry.list_info(fmt)}  # noqa: E731
    assert ids(None) == {"test.noop", "test.png_only"}
    assert ids("png") == {"test.noop", "test.png_only"}
    assert ids("wav") == {"test.noop"}


def test_availability_reports_missing_required_but_not_optional_dependencies(client):
    plugins = {p["id"]: p for p in client.get("/api/plugins").json()}
    missing = plugins["test.missing_dep"]
    assert missing["available"] is False and "spectra-no-such-binary-xyz" in missing["unavailable_reason"]
    assert missing["dependencies"][0]["status"]["available"] is False
    assert plugins["test.optional_dep"]["available"] is True


def test_api_exposes_schemas_and_limitations(client):
    p = client.get("/api/plugins/core.integrity_verify").json()
    assert p["deterministic"] is True and p["limitations"] and p["method"]
    assert p["config_schema"]["properties"]["chunk_size_kib"]["minimum"] == 4
    assert "match" in p["summary_schema"]["properties"]
    assert client.get("/api/plugins/nope.nope").status_code == 404
    only_png = {x["id"] for x in client.get("/api/plugins", params={"format": "png"}).json()}
    assert "test.png_only" in only_png
    assert "test.png_only" not in {
        x["id"] for x in client.get("/api/plugins", params={"format": "wav"}).json()
    }


class _EP:
    def __init__(self, name, loader):
        self.name, self._loader = name, loader

    def load(self):
        return self._loader()


def test_entry_point_plugins_load_and_failures_are_isolated(monkeypatch, registry):
    def broken():
        raise ImportError("third-party plugin is broken")

    eps = [_EP("good", lambda: PngOnlyPlugin), _EP("broken", broken), _EP("notaplugin", lambda: dict)]
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda group=None: eps)
    registry.load_entry_points()  # must not raise
    assert registry.get("test.png_only").source == "entry_point:good"
    assert {e["entry_point"] for e in registry.load_errors} == {"broken", "notaplugin"}
    assert any("broken" in e["error"] for e in registry.load_errors)


# ---- dependencies -----------------------------------------------------------------------------------
def test_every_known_dependency_is_checked_without_raising():
    items = DependencyChecker().check_all()
    assert {i.name for i in items} == {s.name for s in KNOWN}
    for i in items:
        assert isinstance(i.available, bool)
        if not i.available:
            assert i.error, f"{i.name}: unavailable dependencies must say why"


def test_core_dependencies_are_available_and_versioned():
    by_name = {i.name: i for i in DependencyChecker().check_all()}
    for name in ("fastapi", "sqlalchemy", "pydantic", "python-magic"):
        assert by_name[name].available and by_name[name].required
    assert by_name["fastapi"].version
    assert by_name["python-magic"].verified_by_import is True  # libmagic must really load


def test_missing_binary_and_module_are_reported_truthfully():
    chk = DependencyChecker()
    b = chk.check_spec(
        DepSpec("ghost", "binary", binary="spectra-no-such-binary-xyz", install_hint="apt install ghost")
    )
    assert b.available is False and "not found on PATH" in b.error and b.install_hint == "apt install ghost"
    m = chk.check_spec(DepSpec("ghostmod", "python", module="spectra_no_such_module", dists=("x",)))
    assert m.available is False and "not installed" in m.error


def test_present_python_module_reports_version():
    s = DependencyChecker().check_spec(DepSpec("pytest", "python", module="pytest", dists=("pytest",)))
    assert s.available and s.version


def test_binary_version_is_parsed(tmp_path, monkeypatch):
    exe = tmp_path / "fakebin"
    exe.write_text("#!/bin/sh\necho 'fakebin 9.8.7 (test)'\n")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    s = DependencyChecker().check_spec(DepSpec("fakebin", "binary", binary="fakebin"))
    assert s.available and s.version == "fakebin 9.8.7 (test)" and s.location == str(exe)


def test_binary_that_cannot_run_is_unavailable(tmp_path, monkeypatch):
    exe = tmp_path / "brokenbin"
    exe.write_text("not executable content\n")
    exe.chmod(0o755)  # executable bit set, but the interpreter line is missing/invalid
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    s = DependencyChecker().check_spec(DepSpec("brokenbin", "binary", binary="brokenbin"))
    assert s.available is False and "could not run" in s.error


def test_deep_check_surfaces_import_failures(monkeypatch):
    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(
            cmd, 1, stdout="", stderr="Traceback...\nImportError: libfoo.so: cannot open"
        )

    monkeypatch.setattr("spectra.core.deps.subprocess.run", fake_run)
    s = DependencyChecker().check_spec(
        DepSpec("pytest", "python", module="pytest", dists=("pytest",)), deep=True
    )
    assert s.available is False and "fails to import" in s.error and "libfoo" in s.error


def test_check_named_handles_unknown_and_mismatched_kinds():
    chk = DependencyChecker()
    assert chk.check_named("spectra-no-such-binary-xyz", "binary").available is False
    assert chk.check_named("json", "python").available is True  # unknown to the catalogue: generic check
    mismatch = chk.check_named("ffmpeg", "python")
    assert mismatch.available is False and "binary" in mismatch.error


def test_dependencies_endpoint(client):
    body = client.get("/api/system/dependencies").json()
    names = {i["name"] for i in body["items"]}
    assert {"ffmpeg", "exiftool", "binwalk", "numpy", "librosa"} <= names
    assert body["summary"]["total"] == len(body["items"])
    assert body["summary"]["missing_required"] == []
    deep = client.get("/api/system/dependencies", params={"deep": True}).json()
    assert deep["deep"] is True
