"""Device pairing and credential management."""

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.auth.principal import Principal
from nova_core.auth.tokens import (
    TokenKind,
    generate_pairing_code,
    generate_token,
    hash_token,
    token_prefix,
)
from nova_core.models.enums import DeviceStatus, PairingCodeStatus, TokenState
from nova_core.models.orm import (
    Device,
    DeviceCredential,
    DevicePairingCode,
    TokenRevocation,
    User,
)
from nova_core.schemas.errors import (
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event
from nova_core.utils.time import ensure_utc, utc_now


class PairingRateLimiter:
    """In-memory sliding window rate limiter for pairing attempts."""

    def __init__(self) -> None:
        self._attempts: dict[str, list[float]] = {}

    def check(self, key: str, max_attempts: int, window_seconds: int) -> None:
        import time

        now = time.time()
        window_start = now - window_seconds
        attempts = [t for t in self._attempts.get(key, []) if t > window_start]
        if len(attempts) >= max_attempts:
            raise ValidationError(
                "Pairing attempt rate limit exceeded",
                details={"retry_after_seconds": window_seconds},
            )
        attempts.append(now)
        self._attempts[key] = attempts


_pairing_limiter = PairingRateLimiter()


class PairingService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self._policies = settings.load_yaml("policies.yaml")

    def _pairing_policy(self) -> dict[str, Any]:
        pairing = self._policies.get("pairing", {})
        return pairing if isinstance(pairing, dict) else {}

    async def create_pairing_code(
        self,
        *,
        user_id: str,
        device_type: str,
        proposed_device_id: str | None = None,
        proposed_name: str | None = None,
    ) -> tuple[DevicePairingCode, str]:
        policy = self._pairing_policy()
        ttl_minutes = int(policy.get("code_ttl_minutes", 15))
        requires_approval = bool(policy.get("require_approval", True))

        code = generate_pairing_code()
        pairing = DevicePairingCode(
            user_id=user_id,
            code=code,
            device_type=device_type,
            proposed_device_id=proposed_device_id,
            proposed_name=proposed_name,
            requires_approval=requires_approval,
            expires_at=utc_now() + timedelta(minutes=ttl_minutes),
        )
        self.session.add(pairing)
        await self.session.flush()

        await record_audit_event(
            self.session,
            actor_type="user",
            actor_id=user_id,
            action="pairing.code_created",
            resource_type="pairing_code",
            resource_id=pairing.id,
            details={"device_type": device_type},
        )
        await self.session.commit()
        return pairing, code

    async def claim_pairing_code(
        self,
        *,
        code: str,
        device_id: str,
        name: str,
        device_type: str,
        hostname: str | None = None,
        os_version: str | None = None,
        architecture: str | None = None,
        metadata: dict[str, Any] | None = None,
        client_ip: str | None = None,
    ) -> tuple[DevicePairingCode, str | None]:
        policy = self._pairing_policy()
        max_attempts = int(policy.get("max_attempts_per_hour", 10))
        _pairing_limiter.check(client_ip or device_id, max_attempts, 3600)

        result = await self.session.execute(
            select(DevicePairingCode).where(DevicePairingCode.code == code.upper())
        )
        pairing = result.scalar_one_or_none()
        if not pairing:
            raise NotFoundError("PairingCode", code)

        if ensure_utc(pairing.expires_at) < utc_now():
            pairing.status = PairingCodeStatus.EXPIRED.value
            await self.session.commit()
            raise ValidationError("Pairing code expired")

        if pairing.status == PairingCodeStatus.CLAIMED.value:
            raise ConflictError("Pairing code already claimed")

        if pairing.status == PairingCodeStatus.REJECTED.value:
            raise ValidationError("Pairing code was rejected")

        pairing.proposed_device_id = device_id
        pairing.proposed_name = name
        pairing.claimed_at = utc_now()

        token: str | None = None
        if not pairing.requires_approval:
            pairing.status = PairingCodeStatus.APPROVED.value
            pairing.approved_at = utc_now()
            token = await self._finalize_pairing(
                pairing, device_id, name, device_type, hostname, os_version, architecture, metadata
            )
        else:
            pairing.status = PairingCodeStatus.PENDING.value

        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=device_id,
            action="pairing.claimed",
            resource_type="pairing_code",
            resource_id=pairing.id,
            details={"requires_approval": pairing.requires_approval},
        )
        await self.session.commit()
        return pairing, token

    async def approve_pairing(self, pairing_id: str, approver: Principal) -> tuple[str, str]:
        result = await self.session.execute(
            select(DevicePairingCode).where(DevicePairingCode.id == pairing_id)
        )
        pairing = result.scalar_one_or_none()
        if not pairing:
            raise NotFoundError("PairingCode", pairing_id)

        if pairing.status == PairingCodeStatus.CLAIMED.value:
            raise ConflictError("Pairing already completed")

        if ensure_utc(pairing.expires_at) < utc_now():
            pairing.status = PairingCodeStatus.EXPIRED.value
            await self.session.commit()
            raise ValidationError("Pairing code expired")

        if not pairing.proposed_device_id or not pairing.proposed_name:
            raise ValidationError("Pairing code must be claimed before approval")

        pairing.status = PairingCodeStatus.APPROVED.value
        pairing.approved_at = utc_now()

        cred_type = "worker" if "worker" in pairing.device_type else "client"
        token = await self._finalize_pairing(
            pairing,
            pairing.proposed_device_id,
            pairing.proposed_name,
            pairing.device_type,
            None,
            None,
            None,
            None,
            credential_type=cred_type,
        )
        pairing.status = PairingCodeStatus.CLAIMED.value

        await record_audit_event(
            self.session,
            actor_type=approver.principal_type,
            actor_id=approver.principal_id,
            action="pairing.approved",
            resource_type="pairing_code",
            resource_id=pairing.id,
        )
        await self.session.commit()
        return pairing.proposed_device_id, token

    async def _finalize_pairing(
        self,
        pairing: DevicePairingCode,
        device_id: str,
        name: str,
        device_type: str,
        hostname: str | None,
        os_version: str | None,
        architecture: str | None,
        metadata: dict[str, Any] | None,
        credential_type: str | None = None,
    ) -> str:
        user_result = await self.session.execute(select(User).where(User.id == pairing.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            user = User(id=pairing.user_id, display_name="Arth Agrawal")
            self.session.add(user)
            await self.session.flush()

        device_result = await self.session.execute(select(Device).where(Device.id == device_id))
        device = device_result.scalar_one_or_none()
        privacy = "restricted" if device_type == "friend_laptop" else "owner"

        if device:
            device.name = name
            device.device_type = device_type
            device.hostname = hostname
            device.os_version = os_version
            device.architecture = architecture
            device.metadata_json = metadata
            device.privacy_class = privacy
            device.status = DeviceStatus.REGISTERED.value
            device.token_state = TokenState.ACTIVE.value
        else:
            device = Device(
                id=device_id,
                user_id=user.id,
                name=name,
                device_type=device_type,
                hostname=hostname,
                os_version=os_version,
                architecture=architecture,
                metadata_json=metadata,
                privacy_class=privacy,
                status=DeviceStatus.REGISTERED.value,
                token_state=TokenState.ACTIVE.value,
            )
            self.session.add(device)
        await self.session.flush()

        cred_type = credential_type or ("worker" if "worker" in device_type else "client")
        token, _cred = await self._issue_credential(device_id, cred_type)
        pairing.status = PairingCodeStatus.CLAIMED.value
        return token

    async def _issue_credential(
        self, device_id: str, credential_type: str
    ) -> tuple[str, DeviceCredential]:
        policy = self._pairing_policy()
        token_ttl_days = int(policy.get("token_ttl_days", 90))
        kind: TokenKind = "worker" if credential_type == "worker" else "client"
        token = generate_token(kind)
        cred = DeviceCredential(
            device_id=device_id,
            token_prefix=token_prefix(token),
            token_hash=hash_token(token, self.settings.nova_token_pepper),
            credential_type=credential_type,
            state=TokenState.ACTIVE.value,
            expires_at=utc_now() + timedelta(days=token_ttl_days),
        )
        self.session.add(cred)
        await self.session.flush()
        return token, cred

    async def rotate_token(self, device_id: str, principal: Principal) -> str:
        result = await self.session.execute(
            select(DeviceCredential).where(
                DeviceCredential.device_id == device_id,
                DeviceCredential.state == TokenState.ACTIVE.value,
            )
        )
        old_creds = list(result.scalars().all())
        for old in old_creds:
            old.state = TokenState.ROTATED.value

        device_result = await self.session.execute(select(Device).where(Device.id == device_id))
        device = device_result.scalar_one_or_none()
        if not device:
            raise NotFoundError("Device", device_id)

        cred_type = "worker" if "worker" in device.device_type else "client"
        token, _cred = await self._issue_credential(device_id, cred_type)

        await record_audit_event(
            self.session,
            actor_type=principal.principal_type,
            actor_id=principal.principal_id,
            action="device.token_rotated",
            resource_type="device",
            resource_id=device_id,
        )
        await self.session.commit()
        return token

    async def revoke_device(self, device_id: str, principal: Principal, reason: str | None) -> None:
        device_result = await self.session.execute(select(Device).where(Device.id == device_id))
        device = device_result.scalar_one_or_none()
        if not device:
            raise NotFoundError("Device", device_id)

        device.status = DeviceStatus.REVOKED.value
        device.token_state = TokenState.REVOKED.value
        device.connection_status = "disconnected"

        cred_result = await self.session.execute(
            select(DeviceCredential).where(
                DeviceCredential.device_id == device_id,
                DeviceCredential.state == TokenState.ACTIVE.value,
            )
        )
        for cred in cred_result.scalars().all():
            cred.state = TokenState.REVOKED.value
            cred.revoked_at = utc_now()
            self.session.add(
                TokenRevocation(
                    credential_id=cred.id,
                    device_id=device_id,
                    reason=reason,
                    revoked_by=principal.principal_id,
                )
            )

        await record_audit_event(
            self.session,
            actor_type=principal.principal_type,
            actor_id=principal.principal_id,
            action="device.revoked",
            resource_type="device",
            resource_id=device_id,
            details={"reason": reason},
        )
        await self.session.commit()


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def authenticate_token(self, token: str) -> Principal:
        if (
            self.settings.nova_bootstrap_admin_enabled
            and token == self.settings.nova_bootstrap_admin_token
        ):
            return Principal(
                principal_type="bootstrap_admin",
                principal_id="bootstrap_admin",
                user_id=self.settings.nova_default_user_id,
            )

        prefix = token_prefix(token)
        result = await self.session.execute(
            select(DeviceCredential, Device)
            .join(Device, Device.id == DeviceCredential.device_id)
            .where(
                DeviceCredential.token_prefix == prefix,
                DeviceCredential.state == TokenState.ACTIVE.value,
            )
        )
        rows = result.all()
        for cred, device in rows:
            if not verify_token_hash(token, self.settings.nova_token_pepper, cred.token_hash):
                continue
            if cred.expires_at and ensure_utc(cred.expires_at) < utc_now():
                cred.state = TokenState.EXPIRED.value
                await self.session.commit()
                raise UnauthorizedError("Token expired")
            if device.status == DeviceStatus.REVOKED.value:
                raise UnauthorizedError("Device revoked")

            return Principal(
                principal_type="device",
                principal_id=device.id,
                user_id=device.user_id,
                device_id=device.id,
                device_type=device.device_type,
                token_id=cred.id,
            )

        raise UnauthorizedError("Invalid token")


def verify_token_hash(token: str, pepper: str, stored_hash: str) -> bool:
    from nova_core.auth.tokens import verify_token

    return verify_token(token, pepper, stored_hash)
