# core/events/handlers/cash_cut_capital_handler.py — SPJ ERP v13.4
"""
CashCutCapitalHandler — consolida el efectivo del turno hacia tesorería/capital.

Bug 10: "El corte de caja debe incrementar el capital disponible".

Al cerrar el turno (CASH_Z_CUT_GENERATED), el efectivo de ventas del turno se
consolida como una entrada CONFIRMADA de tesorería (treasury_movements) vía la
fachada unificada TreasuryService.register_inflow. Esto:

  - refleja el corte en tesorería y en los KPIs financieros;
  - hace pasar la reconciliación (ReconciliationService espera un
    treasury_movement por el efectivo del turno);
  - es idempotente por el id del corte (no duplica al reintentar el evento).

No registra en treasury_ledger (eso ya lo hace el handler de venta por cada
venta) — evita doble conteo. Post-commit, no bloquea el corte si falla.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("spj.handlers.cash_cut_capital")


class CashCutCapitalHandler:
    """Consolida el efectivo del corte Z como movimiento de tesorería confirmado."""

    def __init__(self, treasury_service: Any) -> None:
        self._treasury = treasury_service

    @staticmethod
    def _cash_consolidated(payload: Dict[str, Any]) -> float:
        """Efectivo real del turno a consolidar en capital.

        Prioriza `ventas_efectivo` (dinero nuevo del turno). Si no viene, usa
        el efectivo esperado menos el fondo inicial (que rota al siguiente turno).
        """
        ventas_efectivo = payload.get("ventas_efectivo")
        if ventas_efectivo is not None:
            return round(float(ventas_efectivo or 0.0), 2)
        esperado = float(payload.get("efectivo_esperado", 0.0) or 0.0)
        fondo = float(payload.get("fondo_inicial", 0.0) or 0.0)
        return round(max(esperado - fondo, 0.0), 2)

    def handle(self, payload: Optional[Dict[str, Any]]) -> None:
        payload = payload or {}
        if self._treasury is None or not hasattr(self._treasury, "register_inflow"):
            return

        monto = self._cash_consolidated(payload)
        if monto <= 0:
            return

        cut_ref = str(
            payload.get("cut_id")
            or payload.get("cierre_id")
            or payload.get("operation_id")
            or payload.get("turno_id")
            or ""
        )
        if not cut_ref:
            logger.warning("CashCutCapitalHandler: corte sin identificador — omitido")
            return

        try:
            self._treasury.register_inflow(
                operation_id=f"{cut_ref}:capital",  # idempotente por corte
                amount=monto,
                payment_method="efectivo",
                source_module="caja",
                source_folio=str(payload.get("turno_id", "")),
                branch_id=str(payload.get("branch_id") or payload.get("sucursal_id") or ""),
                user=str(payload.get("user") or payload.get("usuario") or "sistema"),
                metadata={
                    "event": "cash_z_cut",
                    "efectivo_esperado": payload.get("efectivo_esperado"),
                    "efectivo_contado": payload.get("efectivo_contado"),
                },
            )
            logger.info(
                "Corte Z consolidado a capital: corte=%s monto=%.2f", cut_ref, monto
            )
        except Exception as exc:  # post-commit: no cancela el corte ya registrado
            logger.warning("CashCutCapitalHandler: %s", exc)
