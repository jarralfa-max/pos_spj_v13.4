# core/services/finance/operating_supplies_service.py — SPJ ERP v13.4
"""
OperatingSuppliesService — insumos operativos idempotentes.

Opera sobre `operating_supplies` (migración 083).

Tipos de insumo:
  thermal_rolls   — rollos térmicos (gasto al comprar, NO por ticket impreso)
  labels          — etiquetas
  cleaning        — artículos de limpieza
  stationery      — papelería
  bags            — bolsas
  packaging       — empaques
  uniforms        — uniformes (gasto o minor_asset según monto)
  small_tools     — herramientas menores
  other           — otros

Política de rollos térmicos:
  - Registrar como gasto/insumo al COMPRAR, NO al imprimir ticket.
  - No calcular costo por ticket individual en esta fase.

Cuentas contables por tipo:
  thermal_rolls / labels / stationery → 630-papeleria_expense
  cleaning → 625-limpieza_expense
  bags / packaging → 615-empaque_expense (o costo_venta si se requiere margen fino)
  uniforms → 640-uniformes_expense
  small_tools → 645-herramientas_menores_expense
  other → 690-otros_gastos
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Optional

logger = logging.getLogger("spj.finance.operating_supplies")

_SUPPLY_ACCOUNT = {
    "thermal_rolls": "630-papeleria_expense",
    "labels":        "630-papeleria_expense",
    "stationery":    "630-papeleria_expense",
    "cleaning":      "625-limpieza_expense",
    "bags":          "615-empaque_expense",
    "packaging":     "615-empaque_expense",
    "uniforms":      "640-uniformes_expense",
    "small_tools":   "645-herramientas_menores_expense",
    "other":         "690-otros_gastos",
}


def _expense_account(supply_type: str) -> str:
    return _SUPPLY_ACCOUNT.get(supply_type, "690-otros_gastos")


class OperatingSuppliesService:
    """Insumos operativos con trazabilidad financiera completa."""

    def __init__(self, db, journal_service=None, document_service=None,
                 treasury_service=None):
        from core.db.connection import wrap
        self._db = wrap(db)
        self._je = journal_service
        self._fd = document_service
        self._tm = treasury_service

    # ── Registro ──────────────────────────────────────────────────────────────

    def register_supply_purchase(
        self,
        operation_id: str,
        supply_type: str,
        total_amount: float,
        description: str = "",
        quantity: float = 1.0,
        unit_cost: Optional[float] = None,
        supplier_id: Optional[int] = None,
        source_module: str = "compras",
        source_id: Optional[int] = None,
        source_folio: str = "",
        payment_method: Optional[str] = None,
        branch_id: int = 1,
        user: str = "sistema",
        metadata: Optional[dict] = None,
    ) -> Dict:
        """
        Registra compra de insumo operativo.

        Si payment_method dado: contado → treasury outflow.
        Si payment_method None: crédito → financial document payable.

        Retorna: {supply_id, document_id, movement_id, journal_id}
        """
        result = {
            "supply_id": 0, "document_id": 0,
            "movement_id": 0, "journal_id": 0,
        }
        if not operation_id or total_amount <= 0:
            return result

        # Idempotencia
        try:
            existing = self._db.fetchone(
                "SELECT id FROM operating_supplies WHERE operation_id=?", (operation_id,)
            )
            if existing:
                result["supply_id"] = int(existing["id"])
                return result
        except Exception as exc:
            logger.debug("operating_supplies no disponible: %s", exc)
            return result

        uc = unit_cost if unit_cost is not None else (total_amount / max(quantity, 1))
        paid_now = payment_method is not None

        # Documento si queda pendiente
        doc_id = 0
        if not paid_now and self._fd:
            doc_id = self._fd.create_payable(
                operation_id=f"{operation_id}-FD",
                source_module=source_module,
                source_id=source_id,
                amount=total_amount,
                party_type="supplier",
                party_id=supplier_id,
                source_folio=source_folio,
                branch_id=branch_id,
                user=user,
                metadata=metadata,
            )
        result["document_id"] = doc_id

        # Movimiento si se pagó
        mov_id = 0
        if paid_now and self._tm:
            mov_id = self._tm.register_outflow(
                operation_id=f"{operation_id}-TM",
                amount=total_amount,
                payment_method=payment_method,
                source_module=source_module,
                source_id=source_id,
                source_folio=source_folio,
                branch_id=branch_id,
                user=user,
                metadata=metadata,
            )
        result["movement_id"] = mov_id

        # Asiento contable
        if self._je:
            debit  = _expense_account(supply_type)
            credit = "110-caja" if paid_now else "210-cuentas_por_pagar"
            je_id = self._je.post_entry(
                operation_id=f"{operation_id}-JE",
                event_type="OPERATING_SUPPLY_PURCHASED",
                source_module=source_module,
                source_id=source_id,
                source_folio=source_folio,
                debit_account=debit,
                credit_account=credit,
                amount=total_amount,
                branch_id=branch_id,
                user=user,
                metadata={"supply_type": supply_type, **(metadata or {})},
            )
            result["journal_id"] = je_id

        # Insertar operating_supply
        try:
            cur = self._db.execute(
                """INSERT INTO operating_supplies
                       (supply_type, description, quantity, unit_cost, total_amount,
                        status, supplier_id, branch_id, source_module, source_id,
                        source_folio, financial_document_id, treasury_movement_id,
                        journal_entry_id, operation_id, metadata_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    supply_type, description, float(quantity), float(uc), float(total_amount),
                    "paid" if paid_now else "pending",
                    supplier_id, branch_id, source_module, source_id, source_folio,
                    doc_id or None, mov_id or None, result["journal_id"] or None,
                    operation_id,
                    json.dumps(metadata or {}, ensure_ascii=False, default=str),
                ),
            )
            result["supply_id"] = cur.lastrowid or 0
        except Exception as exc:
            logger.warning("operating_supplies INSERT op=%s: %s", operation_id, exc)

        return result

    def pay_supply_purchase(
        self,
        supply_id: int,
        amount: float,
        payment_method: str = "efectivo",
        user: str = "sistema",
    ) -> Dict:
        """Registra pago de insumo pendiente."""
        result = {"movement_id": 0, "journal_id": 0, "nuevo_status": "pending"}
        try:
            row = self._db.fetchone(
                "SELECT * FROM operating_supplies WHERE id=?", (supply_id,)
            )
            if not row or row["status"] == "paid":
                return result

            op_id = f"{row['operation_id']}-PAY"

            if self._tm:
                result["movement_id"] = self._tm.register_outflow(
                    operation_id=f"{op_id}-TM",
                    amount=amount,
                    payment_method=payment_method,
                    source_module=row["source_module"],
                    source_id=row["source_id"],
                    branch_id=row["branch_id"],
                    user=user,
                )

            if self._je:
                result["journal_id"] = self._je.post_entry(
                    operation_id=f"{op_id}-JE",
                    event_type="OPERATING_SUPPLY_PAID",
                    source_module=row["source_module"],
                    source_id=row["source_id"],
                    debit_account="210-cuentas_por_pagar",
                    credit_account="110-caja",
                    amount=amount,
                    branch_id=row["branch_id"],
                    user=user,
                )

            self._db.execute(
                "UPDATE operating_supplies SET status='paid' WHERE id=?", (supply_id,)
            )
            result["nuevo_status"] = "paid"
        except Exception as exc:
            logger.warning("pay_supply_purchase id=%s: %s", supply_id, exc)

        return result

    @staticmethod
    def classify_supply(supply_type: str) -> str:
        """Retorna la cuenta contable de gasto para el tipo de insumo."""
        return _expense_account(supply_type)
