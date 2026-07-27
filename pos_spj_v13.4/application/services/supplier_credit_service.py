# application/services/supplier_credit_service.py — SPJ POS v13.4
"""
SupplierCreditService — política de crédito de proveedor para Compras.

Espeja CustomerCreditService: valida que una compra a crédito no exceda el
límite del proveedor antes de autorizarla. Nunca autoriza en silencio.

Reglas:
- Identidad UUID string (proveedor_id) — nunca int.
- Crédito disponible = limite_credito − saldo pendiente de CxP del proveedor.
- No crea ni altera schema.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger("spj.supplier_credit")


class SupplierCreditService:
    def __init__(self, db_conn: Any) -> None:
        self.db = db_conn

    # ── infra ────────────────────────────────────────────────────────────────
    def _table_exists(self, name: str) -> bool:
        return bool(self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone())

    def get_supplier(self, supplier_id: str) -> Optional[dict]:
        supplier_id = str(supplier_id or "").strip()
        if not supplier_id:
            return None
        row = self.db.execute(
            "SELECT id, nombre, COALESCE(activo,1), COALESCE(limite_credito,0) "
            "FROM proveedores WHERE id=?",
            (supplier_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]),
            "nombre": str(row[1] or ""),
            "activo": bool(row[2]),
            "limite_credito": float(row[3] or 0),
        }

    def outstanding_balance(self, supplier_id: str) -> float:
        """Saldo pendiente de CxP del proveedor (fuentes canónicas)."""
        supplier_id = str(supplier_id or "").strip()
        if not supplier_id:
            return 0.0
        total = 0.0
        if self._table_exists("accounts_payable"):
            row = self.db.execute(
                "SELECT COALESCE(SUM(balance),0) FROM accounts_payable "
                "WHERE supplier_id=? AND COALESCE(status,'pendiente') IN ('pendiente','parcial')",
                (supplier_id,),
            ).fetchone()
            total += float(row[0] or 0) if row else 0.0
        if self._table_exists("cuentas_por_pagar"):
            row = self.db.execute(
                "SELECT COALESCE(SUM(saldo_pendiente),0) FROM cuentas_por_pagar "
                "WHERE proveedor_id=? AND COALESCE(estado,'pendiente') IN ('pendiente','parcial')",
                (supplier_id,),
            ).fetchone()
            total += float(row[0] or 0) if row else 0.0
        return round(total, 2)

    def available_credit(self, supplier_id: str) -> float:
        supplier = self.get_supplier(supplier_id)
        if not supplier:
            return 0.0
        return round(supplier["limite_credito"] - self.outstanding_balance(supplier_id), 2)

    def validate_credit(self, supplier_id: str, monto: float) -> Tuple[bool, str]:
        """
        (True, "") si la compra a crédito por `monto` está autorizada;
        (False, motivo) en caso contrario. Nunca autoriza en silencio.
        """
        supplier_id = str(supplier_id or "").strip()
        if not supplier_id:
            return False, "Para comprar a crédito debe seleccionar un proveedor válido."
        supplier = self.get_supplier(supplier_id)
        if not supplier:
            return False, f"Proveedor {supplier_id} no encontrado."
        if not supplier["activo"]:
            return False, f"El proveedor '{supplier['nombre']}' está inactivo."
        if supplier["limite_credito"] <= 0:
            return False, (
                f"El proveedor '{supplier['nombre']}' no tiene línea de crédito "
                "configurada. Registre la compra de contado o configure su límite."
            )
        disponible = supplier["limite_credito"] - self.outstanding_balance(supplier_id)
        monto = round(float(monto or 0), 2)
        if disponible < monto:
            return False, (
                f"Crédito de proveedor insuficiente para '{supplier['nombre']}': "
                f"disponible ${disponible:,.2f}, requerido ${monto:,.2f}"
            )
        return True, ""
