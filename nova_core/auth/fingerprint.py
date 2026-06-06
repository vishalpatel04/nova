"""Request fingerprinting for scoped idempotency."""

import hashlib
import json
from typing import Any


def fingerprint_request(body: dict[str, Any] | None) -> str:
    normalized = json.dumps(body or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode()).hexdigest()
