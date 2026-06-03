"""Typed API error hierarchy."""

from typing import Any


class NovaError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class NotFoundError(NovaError):
    def __init__(self, resource: str, resource_id: str) -> None:
        super().__init__(
            code="not_found",
            message=f"{resource} not found: {resource_id}",
            status_code=404,
            details={"resource": resource, "id": resource_id},
        )


class ConflictError(NovaError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(code="conflict", message=message, status_code=409, details=details)


class ValidationError(NovaError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(code="validation_error", message=message, status_code=422, details=details)


class UnauthorizedError(NovaError):
    def __init__(self, message: str = "Unauthorized") -> None:
        super().__init__(code="unauthorized", message=message, status_code=401)


class ServiceUnavailableError(NovaError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="service_unavailable",
            message=message,
            status_code=503,
            details=details,
        )
