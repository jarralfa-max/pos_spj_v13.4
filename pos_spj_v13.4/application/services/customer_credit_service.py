# application/services/customer_credit_service.py — SPJ POS v13.4
"""
CustomerCreditService — validación de clientes y crédito (CxC) en checkout.

Responsabilidades:
- Verificar que el cliente existe antes de completar la venta
- Validar que el cliente tiene crédito suficiente para ventas a crédito
- Registrar la deuda en cuentas_por_cobrar para ventas a crédito

No contiene lógica de UI ni SQL de negocio embebido en capas superiores.
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

logger = logging.getLogger("spj.customer_credit")


class CustomerCreditService:
    """
    Servicio de aplicación para validación de clientes y crédito.
    Inyectable en SalesService sin dependencia de PyQt5 ni GrowthEngine.
    """

    def __init__(self, db_conn, finance_service=None):
        self.db = db_conn
        self._finance = finance_service
        self._ensure_cxc_table()

    # ── API pública ───────────────────────────────────────────────────────────

    def get_customer(self, cliente_id: int) -> Optional[dict]:
        """
        Retorna dict con datos del cliente o None si no existe/está inactivo.
        Claves: id, nombre, activo, credit_limit, credit_balance, puntos
        """
        try:
            row = self.db.execute(
                """SELECT id, nombre, activo,
                          COALESCE(credit_limit, 0.0)   AS credit_limit,
                          COALESCE(credit_balance, 0.0) AS credit_balance,
                          COALESCE(puntos, 0)           AS puntos
                   FROM clientes WHERE id = ? AND activo = 1""",
                (cliente_id,),
            ).fetchone()
        except Exception as e:
            logger.warning("get_customer id=%s: %s", cliente_id, e)
            return None

        if not row:
            return None

        return {
            "id":             row[0],
            "nombre":         row[1],
            "activo":         bool(row[2]),
            "credit_limit":   float(row[3]),
            "credit_balance": float(row[4]),
            "puntos":         int(row[5]),
        }

    def validate_credit(self, cliente_id: int, monto: float) -> Tuple[bool, str]:
        """
        Verifica si el cliente puede comprar a crédito por `monto`.

        Returns:
            (True, "")              — aprobado
            (False, "motivo...")    — rechazado
        """
        customer = self.get_customer(cliente_id)
        if not customer:
            return False, f"Cliente ID {cliente_id} no encontrado o inactivo."

        disponible = customer["credit_limit"] - customer["credit_balance"]
        if disponible < monto:
            return (
                False,
                f"Crédito insuficiente para '{customer['nombre']}': "
                f"disponible ${disponible:,.2f}, requerido ${monto:,.2f}",
            )
        return True, ""

    def register_credit_sale(
        self,
        cliente_id: int,
        sale_id: int,
        folio: str,
        monto: float,
        sucursal_id: int = 1,
    ) -> None:
        """
        Registra la deuda en cuentas_por_cobrar y actualiza credit_balance del cliente.
        Llamado DESPUÉS de que la transacción de venta ha sido confirmada (RELEASE SAVEPOINT).
        """
        try:
            # Registrar en CxC
            self.db.execute(
                """INSERT INTO cuentas_por_cobrar
                       (cliente_id, venta_id, folio, monto_original, saldo_pendiente,
                        sucursal_id, estado)
                   VALUES (?, ?, ?, ?, ?, ?, 'pendiente')""",
                (cliente_id, sale_id, folio, monto, monto, sucursal_id),
            )
            # Incrementar deuda en perfil del cliente
            self.db.execute(
                "UPDATE clientes SET credit_balance = COALESCE(credit_balance, 0) + ? WHERE id = ?",
                (monto, cliente_id),
            )
            try:
                self.db.commit()
            except Exception:
                pass

            # Asiento contable doble entrada (CLAUDE.md regla 11)
            if self._finance and hasattr(self._finance, "registrar_asiento"):
                try:
                    self._finance.registrar_asiento(
                        debe="130.1-cuentas-por-cobrar",
                        haber="401.0-ingresos-ventas",
                        concepto=f"Venta a crédito {folio}",
                        monto=monto,
                        modulo="ventas",
                        referencia_id=sale_id,
                        sucursal_id=sucursal_id,
                        evento="VENTA_CREDITO",
                    )
                except Exception as e:
                    logger.debug("registrar_asiento CxC: %s", e)

            logger.info(
                "CxC registrada: cliente=%d venta=%d folio=%s monto=%.2f",
                cliente_id, sale_id, folio, monto,
            )
        except Exception as e:
            logger.error("register_credit_sale: %s", e)

    # ── Infraestructura ───────────────────────────────────────────────────────

    def _ensure_cxc_table(self) -> None:
        """Crea cuentas_por_cobrar si no existe (idempotente)."""
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS cuentas_por_cobrar (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    cliente_id       INTEGER NOT NULL,
                    venta_id         INTEGER,
                    folio            TEXT,
                    monto_original   REAL    NOT NULL,
                    saldo_pendiente  REAL    NOT NULL,
                    estado           TEXT    DEFAULT 'pendiente',
                    sucursal_id      INTEGER DEFAULT 1,
                    fecha            DATETIME DEFAULT (datetime('now')),
                    fecha_pago       DATETIME
                )
            """)
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("_ensure_cxc_table: %s", e)
