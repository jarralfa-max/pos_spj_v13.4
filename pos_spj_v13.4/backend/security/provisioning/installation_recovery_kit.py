"""InstallationRecoveryKit — SHELL-2 security foundation.

Backup codes for the installation itself (distinct from
`AccountRecoveryService`'s per-user password-reset tokens): generated once
during provisioning, shown to the owner exactly once, printable/exportable,
each usable exactly one time to recover a LOCKED/RECOVERY_REQUIRED
installation. No universal support code exists — every code is
installation-specific and hashed at rest.
"""
from __future__ import annotations

from datetime import datetime

from backend.security.provisioning.recovery_code import RecoveryCode, generate_backup_code, hash_backup_code
from backend.security.provisioning.recovery_code_repository import RecoveryCodeRepository

DEFAULT_CODE_COUNT = 10


class InstallationRecoveryKit:
    def __init__(self, *, code_repository: RecoveryCodeRepository) -> None:
        self._codes = code_repository

    def generate(
        self, installation_id: str, *, count: int = DEFAULT_CODE_COUNT, now: datetime | None = None
    ) -> list[str]:
        """Issue `count` fresh backup codes. Returns the raw codes — the only
        time they exist in plaintext; hand them to the owner to print/export
        and never persist or log the raw values."""
        if count < 1:
            raise ValueError("count debe ser al menos 1.")
        raw_codes = []
        for _ in range(count):
            raw_code = generate_backup_code()
            self._codes.save(RecoveryCode.issue(installation_id, raw_code=raw_code, now=now))
            raw_codes.append(raw_code)
        return raw_codes

    def redeem(self, installation_id: str, raw_code: str, *, now: datetime | None = None) -> bool:
        """Consume one code. Returns False for unknown/foreign/already-used
        codes (never raises — callers show a generic failure either way, to
        avoid leaking which case it was)."""
        code = self._codes.find_by_hash(hash_backup_code(raw_code)) if raw_code else None
        if code is None or code.installation_id != installation_id or not code.is_active():
            return False
        self._codes.replace(code.redeem(now=now))
        return True

    def revoke_all(self, installation_id: str) -> int:
        active = self._codes.find_active_for_installation(installation_id)
        for code in active:
            self._codes.replace(code.revoke())
        return len(active)

    def rotate(
        self, installation_id: str, *, count: int = DEFAULT_CODE_COUNT, now: datetime | None = None
    ) -> list[str]:
        """Revoke every still-active code and issue a fresh batch."""
        self.revoke_all(installation_id)
        return self.generate(installation_id, count=count, now=now)
