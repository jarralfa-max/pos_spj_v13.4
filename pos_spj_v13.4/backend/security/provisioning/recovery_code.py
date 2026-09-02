"""RecoveryCode — SHELL-2 security foundation.

A single backup code from the installation's `InstallationRecoveryKit`.
Codes are short enough for a human to copy onto paper (`xxxxx-xxxxx`, 10
lowercase hex characters), shown to the owner exactly once at generation,
and — like `RecoveryToken` — hashed with a fast digest rather than Argon2id:
they're machine-generated high-entropy secrets, not user-chosen passwords,
so a fast unsalted hash is the correct and standard tool (same rationale as
`backend.security.recovery.recovery_token`).
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from backend.shared.ids import new_uuid


class RecoveryCodeStatus(str, Enum):
    ACTIVE = "ACTIVE"
    USED = "USED"
    REVOKED = "REVOKED"


def generate_backup_code() -> str:
    raw = secrets.token_hex(5)  # 10 lowercase hex chars, ~40 bits
    return f"{raw[:5]}-{raw[5:]}"


def hash_backup_code(raw_code: str) -> str:
    if not raw_code:
        raise ValueError("raw_code no puede estar vacío.")
    normalized = raw_code.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RecoveryCode:
    id: str
    installation_id: str
    code_hash: str
    status: RecoveryCodeStatus
    created_at: datetime
    used_at: datetime | None = None

    @classmethod
    def issue(cls, installation_id: str, *, raw_code: str, now: datetime | None = None) -> "RecoveryCode":
        return cls(
            id=new_uuid(),
            installation_id=installation_id,
            code_hash=hash_backup_code(raw_code),
            status=RecoveryCodeStatus.ACTIVE,
            created_at=now or datetime.now(timezone.utc),
        )

    def is_active(self) -> bool:
        return self.status is RecoveryCodeStatus.ACTIVE

    def redeem(self, *, now: datetime | None = None) -> "RecoveryCode":
        if not self.is_active():
            raise ValueError(f"El código {self.id} no está activo ({self.status.value}).")
        return RecoveryCode(
            id=self.id, installation_id=self.installation_id, code_hash=self.code_hash,
            status=RecoveryCodeStatus.USED, created_at=self.created_at,
            used_at=now or datetime.now(timezone.utc),
        )

    def revoke(self) -> "RecoveryCode":
        if not self.is_active():
            return self
        return RecoveryCode(
            id=self.id, installation_id=self.installation_id, code_hash=self.code_hash,
            status=RecoveryCodeStatus.REVOKED, created_at=self.created_at, used_at=self.used_at,
        )
