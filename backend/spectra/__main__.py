"""`python -m spectra` — run the local SPECTRA server."""

from __future__ import annotations

import uvicorn

from spectra.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "spectra.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
