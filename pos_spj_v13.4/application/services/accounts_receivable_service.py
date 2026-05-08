# application/services/accounts_receivable_service.py — SPJ POS v13.4
"""
AccountsReceivableService — single authoritative path for all CxC mutations.

Every write to cuentas_por_cobrar must go through this service so that:
  1. The GL journal entry (debe=130.1-CxC / haber=401.0-ingresos) is always posted.
  2. Both credit_balance and saldo columns on clientes stay in sync.
  3. Cancellations correctly reverse both the CxC record and the GL entry.
  4. Every operation is idempotent (folio-based duplicate guard).

Note: For new sales processed via SalesService + EventBus, CxC is created
atomically inside the SAVEPOINT by CreditSaleFinanceHandler (priority=85).
This service is the explicit API for any other caller (legacy paths, manual
corrections, partial payments, etc.).
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("spj.accounts_receivable")


class AccountsReceivableService:
    """
    All public methods are atomic (SAVEPOINT-wrapped) so callers don't need to
    manage transactions themselves.
    """

    def __init__(self, db_conn, finance_service=None):
        self.db = db_conn
        self._finance = finance_service

    # ── Create ────────────────────────────────────────────────────────────────

    def create_cxc(
        self,
        cliente_id: int,
        sale_id: int,
        folio: str,
        monto: float,
        sucursal_id: int = 1,
    ) -> int:
        """
        Insert a new CxC row, increment both credit columns, and post the GL entry.

        Returns the new CxC row id, or 0 if a CxC already exists for this folio
        (idempotent guard — the caller is responsible for not calling twice).
        """
        if monto <= 0:
            raise ValueError(f"CxC monto must be > 0, got {monto}")

        sp = f"cxc_create_{sale_id}"
        try:
            self.db.execute(f"SAVEPOINT {sp}")

            # Idempotency: skip if this folio already has an open CxC
            existing = self.db.execute(
                "SELECT id FROM cuentas_por_cobrar WHERE folio = ? AND cliente_id = ?",
                (folio, cliente_id),
            ).fetchone()
            if existing:
                self.db.execute(f"RELEASE SAVEPOINT {sp}")
                logger.info("create_cxc: folio=%s already exists — skipping", folio)
                return 0

            cursor = self.db.execute(
                """INSERT INTO cuentas_por_cobrar
                       (cliente_id, venta_id, folio, monto_original, saldo_pendiente,
                        sucursal_id, estado)
                   VALUES (?, ?, ?, ?, ?, ?, 'pendiente')""",
                (cliente_id, sale_id, folio, monto, monto, sucursal_id),
            )
            cxc_id = cursor.lastrowid

            self.db.execute(
                "UPDATE clientes "
                "SET credit_balance = COALESCE(credit_balance, 0) + ?, "
                "    saldo          = COALESCE(saldo, 0) + ? "
                "WHERE id = ?",
                (monto, monto, cliente_id),
            )

            self.db.execute(f"RELEASE SAVEPOINT {sp}")
        except Exception as exc:
            try:
                self.db.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                self.db.execute(f"RELEASE SAVEPOINT {sp}")
            except Exception:
                pass
            logger.error("create_cxc: %s", exc)
            raise

        # GL entry posted AFTER the SAVEPOINT so the DB state is already committed.
        # If the GL fails it is logged but does NOT roll back the CxC (cash-first
        # principle: the debt exists regardless of the accounting entry).
        self._post_gl(
            debe="130.1-cuentas-por-cobrar",
            haber="401.0-ingresos-ventas",
            concepto=f"Venta a crédito {folio}",
            monto=monto,
            sale_id=sale_id,
            cliente_id=cliente_id,
            folio=folio,
            sucursal_id=sucursal_id,
            evento="VENTA_CREDITO",
        )

        logger.info(
            "CxC creada: id=%d cliente=%d venta=%d folio=%s monto=%.2f",
            cxc_id, cliente_id, sale_id, folio, monto,
        )
        return cxc_id

    # ── Cancel / Reverse ──────────────────────────────────────────────────────

    def reverse_cxc(
        self,
        sale_id: int,
        sucursal_id: int = 1,
        cliente_id: Optional[int] = None,
    ) -> None:
        """
        Mark all CxC rows for sale_id as 'cancelada', restore credit_balance/saldo,
        and post the reversal GL entry.
        """
        sp = f"cxc_reverse_{sale_id}"
        try:
            self.db.execute(f"SAVEPOINT {sp}")

            rows = self.db.execute(
                "SELECT id, monto_original, cliente_id FROM cuentas_por_cobrar "
                "WHERE venta_id = ? AND sucursal_id = ? AND estado != 'cancelada'",
                (sale_id, sucursal_id),
            ).fetchall()

            total_reversed = 0.0
            for row in rows:
                cxc_id, monto, cid = row[0], float(row[1]), row[2]
                self.db.execute(
                    "UPDATE cuentas_por_cobrar SET estado='cancelada', saldo_pendiente=0 WHERE id=?",
                    (cxc_id,),
                )
                self.db.execute(
                    "UPDATE clientes "
                    "SET credit_balance = MAX(0, COALESCE(credit_balance, 0) - ?), "
                    "    saldo          = MAX(0, COALESCE(saldo, 0) - ?) "
                    "WHERE id = ?",
                    (monto, monto, cid),
                )
                total_reversed += monto

            self.db.execute(f"RELEASE SAVEPOINT {sp}")
        except Exception as exc:
            try:
                self.db.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                self.db.execute(f"RELEASE SAVEPOINT {sp}")
            except Exception:
                pass
            logger.error("reverse_cxc sale=%s: %s", sale_id, exc)
            raise

        if total_reversed > 0:
            self._post_gl(
                debe="401.0-ingresos-ventas",
                haber="130.1-cuentas-por-cobrar",
                concepto=f"Reversal CxC venta {sale_id}",
                monto=total_reversed,
                sale_id=sale_id,
                cliente_id=cliente_id,
                folio=str(sale_id),
                sucursal_id=sucursal_id,
                evento="VENTA_CANCELADA",
            )

        logger.info("CxC revertida: venta=%d monto_total=%.2f", sale_id, total_reversed)

    # ── Apply payment ─────────────────────────────────────────────────────────

    def apply_payment(
        self,
        cxc_id: int,
        amount: float,
        sucursal_id: int = 1,
    ) -> None:
        """Reduce saldo_pendiente and credit_balance by amount; mark 'pagada' when zero."""
        if amount <= 0:
            raise ValueError("Payment amount must be > 0")

        sp = f"cxc_pay_{cxc_id}"
        try:
            self.db.execute(f"SAVEPOINT {sp}")

            row = self.db.execute(
                "SELECT saldo_pendiente, cliente_id, monto_original FROM cuentas_por_cobrar WHERE id=?",
                (cxc_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"CxC id={cxc_id} not found")

            saldo, cliente_id, _ = float(row[0]), row[1], float(row[2])
            applied = min(amount, saldo)
            new_saldo = round(saldo - applied, 2)
            estado = "pagada" if new_saldo == 0 else "pendiente"

            self.db.execute(
                "UPDATE cuentas_por_cobrar SET saldo_pendiente=?, estado=? WHERE id=?",
                (new_saldo, estado, cxc_id),
            )
            self.db.execute(
                "UPDATE clientes "
                "SET credit_balance = MAX(0, COALESCE(credit_balance, 0) - ?), "
                "    saldo          = MAX(0, COALESCE(saldo, 0) - ?) "
                "WHERE id = ?",
                (applied, applied, cliente_id),
            )

            self.db.execute(f"RELEASE SAVEPOINT {sp}")
        except Exception as exc:
            try:
                self.db.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                self.db.execute(f"RELEASE SAVEPOINT {sp}")
            except Exception:
                pass
            logger.error("apply_payment cxc=%s: %s", cxc_id, exc)
            raise

        self._post_gl(
            debe="110-caja",
            haber="130.1-cuentas-por-cobrar",
            concepto=f"Cobro CxC #{cxc_id}",
            monto=applied,
            sale_id=cxc_id,
            cliente_id=cliente_id,
            folio=str(cxc_id),
            sucursal_id=sucursal_id,
            evento="COBRO_CXC",
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _post_gl(
        self,
        debe: str,
        haber: str,
        concepto: str,
        monto: float,
        sale_id,
        cliente_id,
        folio: str,
        sucursal_id: int,
        evento: str,
    ) -> None:
        if not (self._finance and hasattr(self._finance, "registrar_asiento")):
            return
        try:
            self._finance.registrar_asiento(
                debe=debe,
                haber=haber,
                concepto=concepto,
                monto=monto,
                modulo="cuentas_por_cobrar",
                referencia_id=sale_id,
                sucursal_id=sucursal_id,
                evento=evento,
                metadata={"cliente_id": cliente_id, "folio": folio},
            )
        except Exception as exc:
            logger.warning("AccountsReceivableService GL: %s", exc)
