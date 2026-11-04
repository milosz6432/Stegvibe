from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from spectra.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_session(c: Container = Depends(get_container)) -> Iterator[Session]:
    with c.session_factory() as session:
        yield session
