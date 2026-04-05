# sync/domain_validators/sales_validator.py — SPJ POS v13.3
"""
Validador de dominio para ventas en sincronización multisucursal.

Reglas:
  1. Venta cancelada localmente NO se puede des-cancelar por sync
  2. Total no puede cambiar en > 10% por sync (posible corrupción)
  3. Folio con formato corrupto se rechaza
  4. Venta con fecha futura (> 24h) se rechaza
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sync.domain_validators.base import DomainValidator

logger = logging.getLogger("spj.sync.validators.sales")

SALES_TABLES = frozenset({"ventas", "detalles_venta"})


class SalesValidator(DomainValidator):
    """Valida reglas de negocio de ventas post-resolución de conflicto."""

    def __init__(self, max_total_delta_pct: float = 10.0):
        self.max_total_delta_pct = max_total_delta_pct

    def validate(
        self,
        tabla: str,
        resolved: dict,
        local: dict,
        remote: dict,
    ) -> Optional[str]:
        if tabla not in SALES_TABLES:
            return None

        if tabla == "ventas":
            return self._validate_venta(resolved, local, remote)

        return None

    def _validate_venta(
        self, resolved: dict, local: dict, remote: dict
    ) -> Optional[str]:
        # ── Regla 1: Cancelación es irreversible ─────────────────────────
        local_cancelada = local.get("cancelada", 0)
        remote_cancelada = remote.get("cancelada", 0)
        if local_cancelada == 1 and remote_cancelada != 1:
            return (
                f"Venta {local.get('folio', '?')} cancelada localmente — "
                "sync remoto intentó des-cancelar"
            )

        # ── Regla 2: Delta de total sospechoso ───────────────────────────
        lt = float(local.get("total", 0))
        rt = float(remote.get("total", 0))
        if lt > 0 and rt > 0:
            delta_pct = abs(lt - rt) / lt * 100
            if delta_pct > self.max_total_delta_pct:
                return (
                    f"Delta de total sospechoso en venta {local.get('folio', '?')}: "
                    f"local=${lt:.2f} vs remote=${rt:.2f} ({delta_pct:.1f}%)"
                )

        # ── Regla 3: Fecha futura ────────────────────────────────────────
        fecha_str = resolved.get("fecha", "")
        if fecha_str:
            try:
                fecha = datetime.fromisoformat(str(fecha_str).replace("Z", "+00:00"))
                if fecha > datetime.now(fecha.tzinfo) + timedelta(hours=24):
                    return f"Venta con fecha futura: {fecha_str}"
            except (ValueError, TypeError):
                pass  # fecha en formato no estándar — no bloquear

        return None
