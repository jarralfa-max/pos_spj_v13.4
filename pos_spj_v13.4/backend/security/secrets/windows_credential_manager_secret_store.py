"""WindowsCredentialManagerSecretStore — SHELL-1 security foundation.

Primary `SecretStoreGateway` implementation on Windows: stores each secret
as a generic credential in the current Windows user's Credential Manager
vault (via pywin32's `win32cred`), namespaced under a fixed target prefix so
SPJ entries never collide with unrelated credentials on the machine.

Rotation timestamp and status are not fields Credential Manager offers
natively, so they are packed into the credential's `Comment` field as small
JSON — never the secret value itself, which lives only in `CredentialBlob`.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from backend.security.secrets.errors import SecretNotFoundError, SecretStoreUnavailableError
from backend.security.secrets.secret_store_gateway import SecretReference, mask_secret

_TARGET_PREFIX = "SPJ_ERP_POS/secret/"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_win32cred():
    if sys.platform != "win32":
        raise SecretStoreUnavailableError(
            "WindowsCredentialManagerSecretStore solo está disponible en Windows."
        )
    try:
        import win32cred

        return win32cred
    except ImportError as exc:
        raise SecretStoreUnavailableError(
            "pywin32 no está instalado — no se puede acceder al Credential Manager "
            "de Windows. Ejecute 'pip install pywin32'."
        ) from exc


class WindowsCredentialManagerSecretStore:
    def __init__(self) -> None:
        self._win32cred = _require_win32cred()

    # ── SecretStoreGateway ──────────────────────────────────────────────────

    def set_secret(self, name: str, value: str) -> SecretReference:
        name = self._require_name(name)
        if not value:
            raise ValueError("value no puede estar vacío.")
        existing = self._read_raw(name)
        now = _utc_now_iso()
        metadata = {
            "created_at": existing["metadata"]["created_at"] if existing else now,
            "last_rotated_at": now,
            "status": "ACTIVE",
        }
        self._write_raw(name, value, metadata)
        return self._to_reference(name, value, metadata)

    def get_secret(self, name: str) -> str | None:
        entry = self._read_raw(self._require_name(name))
        return entry["value"] if entry else None

    def describe(self, name: str) -> SecretReference | None:
        entry = self._read_raw(self._require_name(name))
        if not entry:
            return None
        return self._to_reference(name, entry["value"], entry["metadata"])

    def rotate_secret(self, name: str, new_value: str) -> SecretReference:
        name = self._require_name(name)
        if self._read_raw(name) is None:
            raise SecretNotFoundError(name)
        return self.set_secret(name, new_value)

    def delete_secret(self, name: str) -> None:
        name = self._require_name(name)
        try:
            self._win32cred.CredDelete(self._target(name), self._win32cred.CRED_TYPE_GENERIC, 0)
        except Exception:
            pass  # already absent — delete is idempotent

    def list_references(self) -> list[SecretReference]:
        try:
            creds = self._win32cred.CredEnumerate(f"{_TARGET_PREFIX}*", 0)
        except Exception:
            creds = []
        references = []
        for cred in creds or []:
            target = cred["TargetName"]
            name = target[len(_TARGET_PREFIX):]
            entry = self._read_raw(name)
            if entry:
                references.append(self._to_reference(name, entry["value"], entry["metadata"]))
        return references

    # ── internals ────────────────────────────────────────────────────────────

    @staticmethod
    def _require_name(name: str) -> str:
        name = (name or "").strip()
        if not name:
            raise ValueError("El nombre del secreto no puede estar vacío.")
        return name

    @staticmethod
    def _target(name: str) -> str:
        return f"{_TARGET_PREFIX}{name}"

    @staticmethod
    def _to_reference(name: str, raw_value: str, metadata: dict) -> SecretReference:
        return SecretReference(
            reference_id=name,
            masked_value=mask_secret(raw_value),
            last_rotated_at=metadata.get("last_rotated_at", ""),
            status=metadata.get("status", "ACTIVE"),
        )

    def _read_raw(self, name: str) -> dict | None:
        try:
            cred = self._win32cred.CredRead(self._target(name), self._win32cred.CRED_TYPE_GENERIC, 0)
        except Exception:
            return None
        blob: bytes = cred["CredentialBlob"]
        value = blob.decode("utf-16-le") if blob else ""
        try:
            metadata = json.loads(cred.get("Comment") or "{}")
        except json.JSONDecodeError:
            metadata = {}
        return {"value": value, "metadata": metadata}

    def _write_raw(self, name: str, value: str, metadata: dict) -> None:
        try:
            self._win32cred.CredWrite(
                {
                    "Type": self._win32cred.CRED_TYPE_GENERIC,
                    "TargetName": self._target(name),
                    "CredentialBlob": value,
                    "Comment": json.dumps(metadata, ensure_ascii=False),
                    "Persist": self._win32cred.CRED_PERSIST_LOCAL_MACHINE,
                },
                0,
            )
        except Exception as exc:
            raise SecretStoreUnavailableError(
                f"No se pudo escribir el secreto '{name}' en Credential Manager: {exc}"
            ) from exc
