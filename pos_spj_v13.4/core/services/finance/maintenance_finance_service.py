# core/services/finance/maintenance_finance_service.py — SPJ ERP v13.4
"""
MaintenanceFinanceService — trazabilidad financiera de mantenimientos.

Opera sobre `maintenance_records` (migración 083).

Tipos: preventive | corrective | repair | parts | labor

Flujos:
  Pagado contado:
    maintenance_record + treasury_outflow + journal(debe=mant_expense/haber=caja)
  Pendiente de pago:
    maintenance_record + financial_document(payable) + journal(debe=mant_expense/haber=cxp)
    → al pagar: treasury_outflow + journal(debe=cxp/haber=caja) + update FD

  Capitalizable (mejora significativa del activo):
    maintenance_record.capitalizable=True
    journal(debe=activo_fijo/haber=caja_o_cxp)
    update fixed_asset.current_value += amount
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Optional

logger = logging.getLogger("spj.finance.maintenance")


class MaintenanceFinanceService:
    """Trazabilidad financiera de mantenimientos."""

    def __init__(self, db, journal_service=None, document_service=None,
                 treasury_service=None, asset_service=None):
        from core.db.connection import wrap
        self._db  = wrap(db)
        self._je  = journal_service
        self._fd  = document_service
        self._tm  = treasury_service
        self._fa  = asset_service

    # ── Registro ──────────────────────────────────────────────────────────────

    def register_maintenance(
        self,
        operation_id: str,
        amount: float,
        maintenance_type: str = "corrective",
        description: str = "",
        asset_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        source_module: str = "mantenimiento",
        source_id: Optional[int] = None,
        source_folio: str = "",
        payment_method: Optional[str] = None,
        is_capitalizable: bool = False,
        branch_id: int = 1,
        user: str = "sistema",
        metadata: Optional[dict] = None,
    ) -> Dict:
        """
        Registra mantenimiento y genera trazabilidad financiera.

        Si payment_method está dado: pago contado → treasury outflow.
        Si payment_method es None: pendiente → financial document payable.

        Retorna: {maintenance_id, document_id, movement_id, journal_id}
        """
        result = {
            "maintenance_id": 0, "document_id": 0,
            "movement_id": 0, "journal_id": 0,
        }
        if not operation_id or amount <= 0:
            return result

        # Idempotencia
        try:
            existing = self._db.fetchone(
                "SELECT id FROM maintenance_records WHERE operation_id=?", (operation_id,)
            )
            if existing:
                result["maintenance_id"] = existing["id"]  # UUIDv7 (sin cast)
                return result
        except Exception as exc:
            logger.debug("maintenance_records no disponible: %s", exc)
            return result

        paid_now = payment_method is not None

        # Documento financiero si queda pendiente
        doc_id = 0
        if not paid_now and self._fd:
            doc_id = self._fd.create_payable(
                operation_id=f"{operation_id}-FD",
                source_module=source_module,
                source_id=source_id,
                amount=amount,
                party_type="supplier",
                party_id=supplier_id,
                source_folio=source_folio,
                branch_id=branch_id,
                user=user,
                metadata=metadata,
            )
        result["document_id"] = doc_id

        # Movimiento de tesorería si se pagó ahora
        mov_id = 0
        if paid_now and self._tm:
            mov_id = self._tm.register_outflow(
                operation_id=f"{operation_id}-TM",
                amount=amount,
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
            if is_capitalizable:
                debit  = "150-activos_fijos"
                credit = "110-caja" if paid_now else "210-cuentas_por_pagar"
                evt    = "MAINTENANCE_CAPITALIZED"
            else:
                debit  = "620-mantenimiento_expense"
                credit = "110-caja" if paid_now else "210-cuentas_por_pagar"
                evt    = "MAINTENANCE_REGISTERED"
            je_id = self._je.post_entry(
                operation_id=f"{operation_id}-JE",
                event_type=evt,
                source_module=source_module,
                source_id=source_id,
                source_folio=source_folio,
                debit_account=debit,
                credit_account=credit,
                amount=amount,
                branch_id=branch_id,
                user=user,
                metadata=metadata,
            )
            result["journal_id"] = je_id

        # Insertar maintenance_record
        try:
            from backend.shared.ids import new_uuid
            maintenance_id = new_uuid()  # identidad UUIDv7 explícita (REGLA CERO)
            self._db.execute(
                """INSERT INTO maintenance_records
                       (id, asset_id, maintenance_type, description, amount,
                        status, supplier_id, branch_id, source_module, source_id,
                        source_folio, financial_document_id, treasury_movement_id,
                        journal_entry_id, capitalizable, operation_id, metadata_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    maintenance_id,
                    asset_id, maintenance_type, description, float(amount),
                    "paid" if paid_now else "pending",
                    supplier_id, branch_id, source_module, source_id, source_folio,
                    doc_id or None, mov_id or None, result["journal_id"] or None,
                    1 if is_capitalizable else 0,
                    operation_id,
                    json.dumps(metadata or {}, ensure_ascii=False, default=str),
                ),
            )
            result["maintenance_id"] = maintenance_id
        except Exception as exc:
            logger.warning("maintenance_records INSERT op=%s: %s", operation_id, exc)

        # Si capitalizable, actualizar fixed_asset
        if is_capitalizable and asset_id and self._fa and result["maintenance_id"]:
            try:
                self._db.execute(
                    "UPDATE fixed_assets SET current_value = current_value + ?,"
                    " updated_at=datetime('now') WHERE id=?",
                    (amount, asset_id),
                )
            except Exception:
                pass

        return result

    def pay_maintenance(
        self,
        maintenance_id: int,
        amount: float,
        payment_method: str = "efectivo",
        user: str = "sistema",
    ) -> Dict:
        """
        Registra pago de mantenimiento pendiente.

        Retorna: {movement_id, journal_id, nuevo_status}
        """
        result = {"movement_id": 0, "journal_id": 0, "nuevo_status": "pending"}
        try:
            row = self._db.fetchone(
                "SELECT * FROM maintenance_records WHERE id=?", (maintenance_id,)
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
                    source_folio=row["source_folio"],
                    branch_id=row["branch_id"],
                    user=user,
                )

            if self._je:
                result["journal_id"] = self._je.post_entry(
                    operation_id=f"{op_id}-JE",
                    event_type="MAINTENANCE_PAID",
                    source_module=row["source_module"],
                    source_id=row["source_id"],
                    debit_account="210-cuentas_por_pagar",
                    credit_account="110-caja",
                    amount=amount,
                    branch_id=row["branch_id"],
                    user=user,
                )

            self._db.execute(
                "UPDATE maintenance_records SET status='paid', updated_at=datetime('now')"
                " WHERE id=?",
                (maintenance_id,),
            )
            result["nuevo_status"] = "paid"
        except Exception as exc:
            logger.warning("pay_maintenance id=%s: %s", maintenance_id, exc)

        return result

    def cancel_maintenance(self, maintenance_id: int, user: str = "sistema") -> bool:
        """Cancela mantenimiento y reversa asiento si existe."""
        try:
            row = self._db.fetchone(
                "SELECT operation_id FROM maintenance_records WHERE id=?", (maintenance_id,)
            )
            if not row:
                return False
            if self._je:
                self._je.post_reversal(f"{row['operation_id']}-JE", reason="cancelado", user=user)
            self._db.execute(
                "UPDATE maintenance_records SET status='cancelled', updated_at=datetime('now')"
                " WHERE id=?",
                (maintenance_id,),
            )
            return True
        except Exception as exc:
            logger.warning("cancel_maintenance id=%s: %s", maintenance_id, exc)
            return False
