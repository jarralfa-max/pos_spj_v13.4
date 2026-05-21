# core/services/finance/journal_entry_service.py — SPJ ERP v13.4
"""
JournalEntryService — asientos contables idempotentes (nueva tabla canonical).

Opera sobre la tabla `journal_entries` (creada en migración 083).
Coexiste con GeneralLedgerService / financial_event_log (legacy) — no los reemplaza.

Diferencia clave vs GeneralLedgerService:
  - journal_entries tiene operation_id UNIQUE → idempotencia garantizada.
  - GeneralLedgerService.registrar_asiento() escribe en financial_event_log (sin op_id único).
  - Este servicio escribe en journal_entries Y opcionalmente delega al GL legacy.

Reglas:
  - post_entry() NO hace commit — el caller decide cuándo confirmar.
  - Si operation_id ya existe, retorna el id existente sin error (idempotente).
  - post_reversal() crea un asiento reversal con cuentas invertidas y sufijo "-REV".
"""
from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("spj.finance.journal_entry")


class JournalEntryService:
    """Asientos contables idempotentes sobre tabla journal_entries."""

    def __init__(self, db, gl_service=None):
        from core.db.connection import wrap
        self._db = wrap(db)
        self._gl = gl_service  # GeneralLedgerService opcional para dual-write legacy

    # ── Escritura ─────────────────────────────────────────────────────────────

    def post_entry(
        self,
        operation_id: str,
        event_type: str,
        source_module: str,
        debit_account: str,
        credit_account: str,
        amount: float,
        source_id: Optional[int] = None,
        source_folio: str = "",
        branch_id: int = 1,
        user: str = "sistema",
        metadata: Optional[dict] = None,
    ) -> int:
        """
        Registra asiento en journal_entries (idempotente por operation_id).

        Retorna: id del registro (existente o nuevo). 0 si tabla no existe.
        NO hace commit.
        """
        if not operation_id:
            logger.warning("post_entry: operation_id vacío — rechazado")
            return 0
        if amount <= 0:
            logger.warning("post_entry op=%s: amount=%.2f — rechazado", operation_id, amount)
            return 0

        # Idempotencia: si ya existe, retornar id sin error
        try:
            existing = self._db.fetchone(
                "SELECT id FROM journal_entries WHERE operation_id = ?", (operation_id,)
            )
            if existing:
                logger.debug("post_entry: op_id=%s ya existe (id=%s)", operation_id, existing["id"])
                return int(existing["id"])
        except Exception as exc:
            logger.debug("journal_entries no disponible: %s", exc)
            return self._fallback_gl(
                event_type, source_module, source_id, debit_account,
                credit_account, amount, source_folio, branch_id, metadata,
            )

        try:
            cur = self._db.execute(
                """INSERT INTO journal_entries
                       (event_type, source_module, source_id, source_folio,
                        debit_account, credit_account, amount,
                        branch_id, user, operation_id, metadata_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_type, source_module, source_id, source_folio,
                    debit_account, credit_account, float(amount),
                    branch_id, user, operation_id,
                    json.dumps(metadata or {}, ensure_ascii=False, default=str),
                ),
            )
            entry_id = cur.lastrowid or 0
        except Exception as exc:
            logger.warning("post_entry INSERT failed op=%s: %s", operation_id, exc)
            entry_id = 0

        # Dual-write legacy (no-fatal)
        self._fallback_gl(
            event_type, source_module, source_id, debit_account,
            credit_account, amount, source_folio, branch_id, metadata,
        )

        return entry_id

    def post_reversal(
        self,
        original_operation_id: str,
        reason: str = "",
        user: str = "sistema",
    ) -> int:
        """
        Crea asiento reversal (cuentas invertidas) del asiento original.

        El nuevo operation_id es original_operation_id + "-REV".
        Retorna: id del asiento reversal. 0 si el original no existe.
        """
        try:
            orig = self._db.fetchone(
                "SELECT * FROM journal_entries WHERE operation_id = ?",
                (original_operation_id,),
            )
        except Exception:
            return 0

        if not orig:
            logger.warning("post_reversal: original op_id=%s no encontrado", original_operation_id)
            return 0

        rev_op_id = f"{original_operation_id}-REV"
        meta = {"reason": reason, "reversal_of": original_operation_id}

        return self.post_entry(
            operation_id=rev_op_id,
            event_type=f"{orig['event_type']}_REVERSAL",
            source_module=orig["source_module"],
            source_id=orig["source_id"],
            source_folio=orig["source_folio"],
            debit_account=orig["credit_account"],   # invertido
            credit_account=orig["debit_account"],   # invertido
            amount=float(orig["amount"]),
            branch_id=orig["branch_id"],
            user=user,
            metadata=meta,
        )

    # ── Consultas ─────────────────────────────────────────────────────────────

    def get_by_operation_id(self, operation_id: str) -> Optional[Dict]:
        try:
            row = self._db.fetchone(
                "SELECT * FROM journal_entries WHERE operation_id = ?", (operation_id,)
            )
            return dict(row) if row else None
        except Exception:
            return None

    def get_by_source(
        self,
        source_module: str,
        source_id: int,
    ) -> List[Dict]:
        try:
            rows = self._db.fetchall(
                "SELECT * FROM journal_entries WHERE source_module=? AND source_id=?"
                " ORDER BY created_at",
                (source_module, source_id),
            )
            return [dict(r) for r in rows]
        except Exception:
            return []

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _fallback_gl(
        self,
        event_type, source_module, source_id, debit_account,
        credit_account, amount, source_folio, branch_id, metadata,
    ) -> int:
        if self._gl and hasattr(self._gl, "registrar_asiento"):
            try:
                return self._gl.registrar_asiento(
                    debe=debit_account,
                    haber=credit_account,
                    concepto=f"{event_type} {source_folio}".strip(),
                    monto=float(amount),
                    modulo=source_module,
                    referencia_id=source_id,
                    sucursal_id=branch_id,
                    evento=event_type,
                    metadata=metadata or {},
                )
            except Exception as exc:
                logger.debug("GL legacy fallback error: %s", exc)
        return 0
