"""Code shown in docs/PLUGINS.md must run. The snippet is extracted from the markdown, not copied here."""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest

from tests.conftest import run_job, upload, wait_for_job

DOC = Path(__file__).resolve().parents[2] / "docs" / "PLUGINS.md"


def _python_block_after(heading: str) -> str:
    text = DOC.read_text(encoding="utf-8")
    start = text.index(heading)
    m = re.search(r"```python\n(.*?)```", text[start:], re.S)
    assert m, f"no python block after {heading!r}"
    return m.group(1)


@pytest.fixture
def doc_plugin(tmp_path, container, client):
    module = "doc_minimal_plugin"
    (tmp_path / f"{module}.py").write_text(_python_block_after("## 3. A minimal plugin"), encoding="utf-8")
    sys.path.insert(0, str(tmp_path))  # spawned workers inherit sys.path
    try:
        mod = importlib.import_module(module)
        container.registry.register(mod.NullRuns, source="doc")
        yield client
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop(module, None)


def test_minimal_plugin_from_the_docs_runs_and_reports_the_run(doc_plugin, case):
    data = (
        b"A" * 10 + b"\x00" * 100 + b"B" * 10 + b"\x00" * 5 + b"C" * 3 + b"\x00" * 70
    )  # 100, 5 (too short), 70
    ev = upload(doc_plugin, case["id"], data, "nul.bin").json()
    job = wait_for_job(doc_plugin, run_job(doc_plugin, ev["id"], "acme.null_runs")["id"])

    assert job["status"] == "succeeded", job
    assert job["result"]["summary"] == {"runs": 2}
    items = doc_plugin.get("/api/findings", params={"job_id": job["id"]}).json()["items"]
    assert sorted((f["location"]["byte_offset"], f["location"]["length"]) for f in items) == [
        (10, 100),
        (128, 70),
    ]
    assert {f["confidence"] for f in items} == {"low"}  # a structural hint is not presented as proof


def test_minimal_plugin_config_bounds_from_the_docs_are_enforced(doc_plugin, evidence):
    r = doc_plugin.post(
        "/api/jobs",
        json={"evidence_id": evidence["id"], "plugin_id": "acme.null_runs", "config": {"min_run": 1}},
    )
    assert r.status_code == 422
