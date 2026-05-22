# core/services/finance/financial_document_service.py — SPJ ERP v13.4
"""
FinancialDocumentService — documentos financieros idempotentes.

Opera sobre la tabla `financial_documents` (migración 083).
Coexiste con AccountsPayableService / AccountsReceivableService (legacy).

Tipos de documentos:
  receivable  — derecho de cobro (CxC)
  payable     — obligación de pago (CxP)
  payroll     — nómina por pagar
  maintenance — mantenimiento pendiente
  asset       — activo pendiente de pago

Reglas:
  - create_*() NO hace commit — el caller decide.
  - Si operation_id ya existe, retorna el id existente (idempotente).
  - apply_collection / apply_payment actualizan balance + status.
  - cancel_document marca status='cancelled' y balance=0.
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Optional

logger = logging.getLogger("spj.finance.financial_document")

_STATUS_PENDING    = "pending"
_STATUS_PARTIAL    = "partial"
_STATUS_PAID       = "paid"
_STATUS_CANCELLED  = "cancelled"


class FinancialDocumentService:
    """Documentos financieros idempotentes (CxC, CxP, nómina, activos)."""

    def __init__(self, db):
        from core.db.connection import wrap
        self._db = wrap(db)

    # ── Creación de documentos ────────────────────────────────────────────────

    def create_receivable(
        self,
        operation_id: str,
        source_module: str,
        source_id: Optional[int],
        amount: float,
        party_id: Optional[int] = None,
        source_folio: str = "",
        due_date: Optional[str] = None,
        branch_id: int = 1,
        user: str = "sistema",
        metadata: Optional[dict] = None,
    ) -> int:
        """Crea CxC en financial_documents (idempotente)."""
        return self._create_document(
            document_type="receivable",
            operation_id=operation_id,
            source_module=source_module,
            source_id=source_id,
            amount=amount,
            party_type="customer",
            party_id=party_id,
            source_folio=source_folio,
            due_date=due_date,
            branch_id=branch_id,
            user=user,
            metadata=metadata,
        )

    def create_payable(
        self,
        operation_id: str,
        source_module: str,
        source_id: Optional[int],
        amount: float,
        party_id: Optional[int] = None,
        party_type: str = "supplier",
        source_folio: str = "",
        due_date: Optional[str] = None,
        branch_id: int = 1,
        user: str = "sistema",
        metadata: Optional[dict] = None,
    ) -> int:
        """Crea CxP en financial_documents (idempotente)."""
        return self._create_document(
            document_type="payable",
            operation_id=operation_id,
            source_module=source_module,
            source_id=source_id,
            amount=amount,
            party_type=party_type,
            party_id=party_id,
            source_folio=source_folio,
            due_date=due_date,
            branch_id=branch_id,
            user=user,
            metadata=metadata,
        )

    def create_payroll_payable(
        self,
        operation_id: str,
        source_id: Optional[int],
        amount: float,
        party_id: Optional[int] = None,
        source_folio: str = "",
        branch_id: int = 1,
        user: str = "sistema",
        metadata: Optional[dict] = None,
    ) -> int:
        """Crea obligación de nómina en financial_documents."""
        return self._create_document(
            document_type="payroll",
            operation_id=operation_id,
            source_module="nomina",
            source_id=source_id,
            amount=amount,
            party_type="employee",
            party_id=party_id,
            source_folio=source_folio,
            branch_id=branch_id,
            user=user,
            metadata=metadata,
        )

    # ── Cobros / Pagos ────────────────────────────────────────────────────────

    def apply_collection(
        self,
        document_id: int,
        amount: float,
        user: str = "sistema",
    ) -> Dict:
        """
        Aplica cobro a un receivable. Actualiza balance y status.

        Retorna: {nuevo_balance, nuevo_status}
        """
        return self._apply_movement(document_id, amount, user, "receivable")

    def apply_payment(
        self,
        document_id: int,
        amount: float,
        user: str = "sistema",
    ) -> Dict:
        """
        Aplica pago a un payable/payroll. Actualiza balance y status.

        Retorna: {nuevo_balance, nuevo_status}
        """
        return self._apply_movement(document_id, amount, user, "payable")

    def cancel_document(self, document_id: int, user: str = "sistema") -> bool:
        """Cancela un documento (balance=0, status=cancelled)."""
        try:
            self._db.execute(
                """UPDATE financial_documents
                   SET status=?, balance=0, updated_at=datetime('now')
                   WHERE id=?""",
                (_STATUS_CANCELLED, document_id),
            )
            return True
        except Exception as exc:
            logger.warning("cancel_document id=%s: %s", document_id, exc)
            return False

    # ── Consultas ─────────────────────────────────────────────────────────────

    def get_balance(self, document_id: int) -> float:
        try:
            row = self._db.fetchone(
                "SELECT balance FROM financial_documents WHERE id=?", (document_id,)
            )
            return float(row["balance"]) if row else 0.0
        except Exception:
            return 0.0

    def get_by_operation_id(self, operation_id: str) -> Optional[Dict]:
        try:
            row = self._db.fetchone(
                "SELECT * FROM financial_documents WHERE operation_id=?", (operation_id,)
            )
            return dict(row) if row else None
        except Exception:
            return None

    def get_by_source(self, source_module: str, source_id: int) -> Optional[Dict]:
        try:
            row = self._db.fetchone(
                "SELECT * FROM financial_documents WHERE source_module=? AND source_id=?",
                (source_module, source_id),
            )
            return dict(row) if row else None
        except Exception:
            return None

    # ── Internos ──────────────────────────────────────────────────────────────

    def _create_document(
        self,
        document_type: str,
        operation_id: str,
        source_module: str,
        source_id: Optional[int],
        amount: float,
        party_type: str = "",
        party_id: Optional[int] = None,
        source_folio: str = "",
        due_date: Optional[str] = None,
        branch_id: int = 1,
        user: str = "sistema",
        metadata: Optional[dict] = None,
    ) -> int:
        if not operation_id:
            logger.warning("_create_document: operation_id vacío")
            return 0
        if amount <= 0:
            logger.warning("_create_document op=%s: amount=%.2f inválido", operation_id, amount)
            return 0

        try:
            existing = self._db.fetchone(
                "SELECT id FROM financial_documents WHERE operation_id=?", (operation_id,)
            )
            if existing:
                logger.debug("financial_documents: op_id=%s ya existe", operation_id)
                return int(existing["id"])
        except Exception as exc:
            logger.debug("financial_documents no disponible: %s", exc)
            return 0

        try:
            cur = self._db.execute(
                """INSERT INTO financial_documents
                       (document_type, status, source_module, source_id, source_folio,
                        party_type, party_id, original_amount, balance,
                        due_date, branch_id, user, operation_id, metadata_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    document_type, _STATUS_PENDING,
                    source_module, source_id, source_folio,
                    party_type, party_id,
                    float(amount), float(amount),
                    due_date, branch_id, user, operation_id,
                    json.dumps(metadata or {}, ensure_ascii=False, default=str),
                ),
            )
            return cur.lastrowid or 0
        except Exception as exc:
            logger.warning("_create_document INSERT op=%s: %s", operation_id, exc)
            return 0

    def _apply_movement(
        self, document_id: int, amount: float, user: str, doc_type: str
    ) -> Dict:
        try:
            row = self._db.fetchone(
                "SELECT balance, original_amount FROM financial_documents WHERE id=?",
                (document_id,),
            )
            if not row:
                raise ValueError(f"Documento {document_id} no encontrado")
            balance = float(row["balance"])
            applied = min(float(amount), balance)
            new_balance = round(balance - applied, 2)
            new_status = _STATUS_PAID if new_balance <= 0 else _STATUS_PARTIAL
            self._db.execute(
                "UPDATE financial_documents SET balance=?, status=?, updated_at=datetime('now')"
                " WHERE id=?",
                (new_balance, new_status, document_id),
            )
            return {"nuevo_balance": new_balance, "nuevo_status": new_status}
        except Exception as exc:
            logger.warning("_apply_movement doc=%s: %s", document_id, exc)
            return {"nuevo_balance": 0.0, "nuevo_status": "error"}
