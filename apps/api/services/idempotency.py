"""Scoped idempotency service."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.auth.fingerprint import fingerprint_request
from nova_core.models.orm import IdempotencyRecord
from nova_core.schemas.errors import ConflictError


class IdempotencyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def check_or_store(
        self,
        *,
        principal_id: str,
        scope: str,
        idempotency_key: str,
        request_body: dict[str, Any] | None,
        resource_type: str,
        resource_id: str,
    ) -> IdempotencyRecord | None:
        fingerprint = fingerprint_request(request_body)
        result = await self.session.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.principal_id == principal_id,
                IdempotencyRecord.scope == scope,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            if existing.request_fingerprint != fingerprint:
                raise ConflictError(
                    "Idempotency key reused with different request body",
                    details={
                        "idempotency_key": idempotency_key,
                        "existing_resource_id": existing.resource_id,
                    },
                )
            return existing

        record = IdempotencyRecord(
            principal_id=principal_id,
            scope=scope,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        self.session.add(record)
        await self.session.flush()
        return None

    async def get_existing(
        self,
        *,
        principal_id: str,
        scope: str,
        idempotency_key: str,
        request_body: dict[str, Any] | None,
    ) -> IdempotencyRecord | None:
        fingerprint = fingerprint_request(request_body)
        result = await self.session.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.principal_id == principal_id,
                IdempotencyRecord.scope == scope,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        existing = result.scalar_one_or_none()
        if existing and existing.request_fingerprint != fingerprint:
            raise ConflictError(
                "Idempotency key reused with different request body",
                details={"idempotency_key": idempotency_key},
            )
        return existing
