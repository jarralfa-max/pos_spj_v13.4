# core/services/finance/treasury_movement_service.py — SPJ ERP v13.4
"""
TreasuryMovementService — movimientos reales de dinero idempotentes.

Opera sobre la tabla `treasury_movements` (migración 083) — fuente única de
movimientos de dinero confirmados. Sin escritura dual a treasury_ledger.

Tipos:
  inflow  — dinero entrante confirmado (venta contado, cobro CxC, MercadoPago webhook)
  outflow — dinero saliente confirmado (pago proveedor, nómina, gasto, activo)

Reglas:
  - register_inflow / register_outflow NO hacen commit — el caller decide.
  - Si operation_id ya existe, retorna el id existente (idempotente).
  - confirm_movement cambia status a 'confirmed'.
  - cancel_movement cambia status a 'cancelled'.
  - MercadoPago pending NO se registra aquí — solo cuando el webhook confirma.
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Optional

logger = logging.getLogger("spj.finance.treasury_movement")

_PAYMENT_ACCOUNT_MAP = {
    "efectivo":      "110-caja",
    "Efectivo":      "110-caja",
    "tarjeta":       "112-banco",
    "Tarjeta":       "112-banco",
    "transferencia": "112-banco",
    "Transferencia": "112-banco",
    "Mercado Pago":  "114-pasarela-mp",
    "mercado_pago":  "114-pasarela-mp",
    "delivery":      "115-caja-delivery",
    "cheque":        "112-banco",
    "Cheque":        "112-banco",
}


def _account_for_payment(payment_method: str) -> str:
    return _PAYMENT_ACCOUNT_MAP.get(payment_method, "110-caja")


class TreasuryMovementService:
    """Movimientos de tesorería confirmados e idempotentes."""

    def __init__(self, db):
        from core.db.connection import wrap
        self._db = wrap(db)

    # ── Entradas ──────────────────────────────────────────────────────────────

    def register_inflow(
        self,
        operation_id: str,
        amount: float,
        payment_method: str,
        source_module: str,
        source_id: Optional[str] = None,
        source_folio: str = "",
        financial_document_id: Optional[str] = None,
        branch_id: str = "",
        user: str = "sistema",
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Registra entrada de dinero confirmada.

        NO registrar si el pago no fue confirmado (ej: link MercadoPago pendiente).
        Retorna: id del movimiento (idempotente por operation_id).
        """
        return self._register(
            movement_type="inflow",
            direction="in",
            operation_id=operation_id,
            amount=amount,
            payment_method=payment_method,
            source_module=source_module,
            source_id=source_id,
            source_folio=source_folio,
            financial_document_id=financial_document_id,
            branch_id=branch_id,
            user=user,
            metadata=metadata,
        )

    def register_outflow(
        self,
        operation_id: str,
        amount: float,
        payment_method: str,
        source_module: str,
        source_id: Optional[str] = None,
        source_folio: str = "",
        financial_document_id: Optional[str] = None,
        branch_id: str = "",
        user: str = "sistema",
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Registra salida de dinero confirmada (pago, gasto, nómina, activo).

        Retorna: id del movimiento (idempotente por operation_id).
        """
        return self._register(
            movement_type="outflow",
            direction="out",
            operation_id=operation_id,
            amount=amount,
            payment_method=payment_method,
            source_module=source_module,
            source_id=source_id,
            source_folio=source_folio,
            financial_document_id=financial_document_id,
            branch_id=branch_id,
            user=user,
            metadata=metadata,
        )

    # ── Estado ────────────────────────────────────────────────────────────────

    def confirm_movement(self, movement_id: str) -> bool:
        """Marca un movimiento como confirmed."""
        try:
            self._db.execute(
                "UPDATE treasury_movements SET status='confirmed' WHERE id=?",
                (movement_id,),
            )
            return True
        except Exception as exc:
            logger.warning("confirm_movement id=%s: %s", movement_id, exc)
            return False

    def cancel_movement(self, movement_id: str, reason: str = "") -> bool:
        """Marca un movimiento como cancelled."""
        try:
            self._db.execute(
                "UPDATE treasury_movements SET status='cancelled' WHERE id=?",
                (movement_id,),
            )
            return True
        except Exception as exc:
            logger.warning("cancel_movement id=%s: %s", movement_id, exc)
            return False

    # ── Consultas ─────────────────────────────────────────────────────────────

    def get_by_operation_id(self, operation_id: str) -> Optional[Dict]:
        try:
            row = self._db.fetchone(
                "SELECT * FROM treasury_movements WHERE operation_id=?", (operation_id,)
            )
            return dict(row) if row else None
        except Exception:
            return None

    # ── Interno ───────────────────────────────────────────────────────────────

    def _register(
        self,
        movement_type: str,
        direction: str,
        operation_id: str,
        amount: float,
        payment_method: str,
        source_module: str,
        source_id: Optional[str],
        source_folio: str,
        financial_document_id: Optional[str],
        branch_id: str,
        user: str,
        metadata: Optional[dict],
    ) -> str:
        """Inserta el movimiento (idempotente por operation_id). Devuelve su id
        UUIDv7, o "" si se rechaza/falla (el fallo queda en log, nunca se
        desvía a otra tabla)."""
        if not operation_id:
            logger.warning("treasury_movement: operation_id vacío — rechazado")
            return ""
        if amount <= 0:
            logger.warning("treasury_movement op=%s: amount=%.2f inválido", operation_id, amount)
            return ""

        try:
            existing = self._db.fetchone(
                "SELECT id FROM treasury_movements WHERE operation_id=?", (operation_id,)
            )
            if existing:
                logger.debug("treasury_movements: op_id=%s ya existe", operation_id)
                return str(existing["id"])

            from backend.shared.ids import new_uuid
            movement_id = new_uuid()  # identidad UUIDv7 explícita (REGLA CERO)
            self._db.execute(
                """INSERT INTO treasury_movements
                       (id, movement_type, direction, amount, payment_method, account,
                        status, source_module, source_id, source_folio,
                        financial_document_id, branch_id, user, operation_id, metadata_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    movement_id,
                    movement_type, direction, float(amount), payment_method,
                    _account_for_payment(payment_method),
                    "confirmed",
                    source_module, source_id, source_folio,
                    financial_document_id,
                    str(branch_id or ""), user, operation_id,
                    json.dumps(metadata or {}, ensure_ascii=False, default=str),
                ),
            )
            return movement_id
        except Exception as exc:
            logger.warning("treasury_movements op=%s: %s", operation_id, exc)
            return ""
