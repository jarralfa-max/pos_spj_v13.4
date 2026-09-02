# infrastructure/secrets/secret_store.py — SecretStore centralizado (WA-1)
"""
Centraliza la lectura de secretos desde `configuraciones` (BD ERP), con una
cache TTL en memoria de proceso para no reabrir SQLite en cada llamada.

Contexto (whatsapp_security_audit.md, Hallazgo 1): antes de esto, cada
lectura de secreto (`get_meta_access_token`, `get_verify_token`, etc. en
`config/settings.py`) volvía a abrir una conexión SQLite nueva contra la BD
del ERP — se ejecutaba en cada `send_message` y en cada webhook recibido, sin
ningún caching.

Diseño importante: `SecretStore` cachea SOLO el resultado de la lectura
contra `configuraciones` (BD). El fallback a `.env`/constantes de módulo lo
sigue resolviendo el llamador (`config/settings.py`) y se pasa como
`env_fallback` en cada llamada — así el fallback siempre refleja el valor
vigente del proceso (importante para tests que hacen monkeypatch de las
constantes de `config.settings`), mientras que solo el costo de abrir SQLite
se cachea.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from typing import Callable, Dict, Tuple

logger = logging.getLogger("wa.secrets")

DEFAULT_TTL_SECONDS = 30.0


class SecretStore:
    """Lee secretos desde `configuraciones.wa_<key>` con cache TTL."""

    def __init__(
        self,
        db_path_getter: Callable[[], str],
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._db_path_getter = db_path_getter
        self._ttl = ttl_seconds
        self._cache: Dict[str, Tuple[str, float]] = {}

    def _read_erp_config(self, key: str) -> str:
        """Lee `configuraciones.wa_<key>` desde la BD del ERP.

        Mismo patrón que `config/settings.py::_read_erp_config` (acepta
        `verify_token` o `wa_verify_token`, devuelve el primer valor
        encontrado).
        """
        db_path = self._db_path_getter()
        if not db_path:
            return ""
        clave = key if key.startswith("wa_") else f"wa_{key}"
        try:
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    "SELECT valor FROM configuraciones WHERE clave=? LIMIT 1",
                    (clave,),
                ).fetchone()
            finally:
                conn.close()
            if row and row[0]:
                return str(row[0])
        except Exception as exc:
            logger.debug("SecretStore: no se pudo leer %s desde BD: %s", clave, exc)
        return ""

    def get(self, key: str, env_fallback: str = "") -> str:
        """Devuelve el secreto: BD (cacheada por TTL) primero, env después."""
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached is not None and (now - cached[1]) < self._ttl:
            db_value = cached[0]
        else:
            db_value = self._read_erp_config(key)
            self._cache[key] = (db_value, now)
        return db_value or (env_fallback or "")

    def clear_cache(self) -> None:
        """Limpia la cache TTL. Uso principal: tests que cambian la BD/ruta
        entre casos y necesitan forzar una relectura inmediata."""
        self._cache.clear()

    @staticmethod
    def mask(value: str) -> str:
        """Enmascara un secreto para logs/UI.

        Mismo patrón que `core/services/whatsapp_credential_service.py:
        _mask_token` — primeros 4 + `*` de relleno + últimos 4, o
        completamente enmascarado si el valor es demasiado corto.
        """
        if not value or len(value) < 8:
            return "***"
        return value[:4] + "*" * (len(value) - 8) + value[-4:]
