"""Read ERP integration credentials without caching secret values across rotations."""
from __future__ import annotations
from pathlib import Path
import os
import sqlite3
from typing import Callable
from backend.infrastructure.integrations.whatsapp_credential_resolver import read_whatsapp_setting

DEFAULT_TTL_SECONDS = 0

class SecretStore:
    def __init__(self, db_path_getter: Callable[[], str], ttl_seconds=DEFAULT_TTL_SECONDS,
                 *, secret_gateway=None, instance_id: str | None = None) -> None:
        self._db_path_getter = db_path_getter
        self._gateway = secret_gateway
        self._instance_id = instance_id

    @property
    def gateway(self):
        if self._gateway is None:
            from backend.security.secrets.default_secret_store import build_default_secret_store
            self._gateway = build_default_secret_store()
        return self._gateway

    def get(self, key: str, env_fallback: str = '') -> str:
        db_path = self._db_path_getter()
        if not db_path:
            return env_fallback or ''
        path = Path(db_path).resolve()
        if not path.is_file():
            raise RuntimeError('WhatsApp configuration database does not exist; check ERP_DB_PATH')
        try:
            conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
            try:
                value = read_whatsapp_setting(conn, key, self,
                    instance_id=self._instance_id if self._instance_id is not None
                    else os.getenv('WA_INTEGRATION_INSTANCE_ID', ''))
            finally:
                conn.close()
        except sqlite3.Error as exc:
            raise RuntimeError('WhatsApp configuration database could not be read') from exc
        return (env_fallback or '') if value is None else value

    def describe(self, name):
        return self.gateway.describe(name)

    def get_secret(self, name):
        return self.gateway.get_secret(name)

    def clear_cache(self) -> None:
        """Public invalidation hook; values are always read afresh."""

    @staticmethod
    def mask(value: str) -> str:
        from whatsapp_service.infrastructure.security.redaction import redact_secret
        return redact_secret(value)
