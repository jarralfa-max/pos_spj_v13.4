# core/repositories/whatsapp_config_repository.py
"""Acceso a datos de configuración WhatsApp — tabla whatsapp_numeros y configuraciones."""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("spj.repo.whatsapp_config")


class WhatsAppConfigRepository:
    """Repository para whatsapp_numeros y claves wa_* en configuraciones."""

    def __init__(self, db):
        self._db = db

    # ── whatsapp_numeros ──────────────────────────────────────────────────────

    def get_numeros(self) -> List[Dict]:
        try:
            rows = self._db.execute(
                "SELECT id, COALESCE(nombre_sucursal,'Global'), canal, "
                "COALESCE(numero_negocio,''), proveedor, activo "
                "FROM whatsapp_numeros ORDER BY sucursal_id NULLS FIRST"
            ).fetchall()
            return [tuple(r) for r in rows]
        except Exception as e:
            logger.debug("get_numeros: %s", e)
            return []

    def get_numero_by_id(self, numero_id: int) -> Optional[tuple]:
        try:
            return self._db.execute(
                "SELECT sucursal_id, canal, proveedor, numero_negocio, "
                "meta_phone_id, meta_token, twilio_sid, rasa_url, rasa_activo, activo "
                "FROM whatsapp_numeros WHERE id=?", (numero_id,)
            ).fetchone()
        except Exception as e:
            logger.debug("get_numero_by_id: %s", e)
            return None

    def insert_numero(self, suc_id, canal, proveedor, numero, phone_id,
                      token, sid, rasa_url, rasa_act, activo, suc_nombre) -> None:
        self._db.execute(
            "INSERT INTO whatsapp_numeros "
            "(sucursal_id, canal, proveedor, numero_negocio, meta_phone_id, "
            "meta_token, twilio_sid, rasa_url, rasa_activo, activo, nombre_sucursal) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (suc_id, canal, proveedor, numero, phone_id, token, sid,
             rasa_url, rasa_act, activo, suc_nombre))
        self._commit()

    def update_numero(self, numero_id, suc_id, canal, proveedor, numero, phone_id,
                      token, sid, rasa_url, rasa_act, activo, suc_nombre) -> None:
        self._db.execute(
            "UPDATE whatsapp_numeros SET sucursal_id=?, canal=?, proveedor=?, "
            "numero_negocio=?, meta_phone_id=?, meta_token=?, twilio_sid=?, "
            "rasa_url=?, rasa_activo=?, activo=?, nombre_sucursal=? "
            "WHERE id=?",
            (suc_id, canal, proveedor, numero, phone_id, token, sid,
             rasa_url, rasa_act, activo, suc_nombre, numero_id))
        self._commit()

    def delete_numero(self, numero_id: int) -> None:
        self._db.execute("DELETE FROM whatsapp_numeros WHERE id=?", (numero_id,))
        self._commit()

    def get_sucursales_activas(self) -> List[tuple]:
        try:
            return self._db.execute(
                "SELECT id, nombre FROM sucursales WHERE activa=1 ORDER BY nombre"
            ).fetchall()
        except Exception:
            return []

    # ── configuraciones (claves wa_*) ─────────────────────────────────────────

    def get_config(self, key: str, default: str = "") -> str:
        try:
            r = self._db.execute(
                "SELECT valor FROM configuraciones WHERE clave=?", (f"wa_{key}",)
            ).fetchone()
            return r[0] if r else default
        except Exception:
            return default

    def set_config(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO configuraciones(clave,valor) VALUES(?,?) "
            "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
            (f"wa_{key}", value))

    def set_config_raw(self, key: str, value: str) -> None:
        """Guarda con clave exacta (sin prefijo wa_)."""
        self._db.execute(
            "INSERT INTO configuraciones(clave,valor) VALUES(?,?) "
            "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
            (key, value))

    def commit(self) -> None:
        self._commit()

    def _commit(self) -> None:
        try:
            self._db.commit()
        except Exception:
            pass
