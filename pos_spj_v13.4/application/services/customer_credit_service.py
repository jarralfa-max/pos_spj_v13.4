# application/services/customer_credit_service.py — SPJ POS v13.4
"""
CustomerCreditService — validación de clientes y crédito (CxC) en checkout.

Responsabilidades:
- Verificar que el cliente existe antes de completar la venta
- Validar que el cliente tiene crédito autorizado y suficiente
- Registrar la deuda en cuentas_por_cobrar para ventas a crédito

Reglas:
- Identidad UUID string en todos los contratos (nunca int).
- Sin sucursal default '1'.
- CxC idempotente por venta_id (índice único idx_cxc_venta_unica).
- No crea ni altera schema (canónico en migrations/).
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.customer_credit")


class CustomerCreditService:
    """
    Servicio de aplicación para validación de clientes y crédito.
    Inyectable en SalesService sin dependencia de PyQt5 ni GrowthEngine.
    """

    def __init__(self, db_conn, finance_service=None):
        self.db = db_conn
        self._finance = finance_service

    # ── API pública ───────────────────────────────────────────────────────────

    def get_customer(self, cliente_id: str) -> Optional[dict]:
        """
        Retorna dict con datos del cliente o None si no existe/está inactivo.
        Claves: id, nombre, activo, allows_credit, credit_limit, credit_balance, puntos
        """
        cliente_id = str(cliente_id or "").strip()
        if not cliente_id:
            return None
        try:
            row = self.db.execute(
                """SELECT id, nombre, activo,
                          COALESCE(allows_credit, 0)    AS allows_credit,
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
            "id":             str(row[0]),
            "nombre":         row[1],
            "activo":         bool(row[2]),
            "allows_credit":  bool(row[3]),
            "credit_limit":   float(row[4]),
            "credit_balance": float(row[5]),
            "puntos":         int(row[6]),
        }

    def validate_credit(self, cliente_id: str, monto: float) -> Tuple[bool, str]:
        """
        Verifica si el cliente puede comprar a crédito por `monto`.

        Returns:
            (True, "")              — aprobado
            (False, "motivo...")    — rechazado
        """
        cliente_id = str(cliente_id or "").strip()
        if not cliente_id:
            return False, "Para vender a crédito debe seleccionar un cliente con crédito autorizado."

        customer = self.get_customer(cliente_id)
        if not customer:
            return False, f"Cliente {cliente_id} no encontrado o inactivo."

        if not customer["allows_credit"]:
            return False, f"El cliente '{customer['nombre']}' no tiene crédito autorizado."

        if customer["credit_limit"] <= 0:
            return False, f"El cliente '{customer['nombre']}' no tiene límite de crédito configurado."

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
        cliente_id: str,
        sale_id: str,
        folio: str,
        monto: float,
        sucursal_id: str,
    ) -> None:
        """
        Registra la deuda en cuentas_por_cobrar, actualiza credit_balance y asienta
        el ledger DENTRO de la misma transacción.

        Idempotente por venta_id: el índice único idx_cxc_venta_unica evita
        duplicar la CxC al reintentar el evento (INSERT OR IGNORE).
        Si falla la CxC, la excepción se propaga y la venta debe abortar:
        nunca se omite CxC en silencio.
        """
        cliente_id  = str(cliente_id or "").strip()
        sale_id     = str(sale_id or "").strip()
        sucursal_id = str(sucursal_id or "").strip()
        if not cliente_id or not sale_id:
            raise ValueError(
                "register_credit_sale requiere cliente_id y venta_id UUID válidos."
            )
        try:
            cur = self.db.execute(
                """INSERT OR IGNORE INTO cuentas_por_cobrar
                       (id, cliente_id, venta_id, folio, monto_original,
                        saldo_pendiente, sucursal_id, estado)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pendiente')""",
                (new_uuid(), cliente_id, sale_id, folio, monto, monto, sucursal_id),
            )
            if getattr(cur, "rowcount", 1) == 0:
                logger.info(
                    "CxC ya registrada para venta=%s (idempotente) — sin cambios",
                    sale_id,
                )
                return

            # Sync both canonical columns so service layer and legacy UI stay consistent
            self.db.execute(
                "UPDATE clientes "
                "SET credit_balance = COALESCE(credit_balance, 0) + ?, "
                "    saldo          = COALESCE(saldo, 0) + ? "
                "WHERE id = ?",
                (monto, monto, cliente_id),
            )

            # Asiento contable DENTRO de la misma transacción (antes del commit)
            # Garantiza que CxC y GL sean atómicos: si el asiento falla, la CxC no se graba.
            if self._finance and hasattr(self._finance, "registrar_asiento"):
                self._finance.registrar_asiento(
                    debe          = "130.1-cuentas-por-cobrar",
                    haber         = "401.0-ingresos-ventas",
                    concepto      = f"Venta a crédito {folio}",
                    monto         = monto,
                    modulo        = "ventas",
                    referencia_id = sale_id,
                    sucursal_id   = sucursal_id,
                    evento        = "VENTA_CREDITO",
                    metadata      = {"cliente_id": cliente_id, "folio": folio},
                )

            logger.info(
                "CxC registrada: cliente=%s venta=%s folio=%s monto=%.2f",
                cliente_id, sale_id, folio, monto,
            )
        except Exception as e:
            logger.error("register_credit_sale: %s", e)
            raise
