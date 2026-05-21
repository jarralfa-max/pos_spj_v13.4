# core/services/finance/idempotency_service.py — SPJ ERP v13.4
"""
IdempotencyService — garantiza escrituras financieras únicas por operation_id.

Reglas:
  - operation_id es la clave de idempotencia para toda escritura financiera.
  - Formato canónico: "{source_module}-{source_id}-{event_type}"
    Ej: "ventas-1234-VENTA_CONTADO", "compras-456-COMPRA_CREDITO"
  - exists() verifica si ya existe el operation_id en la tabla indicada.
  - get_existing_id() retorna el id del registro existente (0 si no existe).
  - generate() genera un operation_id canónico consistente.

Tablas soportadas: financial_documents, treasury_movements, journal_entries,
  fixed_assets, asset_depreciation_entries, maintenance_records,
  operating_supplies, financial_trace_log.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

logger = logging.getLogger("spj.finance.idempotency")

_SUPPORTED_TABLES = frozenset({
    "financial_documents",
    "treasury_movements",
    "journal_entries",
    "fixed_assets",
    "asset_depreciation_entries",
    "maintenance_records",
    "operating_supplies",
    "financial_trace_log",
})


class IdempotencyService:
    """Servicio de idempotencia para escrituras financieras."""

    def __init__(self, db):
        from core.db.connection import wrap
        self._db = wrap(db)

    # ── Verificación ──────────────────────────────────────────────────────────

    def exists(self, operation_id: str, table: str) -> bool:
        """Retorna True si operation_id ya existe en la tabla indicada."""
        if table not in _SUPPORTED_TABLES:
            logger.warning("IdempotencyService.exists: tabla no soportada '%s'", table)
            return False
        if not operation_id:
            return False
        try:
            row = self._db.fetchone(
                f"SELECT 1 FROM {table} WHERE operation_id = ? LIMIT 1",
                (operation_id,),
            )
            return row is not None
        except Exception as exc:
            logger.debug("IdempotencyService.exists(%s, %s): %s", operation_id, table, exc)
            return False

    def get_existing_id(self, operation_id: str, table: str) -> int:
        """Retorna el id del registro con ese operation_id, o 0 si no existe."""
        if table not in _SUPPORTED_TABLES:
            return 0
        if not operation_id:
            return 0
        try:
            row = self._db.fetchone(
                f"SELECT id FROM {table} WHERE operation_id = ? LIMIT 1",
                (operation_id,),
            )
            return int(row["id"]) if row else 0
        except Exception:
            return 0

    # ── Generación de operation_id ────────────────────────────────────────────

    @staticmethod
    def generate(source_module: str, source_id, event_type: str) -> str:
        """
        Genera un operation_id canónico reproducible.

        Formato: "{source_module}-{source_id}-{event_type}"
        Ejemplos:
          "ventas-1234-VENTA_CONTADO"
          "compras-456-COMPRA_CREDITO"
          "activos-7-DEP-2026-05"

        Si source_id es None, se usa "0".
        """
        sid = str(source_id) if source_id is not None else "0"
        return f"{source_module}-{sid}-{event_type}"

    @staticmethod
    def generate_hash(source_module: str, source_id, event_type: str,
                      extra: str = "") -> str:
        """
        Genera operation_id con hash SHA-256 truncado (para casos con datos extra).
        Útil cuando el event_type + extra puede colisionar (ej: depreciaciones de mismo activo).
        """
        raw = f"{source_module}:{source_id}:{event_type}:{extra}"
        h = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{source_module}-{source_id}-{event_type}-{h}"
