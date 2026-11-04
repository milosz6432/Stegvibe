"""Plugin discovery, validation and availability."""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
from dataclasses import dataclass

from spectra.core.deps import DependencyChecker
from spectra.core.errors import NotFoundError
from spectra.formats import token_matches
from spectra.plugins.base import AnalysisPlugin, PluginMeta
from spectra.schemas.plugins import PluginDependencyInfo, PluginInfo

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "spectra.plugins"


@dataclass(frozen=True)
class PluginEntry:
    cls: type[AnalysisPlugin]
    entrypoint: str  # "module:QualName", what the worker subprocess imports
    source: str  # "builtin" | "entry_point:<name>" | "registered"

    @property
    def meta(self) -> PluginMeta:
        return self.cls.meta


class PluginRegistry:
    def __init__(self, deps: DependencyChecker):
        self._deps = deps
        self._entries: dict[str, PluginEntry] = {}
        self.load_errors: list[dict[str, str]] = []

    # ---- registration --------------------------------------------------
    def register(self, cls: type[AnalysisPlugin], *, source: str = "registered") -> PluginEntry:
        if not (isinstance(cls, type) and issubclass(cls, AnalysisPlugin)):
            raise TypeError(f"{cls!r} is not an AnalysisPlugin subclass")
        meta = getattr(cls, "meta", None)
        if not isinstance(meta, PluginMeta):
            raise TypeError(f"{cls.__qualname__} must define a PluginMeta in 'meta'")
        if "<locals>" in cls.__qualname__:
            raise ValueError("plugins must be defined at module level so worker processes can import them")
        if meta.id in self._entries:
            raise ValueError(f"duplicate plugin id: {meta.id}")
        entry = PluginEntry(cls=cls, entrypoint=f"{cls.__module__}:{cls.__qualname__}", source=source)
        self._entries[meta.id] = entry
        return entry

    def load_builtin(self) -> None:
        from spectra.plugins.builtin import BUILTIN_PLUGINS

        for cls in BUILTIN_PLUGINS:
            self.register(cls, source="builtin")

    def load_entry_points(self) -> None:
        for ep in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP):
            try:
                cls = ep.load()
                self.register(cls, source=f"entry_point:{ep.name}")
            except Exception as exc:  # a broken third-party plugin must not take the app down
                log.warning("failed to load plugin entry point %s: %s", ep.name, exc)
                self.load_errors.append({"entry_point": ep.name, "error": f"{type(exc).__name__}: {exc}"})

    # ---- queries -------------------------------------------------------
    def get(self, plugin_id: str) -> PluginEntry:
        try:
            return self._entries[plugin_id]
        except KeyError:
            raise NotFoundError(f"Unknown plugin '{plugin_id}'.", code="plugin_not_found") from None

    def __len__(self) -> int:
        return len(self._entries)

    def supports_format(self, entry: PluginEntry, fmt: str | None) -> bool:
        return any(token_matches(t, fmt) for t in entry.meta.supported_formats)

    def availability(self, entry: PluginEntry) -> tuple[bool, str | None, list[PluginDependencyInfo]]:
        infos: list[PluginDependencyInfo] = []
        missing: list[str] = []
        for dep in entry.meta.dependencies:
            status = self._deps.check_named(dep.name, dep.kind)
            infos.append(
                PluginDependencyInfo(
                    name=dep.name, kind=dep.kind, optional=dep.optional, purpose=dep.purpose, status=status
                )
            )
            if not status.available and not dep.optional:
                missing.append(dep.name)
        reason = f"missing required dependencies: {', '.join(missing)}" if missing else None
        return (not missing, reason, infos)

    def info(self, entry: PluginEntry) -> PluginInfo:
        available, reason, dep_infos = self.availability(entry)
        m = entry.meta
        return PluginInfo(
            id=m.id,
            name=m.name,
            version=m.version,
            description=m.description,
            category=m.category,
            supported_formats=list(m.supported_formats),
            dependencies=dep_infos,
            method=m.method,
            limitations=list(m.limitations),
            deterministic=m.deterministic,
            cpu_heavy=m.cpu_heavy,
            available=available,
            unavailable_reason=reason,
            source=entry.source,
            config_schema=entry.cls.config_schema(),
            summary_schema=entry.cls.summary_schema(),
        )

    def list_info(self, fmt: str | None = None) -> list[PluginInfo]:
        entries = sorted(self._entries.values(), key=lambda e: e.meta.id)
        if fmt:
            entries = [e for e in entries if self.supports_format(e, fmt)]
        return [self.info(e) for e in entries]
