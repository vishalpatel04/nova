"""Authentication and authorization types."""

from dataclasses import dataclass
from typing import Literal

PrincipalType = Literal["user", "device", "bootstrap_admin"]


@dataclass(frozen=True)
class Principal:
    principal_type: PrincipalType
    principal_id: str
    user_id: str
    device_id: str | None = None
    device_type: str | None = None
    token_id: str | None = None

    @property
    def idempotency_scope_id(self) -> str:
        if self.device_id:
            return f"device:{self.device_id}"
        return f"user:{self.user_id}"
