from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from spectra.core.deps import DependencyStatus


class PluginDependencyInfo(BaseModel):
    name: str
    kind: str
    optional: bool
    purpose: str
    status: DependencyStatus


class PluginInfo(BaseModel):
    id: str
    name: str
    version: str
    description: str
    category: str
    supported_formats: list[str]
    dependencies: list[PluginDependencyInfo]
    method: str
    limitations: list[str]
    deterministic: bool
    cpu_heavy: bool
    available: bool
    unavailable_reason: str | None = None
    source: str
    config_schema: dict[str, Any]
    summary_schema: dict[str, Any] | None = None
