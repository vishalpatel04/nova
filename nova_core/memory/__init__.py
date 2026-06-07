"""Local memory kernel — indexing, retrieval, and vault-safe access."""

from nova_core.memory.access_policy import (
    AccessPolicy,
    AccessProfile,
    resolve_access_policy,
)
from nova_core.memory.vault import (
    VAULT_INVISIBLE_MESSAGE,
    assert_not_vault_path,
    is_vault_path,
)

__all__ = [
    "AccessProfile",
    "AccessPolicy",
    "resolve_access_policy",
    "VAULT_INVISIBLE_MESSAGE",
    "is_vault_path",
    "assert_not_vault_path",
]
