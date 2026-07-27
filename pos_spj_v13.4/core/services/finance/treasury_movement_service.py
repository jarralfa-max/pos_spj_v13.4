# core/services/finance/treasury_movement_service.py — SPJ ERP v13.4
"""
TreasuryMovementService — movimientos reales de dinero idempotentes.

Opera sobre la tabla `treasury_movements` (migración 083).
Coexiste con TreasuryService / treasury_ledger (legacy) — no los reemplaza.

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

    def __init__(self, db, treasury_service=None):
        from core.db.connection import wrap
        self._db = wrap(db)
        self._ts = treasury_service  # TreasuryService legacy para dual-write

    # ── Entradas ──────────────────────────────────────────────────────────────

    def register_inflow(
        self,
        operation_id: str,
        amount: float,
        payment_method: str,
        source_module: str,
        source_id: Optional[int] = None,
        source_folio: str = "",
        financial_document_id: Optional[int] = None,
        branch_id: int = 1,
        user: str = "sistema",
        metadata: Optional[dict] = None,
    ) -> int:
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
        source_id: Optional[int] = None,
        source_folio: str = "",
        financial_document_id: Optional[int] = None,
        branch_id: int = 1,
        user: str = "sistema",
        metadata: Optional[dict] = None,
    ) -> int:
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

    def confirm_movement(self, movement_id: int) -> bool:
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

    def cancel_movement(self, movement_id: int, reason: str = "") -> bool:
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
        source_id: Optional[int],
        source_folio: str,
        financial_document_id: Optional[int],
        branch_id: int,
        user: str,
        metadata: Optional[dict],
    ) -> int:
        if not operation_id:
            logger.warning("treasury_movement: operation_id vacío — rechazado")
            return 0
        if amount <= 0:
            logger.warning("treasury_movement op=%s: amount=%.2f inválido", operation_id, amount)
            return 0

        try:
            existing = self._db.fetchone(
                "SELECT id FROM treasury_movements WHERE operation_id=?", (operation_id,)
            )
            if existing:
                logger.debug("treasury_movements: op_id=%s ya existe", operation_id)
                return existing["id"]  # UUIDv7 (sin cast)
        except Exception as exc:
            logger.debug("treasury_movements no disponible: %s", exc)
            return self._fallback_ts(movement_type, amount, payment_method,
                                     source_module, source_folio, branch_id, user)

        account = _account_for_payment(payment_method)
        try:
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
                    movement_type, direction, float(amount), payment_method, account,
                    "confirmed",
                    source_module, source_id, source_folio,
                    financial_document_id,
                    branch_id, user, operation_id,
                    json.dumps(metadata or {}, ensure_ascii=False, default=str),
                ),
            )
        except Exception as exc:
            logger.warning("treasury_movements INSERT op=%s: %s", operation_id, exc)
            movement_id = 0

        # Dual-write legacy (no-fatal)
        self._fallback_ts(movement_type, amount, payment_method,
                          source_module, source_folio, branch_id, user)

        return movement_id

    def _fallback_ts(
        self, movement_type, amount, payment_method, source_module,
        source_folio, branch_id, user
    ) -> int:
        if not self._ts:
            return 0
        try:
            tipo = "ingreso" if movement_type == "inflow" else "egreso"
            categoria = f"{source_module}_trazabilidad"
            method = getattr(self._ts, "registrar_movimiento", None)
            if method:
                method(
                    tipo=tipo,
                    categoria=categoria,
                    concepto=source_folio or source_module,
                    monto=float(amount),
                    sucursal_id=branch_id,
                    usuario=user,
                )
        except Exception as exc:
            logger.debug("TreasuryService fallback error: %s", exc)
        return 0
