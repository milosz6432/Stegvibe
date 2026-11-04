"""Child-process entry point for analysis jobs.

Runs in a *spawned* interpreter (no inherited DB handles, threads or open evidence files). The module
imports nothing heavy at top level so that resource limits can be applied before plugin code is loaded.

Protocol (child → parent over a one-way pipe), each message a tuple:
    ("progress", fraction, message)
    ("result",   PluginResult-as-dict)
    ("error",    {"code": str, "message": str, "traceback": str})
"""

from __future__ import annotations

import importlib
import os
import time
import traceback
from pathlib import Path
from typing import Any


def load_entrypoint(entrypoint: str) -> Any:
    module_name, _, qualname = entrypoint.partition(":")
    obj: Any = importlib.import_module(module_name)
    for part in qualname.split("."):
        obj = getattr(obj, part)
    return obj


def apply_limits(memory_limit_mb: int, cpu_seconds: int) -> None:
    """POSIX resource caps. Silently unavailable elsewhere (documented limitation)."""
    try:
        import resource
    except ImportError:  # Windows
        return
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))  # never write core dumps containing evidence
    except (ValueError, OSError):
        pass
    if memory_limit_mb > 0:
        limit = memory_limit_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        except (ValueError, OSError):
            pass
    if cpu_seconds > 0:
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 5))
        except (ValueError, OSError):
            pass


def _send_error(conn, code: str, message: str, tb: str = "") -> None:
    try:
        conn.send(("error", {"code": code, "message": message[:2000], "traceback": tb[-4000:]}))
    except Exception:
        pass


def worker_main(spec: dict, conn) -> None:
    if hasattr(os, "setpgrp"):  # own process group so the supervisor can kill helper binaries too
        try:
            os.setpgrp()
        except OSError:
            pass

    last_sent = 0.0

    def report(fraction: float, message: str) -> None:
        nonlocal last_sent
        now = time.monotonic()
        if fraction >= 1.0 or now - last_sent >= 0.1:
            last_sent = now
            try:
                conn.send(("progress", float(fraction), str(message)[:500]))
            except Exception:
                pass

    try:
        apply_limits(int(spec.get("memory_limit_mb", 0)), int(spec.get("cpu_seconds", 0)))
        from spectra.plugins.base import EvidenceRef, PluginContext, PluginResult

        cls = load_entrypoint(spec["entrypoint"])
        config = cls.ConfigModel.model_validate(spec["config"])
        evidence = EvidenceRef.model_validate(spec["evidence"])
        ctx = PluginContext(evidence, Path(spec["output_dir"]), report)
        result = cls().run(ctx, config)
        if not isinstance(result, PluginResult):
            raise TypeError(f"plugin returned {type(result).__name__}, expected PluginResult")
        if cls.SummaryModel is not None:
            result.summary = cls.SummaryModel.model_validate(result.summary).model_dump(mode="json")
        conn.send(("result", result.model_dump(mode="json")))
    except MemoryError:
        _send_error(conn, "memory", "The analysis exceeded its memory limit.")
    except BaseException as exc:  # noqa: BLE001 - report everything to the supervisor
        _send_error(conn, "plugin_error", f"{type(exc).__name__}: {exc}", traceback.format_exc())
    finally:
        try:
            conn.close()
        except Exception:
            pass
