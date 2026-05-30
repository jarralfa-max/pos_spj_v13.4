# core/repositories/hardware_config_repository.py
"""Canonical hardware configuration repository.

This module is the single database contract for hardware settings.
The canonical table is ``hardware_config``. Do not introduce or read from
``configuraciones_hardware`` in production code; that table was a legacy
assumption and caused PrinterService to look at a non-existent source.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

logger = logging.getLogger("spj.hardware_config")


class HardwareConfigRepository:
    """Read/write repository for the canonical ``hardware_config`` table."""

    DEFAULT_TYPES = {
        "ticket": "Impresora de tickets",
        "etiquetas": "Impresora de etiquetas",
        "bascula": "Báscula",
        "cajon": "Cajón de dinero",
        "scanner": "Escáner",
        "red": "Red",
    }

    def __init__(self, db):
        self.db = db

    def ensure_schema(self) -> None:
        """Create the canonical table when running on an older local DB."""
        if self.db is None:
            return
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS hardware_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT UNIQUE NOT NULL,
                nombre TEXT NOT NULL,
                driver TEXT,
                puerto TEXT,
                configuraciones TEXT,
                activo INTEGER DEFAULT 1,
                sucursal_id INTEGER DEFAULT 1,
                fecha_actualizacion DATETIME DEFAULT (datetime('now'))
            )
            """
        )

    def seed_defaults(self) -> None:
        """Ensure stable rows exist for every supported hardware domain."""
        if self.db is None:
            return
        self.ensure_schema()
        for tipo, nombre in self.DEFAULT_TYPES.items():
            self.db.execute(
                """
                INSERT OR IGNORE INTO hardware_config(tipo, nombre, activo, configuraciones)
                VALUES (?, ?, 1, '{}')
                """,
                (tipo, nombre),
            )

    def get_config(self, tipo: str) -> Dict[str, Any]:
        """Return parsed JSON config for ``tipo`` from the canonical table."""
        if self.db is None:
            return {}
        self.ensure_schema()
        row = self.db.execute(
            """
            SELECT configuraciones
            FROM hardware_config
            WHERE tipo=? AND COALESCE(activo, 1)=1
            LIMIT 1
            """,
            (str(tipo),),
        ).fetchone()
        if not row:
            return {}
        raw = row[0] if not isinstance(row, dict) else row.get("configuraciones")
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception as exc:
            logger.warning("Config JSON inválido para hardware_config.%s: %s", tipo, exc)
            return {}

    def save_config(self, tipo: str, nombre: str, config: Dict[str, Any], activo: int = 1) -> None:
        """Persist a config dict using the canonical JSON contract."""
        if self.db is None:
            return
        self.ensure_schema()
        payload = json.dumps(config or {}, ensure_ascii=False)
        self.db.execute(
            """
            INSERT INTO hardware_config(tipo, nombre, activo, configuraciones)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(tipo) DO UPDATE SET
                nombre=excluded.nombre,
                activo=excluded.activo,
                configuraciones=excluded.configuraciones,
                fecha_actualizacion=datetime('now')
            """,
            (str(tipo), str(nombre or tipo), int(activo), payload),
        )

    def migrate_legacy_configuraciones_hardware(self) -> None:
        """Best-effort import from the old assumed table, if it exists.

        This is only a migration bridge. Production readers must use
        ``hardware_config`` exclusively.
        """
        if self.db is None:
            return
        exists = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='configuraciones_hardware'"
        ).fetchone()
        if not exists:
            return
        rows = self.db.execute(
            "SELECT tipo, clave, valor FROM configuraciones_hardware"
        ).fetchall()
        grouped: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            tipo = row[0]
            clave = row[1]
            valor = row[2]
            grouped.setdefault(str(tipo), {})[str(clave)] = valor
        for tipo, cfg in grouped.items():
            target = "ticket" if tipo in {"ticket", "impresora"} else tipo
            if target in {"impresora_etiquetas", "label", "labels"}:
                target = "etiquetas"
            self.save_config(target, self.DEFAULT_TYPES.get(target, target), cfg, activo=1)
