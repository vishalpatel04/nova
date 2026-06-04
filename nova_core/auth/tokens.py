"""Cryptographic token utilities — never store plaintext tokens."""

import hashlib
import secrets
from typing import Literal

TokenKind = Literal["client", "worker", "admin", "bootstrap"]


def generate_token(kind: TokenKind) -> str:
    prefix = {
        "client": "nova_cli",
        "worker": "nova_wrk",
        "admin": "nova_adm",
        "bootstrap": "nova_bts",
    }
    return f"{prefix[kind]}_{secrets.token_urlsafe(32)}"


def token_prefix(token: str) -> str:
    return token[:16]


def hash_token(token: str, pepper: str) -> str:
    return hashlib.sha256(f"{pepper}:{token}".encode()).hexdigest()


def verify_token(token: str, pepper: str, stored_hash: str) -> bool:
    return secrets.compare_digest(hash_token(token, pepper), stored_hash)


def generate_pairing_code() -> str:
    return secrets.token_hex(3).upper()


def generate_websocket_ticket() -> str:
    return f"nova_wst_{secrets.token_urlsafe(32)}"
