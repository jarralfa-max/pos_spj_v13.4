# core/services/finance/third_party_service.py — SPJ ERP
"""
UnifiedThirdPartyService — Gestión unificada de terceros (Proveedores/Clientes).

Wrapper sobre FinanceService AP/AR. No reemplaza módulos existentes.
Sin SQL propio — delega completamente a FinanceService.
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.services.enterprise.finance_service import FinanceService

logger = logging.getLogger("spj.third_party_service")


class UnifiedThirdPartyService:
    """Punto único de consulta y pago para terceros (AP y AR)."""

    def __init__(self, finance_service: "FinanceService"):
        self._fs = finance_service

    def get_balance(self, third_party_id: int, tipo: str = "proveedor") -> dict:
        """
        Retorna saldo pendiente para un tercero.
        tipo='proveedor' → CXP (accounts_payable)
        tipo='cliente'   → CXC (accounts_receivable)
        """
        try:
            if tipo == "proveedor":
                rows = self._fs.cuentas_por_pagar()
                filtered = [r for r in rows
                            if int(r.get("supplier_id") or r.get("proveedor_id") or 0) == third_party_id]
                saldo = sum(float(r.get("balance", r.get("saldo", 0))) for r in filtered)
                return {
                    "third_party_id": third_party_id,
                    "tipo": tipo,
                    "saldo_pendiente": round(saldo, 2),
                    "facturas": len(filtered),
                }
            else:
                rows = self._fs.cuentas_por_cobrar()
                filtered = [r for r in rows
                            if int(r.get("cliente_id") or 0) == third_party_id]
                saldo = sum(float(r.get("balance", r.get("saldo", 0))) for r in filtered)
                return {
                    "third_party_id": third_party_id,
                    "tipo": tipo,
                    "saldo_pendiente": round(saldo, 2),
                    "facturas": len(filtered),
                }
        except Exception as e:
            logger.warning("get_balance non-fatal: %s", e)
            return {"third_party_id": third_party_id, "tipo": tipo,
                    "saldo_pendiente": 0.0, "error": str(e)}

    def apply_payment(self, data: dict) -> dict:
        """
        Aplica un pago a CXP o CXC.
        data keys:
          account_id   — int (fila AP o AR)
          monto        — float
          tipo         — 'cxp' | 'cxc'
          metodo_pago  — str (default 'efectivo')
          usuario      — str (default 'Sistema')
          notas        — str (opcional)
        """
        try:
            account_id = int(data["account_id"])
            monto      = float(data["monto"])
            tipo       = data.get("tipo", "cxp")
            metodo     = data.get("metodo_pago", "efectivo")
            usuario    = data.get("usuario", "Sistema")
            notas      = data.get("notas")

            if tipo == "cxp":
                result = self._fs.abonar_cxp(
                    ap_id=account_id, monto=monto,
                    metodo_pago=metodo, usuario=usuario, notas=notas,
                ) or {}
            else:
                result = self._fs.cobrar_cxc(
                    ar_id=account_id, monto=monto,
                    metodo_pago=metodo, usuario=usuario, notas=notas,
                ) or {}

            try:
                from core.events.event_bus import get_bus
                from core.events.domain_events import PAYMENT_RECEIVED
                get_bus().publish(PAYMENT_RECEIVED, {
                    "account_id": account_id,
                    "tipo": tipo,
                    "monto": monto,
                    "metodo_pago": metodo,
                    "nuevo_balance": result.get("nuevo_balance", 0),
                    "nuevo_status": result.get("nuevo_status", ""),
                })
            except Exception as _e:
                logger.debug("apply_payment event non-fatal: %s", _e)

            return {"ok": True, **result}

        except Exception as e:
            logger.warning("apply_payment failed: %s", e)
            return {"ok": False, "error": str(e)}
