"""Composition root: builds every long-lived service from a Settings object."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from spectra import __version__
from spectra.config import Settings
from spectra.core.audit import AuditService
from spectra.core.deps import DependencyChecker
from spectra.core.evidence_store import EvidenceStore
from spectra.db.base import make_engine, make_session_factory
from spectra.db.models import init_db
from spectra.jobs.manager import JobManager
from spectra.plugins.registry import PluginRegistry

log = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    audit: AuditService
    store: EvidenceStore
    deps: DependencyChecker
    registry: PluginRegistry
    jobs: JobManager

    def close(self) -> None:
        self.jobs.shutdown()
        self.engine.dispose()


def build_container(settings: Settings, *, load_entry_points: bool = True) -> Container:
    settings.ensure_dirs()
    engine = make_engine(settings.db_path)
    init_db(engine)
    sf = make_session_factory(engine)
    audit = AuditService(sf)
    store = EvidenceStore(settings)
    deps = DependencyChecker()
    registry = PluginRegistry(deps)
    registry.load_builtin()
    if load_entry_points:
        registry.load_entry_points()
    jobs = JobManager(settings, sf, registry, store, audit)

    recovered = jobs.recover_interrupted()
    removed_tmp = store.cleanup_stale_tmp()
    audit.record(
        "system.started",
        actor="system",
        details={
            "version": __version__,
            "plugins": len(registry),
            "recovered_jobs": recovered,
            "stale_tmp_removed": removed_tmp,
        },
    )
    log.info("SPECTRA %s ready (data dir: %s, %d plugins)", __version__, settings.data_dir, len(registry))
    return Container(settings, engine, sf, audit, store, deps, registry, jobs)
