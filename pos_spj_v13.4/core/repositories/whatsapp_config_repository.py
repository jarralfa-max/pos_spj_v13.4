# core/repositories/whatsapp_config_repository.py
"""Acceso a datos de configuración WhatsApp. Sin lógica de negocio."""
from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger("spj.repo.wa_config")

_CFG_PREFIX = "wa_"


class WhatsAppConfigRepository:
    def __init__(self, conn):
        self.conn = conn
        self._ensure_table()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _ensure_table(self):
        try:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS whatsapp_numeros (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    sucursal_id     INTEGER,
                    canal           TEXT DEFAULT 'todos',
                    proveedor       TEXT DEFAULT 'meta',
                    numero_negocio  TEXT,
                    meta_token      TEXT,
                    meta_phone_id   TEXT,
                    twilio_sid      TEXT,
                    twilio_token    TEXT,
                    verify_token    TEXT DEFAULT 'spj_verify',
                    rasa_url        TEXT DEFAULT 'http://localhost:5005',
                    rasa_activo     INTEGER DEFAULT 0,
                    activo          INTEGER DEFAULT 1,
                    nombre_sucursal TEXT,
                    UNIQUE(sucursal_id, canal)
                )""")
            try:
                self.conn.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("_ensure_table whatsapp_numeros: %s", e)

    # ── Números ───────────────────────────────────────────────────────────────

    def list_numeros(self) -> List[Dict]:
        try:
            rows = self.conn.execute(
                "SELECT id, COALESCE(nombre_sucursal,'Global') as nombre_sucursal, "
                "canal, COALESCE(numero_negocio,'') as numero_negocio, "
                "proveedor, activo "
                "FROM whatsapp_numeros ORDER BY sucursal_id NULLS FIRST"
            ).fetchall()
            return [dict(r) if hasattr(r, 'keys') else
                    {"id": r[0], "nombre_sucursal": r[1], "canal": r[2],
                     "numero_negocio": r[3], "proveedor": r[4], "activo": r[5]}
                    for r in rows]
        except Exception as e:
            logger.debug("list_numeros: %s", e)
            return []

    def get_numero(self, row_id: int) -> Optional[Dict]:
        try:
            row = self.conn.execute(
                "SELECT sucursal_id, canal, proveedor, numero_negocio, "
                "meta_phone_id, meta_token, twilio_sid, rasa_url, "
                "rasa_activo, activo, nombre_sucursal "
                "FROM whatsapp_numeros WHERE id=?", (row_id,)
            ).fetchone()
            if not row:
                return None
            keys = ["sucursal_id","canal","proveedor","numero_negocio",
                    "meta_phone_id","meta_token","twilio_sid","rasa_url",
                    "rasa_activo","activo","nombre_sucursal"]
            return dict(zip(keys, row)) if not hasattr(row, 'keys') else dict(row)
        except Exception as e:
            logger.debug("get_numero %s: %s", row_id, e)
            return None

    def save_numero(self, data: Dict, row_id: Optional[int] = None) -> bool:
        """Upsert. data keys: sucursal_id, canal, proveedor, numero_negocio,
        meta_phone_id, meta_token, twilio_sid, rasa_url, rasa_activo,
        activo, nombre_sucursal."""
        try:
            fields = ("sucursal_id", "canal", "proveedor", "numero_negocio",
                      "meta_phone_id", "meta_token", "twilio_sid",
                      "rasa_url", "rasa_activo", "activo", "nombre_sucursal")
            vals = tuple(data.get(f) for f in fields)
            if row_id:
                sets = ", ".join(f"{f}=?" for f in fields)
                self.conn.execute(
                    f"UPDATE whatsapp_numeros SET {sets} WHERE id=?",
                    vals + (row_id,))
            else:
                placeholders = ", ".join("?" * len(fields))
                self.conn.execute(
                    f"INSERT INTO whatsapp_numeros ({', '.join(fields)}) "
                    f"VALUES ({placeholders})", vals)
            try:
                self.conn.commit()
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error("save_numero: %s", e)
            return False

    def delete_numero(self, row_id: int) -> bool:
        try:
            self.conn.execute(
                "DELETE FROM whatsapp_numeros WHERE id=?", (row_id,))
            try:
                self.conn.commit()
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error("delete_numero %s: %s", row_id, e)
            return False

    # ── Configuraciones key-value ──────────────────────────────────────────────

    def get_config(self, key: str, default: str = "") -> str:
        clave = f"{_CFG_PREFIX}{key}"
        try:
            row = self.conn.execute(
                "SELECT valor FROM configuraciones WHERE clave=?", (clave,)
            ).fetchone()
            return (row[0] if row else default) or default
        except Exception:
            return default

    def set_config(self, key: str, value: str) -> None:
        clave = f"{_CFG_PREFIX}{key}"
        try:
            self.conn.execute(
                "INSERT INTO configuraciones(clave,valor) VALUES(?,?) "
                "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                (clave, value))
        except Exception as e:
            logger.debug("set_config %s: %s", key, e)

    def set_config_batch(self, items: Dict[str, str]) -> None:
        for k, v in items.items():
            self.set_config(k, v)
        try:
            self.conn.commit()
        except Exception:
            pass

    # ── Sucursales (lectura) ───────────────────────────────────────────────────

    def list_sucursales_activas(self) -> List[Dict]:
        try:
            rows = self.conn.execute(
                "SELECT id, nombre FROM sucursales WHERE activa=1 ORDER BY nombre"
            ).fetchall()
            return [{"id": r[0], "nombre": r[1]} for r in rows]
        except Exception:
            return []
