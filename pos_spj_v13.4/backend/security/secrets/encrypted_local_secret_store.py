"""EncryptedLocalSecretStore — SHELL-1 security foundation.

Cross-platform fallback `SecretStoreGateway` for machines/tests where an OS
credential vault isn't the primary target. Every secret value is encrypted
at rest with Fernet (AES-128-CBC + HMAC); the Fernet master key itself is
protected with Windows DPAPI when running on Windows (tied to the current
Windows user, unrecoverable off-machine) and falls back to a
restrictive-permission key file elsewhere, which is logged as a weaker
posture — this store should be treated as the fallback, not the primary,
outside Windows.

The file only ever contains ciphertext plus non-sensitive metadata
(reference id, rotation timestamp, status). The raw key never touches this
module's return values or logs.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from backend.security.secrets.errors import SecretStoreUnavailableError
from backend.security.secrets.secret_store_gateway import SecretReference, mask_secret
from backend.shared.app_paths import AppPaths

logger = logging.getLogger("spj.security.secrets")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EncryptedLocalSecretStore:
    def __init__(self, *, app_paths: AppPaths | None = None, store_dir: Path | None = None) -> None:
        base = store_dir or (app_paths or AppPaths.from_environment()).user_data_dir / "secrets"
        base.mkdir(parents=True, exist_ok=True)
        self._store_path = base / "secret_store.enc.json"
        self._key_path = base / "master.key"
        self._fernet = Fernet(self._load_or_create_key())

    # ── SecretStoreGateway ──────────────────────────────────────────────────

    def set_secret(self, name: str, value: str) -> SecretReference:
        name = self._require_name(name)
        if not value:
            raise ValueError("value no puede estar vacío.")
        data = self._read_store()
        now = _utc_now_iso()
        existing = data.get(name)
        data[name] = {
            "ciphertext": self._fernet.encrypt(value.encode("utf-8")).decode("ascii"),
            "created_at": existing["created_at"] if existing else now,
            "last_rotated_at": now,
            "status": "ACTIVE",
        }
        self._write_store(data)
        return self._to_reference(name, value, data[name])

    def get_secret(self, name: str) -> str | None:
        name = self._require_name(name)
        entry = self._read_store().get(name)
        if not entry:
            return None
        try:
            return self._fernet.decrypt(entry["ciphertext"].encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise SecretStoreUnavailableError(
                f"No se pudo descifrar el secreto '{name}' — la clave maestra local "
                "no coincide (¿store copiado de otra máquina/usuario?)."
            ) from exc

    def describe(self, name: str) -> SecretReference | None:
        name = self._require_name(name)
        entry = self._read_store().get(name)
        if not entry:
            return None
        raw = self.get_secret(name) or ""
        return self._to_reference(name, raw, entry)

    def rotate_secret(self, name: str, new_value: str) -> SecretReference:
        name = self._require_name(name)
        if self.describe(name) is None:
            raise SecretStoreUnavailableError(
                f"No se puede rotar '{name}': no existe un secreto previo."
            )
        return self.set_secret(name, new_value)

    def delete_secret(self, name: str) -> None:
        name = self._require_name(name)
        data = self._read_store()
        if name in data:
            del data[name]
            self._write_store(data)

    def list_references(self) -> list[SecretReference]:
        data = self._read_store()
        return [
            self._to_reference(name, self.get_secret(name) or "", entry)
            for name, entry in data.items()
        ]

    # ── internals ────────────────────────────────────────────────────────────

    @staticmethod
    def _require_name(name: str) -> str:
        name = (name or "").strip()
        if not name:
            raise ValueError("El nombre del secreto no puede estar vacío.")
        return name

    @staticmethod
    def _to_reference(name: str, raw_value: str, entry: dict) -> SecretReference:
        return SecretReference(
            reference_id=name,
            masked_value=mask_secret(raw_value),
            last_rotated_at=entry.get("last_rotated_at", ""),
            status=entry.get("status", "ACTIVE"),
        )

    def _read_store(self) -> dict:
        if not self._store_path.exists():
            return {}
        try:
            return json.loads(self._store_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise SecretStoreUnavailableError(
                f"No se pudo leer el almacén de secretos local: {exc}"
            ) from exc

    def _write_store(self, data: dict) -> None:
        try:
            self._store_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            raise SecretStoreUnavailableError(
                f"No se pudo escribir el almacén de secretos local: {exc}"
            ) from exc

    def _load_or_create_key(self) -> bytes:
        if self._key_path.exists():
            return self._read_protected_key()
        key = Fernet.generate_key()
        self._write_protected_key(key)
        return key

    def _read_protected_key(self) -> bytes:
        blob = self._key_path.read_bytes()
        if sys.platform == "win32":
            try:
                import win32crypt

                _description, key = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
                return key
            except ImportError:
                logger.warning(
                    "pywin32 no disponible: leyendo la clave maestra sin DPAPI."
                )
                return blob
        return blob

    def _write_protected_key(self, key: bytes) -> None:
        if sys.platform == "win32":
            try:
                import win32crypt

                protected = win32crypt.CryptProtectData(
                    key, "SPJ ERP secret store master key", None, None, None, 0
                )
                self._key_path.write_bytes(protected)
                return
            except ImportError:
                logger.warning(
                    "pywin32 no disponible: guardando la clave maestra sin DPAPI "
                    "(protección reducida)."
                )
        self._key_path.write_bytes(key)
        try:
            self._key_path.chmod(0o600)
        except OSError:
            pass
