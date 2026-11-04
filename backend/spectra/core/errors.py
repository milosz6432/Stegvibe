"""Domain exceptions. The API layer maps these to a uniform ``{"error": {...}}`` JSON envelope."""

from __future__ import annotations

from typing import Any


class SpectraError(Exception):
    status_code = 400
    code = "error"

    def __init__(self, message: str, *, details: Any = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code


class NotFoundError(SpectraError):
    status_code = 404
    code = "not_found"


class ConflictError(SpectraError):
    status_code = 409
    code = "conflict"


class InvalidRequestError(SpectraError):
    status_code = 422
    code = "invalid_request"


class PayloadTooLargeError(SpectraError):
    status_code = 413
    code = "payload_too_large"


class InsufficientStorageError(SpectraError):
    status_code = 507
    code = "insufficient_storage"


class ForbiddenError(SpectraError):
    status_code = 403
    code = "forbidden"
