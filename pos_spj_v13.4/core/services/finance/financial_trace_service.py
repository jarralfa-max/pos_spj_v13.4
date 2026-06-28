# core/services/finance/financial_trace_service.py — SPJ ERP v13.4
"""
FinancialTraceService — trazabilidad financiera end-to-end.

Orquesta todos los servicios financieros para garantizar que cada
operación deje rastro completo:

  evento → documento → tesorería → asiento → bitácora → conciliación

Métodos públicos por módulo:
  trace_sale(payload)               — venta (contado o crédito)
  trace_purchase(payload)           — compra (contado o crédito)
  trace_payment(payload)            — cobro de CxC o pago de CxP
  trace_payroll(payload)            — nómina generada o pagada
  trace_expense(payload)            — gasto operativo
  trace_waste(payload)              — merma (asiento sin treasury)
  trace_loyalty(payload)            — puntos ganados/canjeados
  trace_delivery_payment(payload)   — cobro delivery confirmado
  trace_driver_settlement(payload)  — corte de repartidor
  trace_fixed_asset_purchase(payload) — compra de activo fijo
  trace_asset_depreciation(payload) — depreciación mensual
  trace_maintenance(payload)        — mantenimiento
  trace_operating_supply(payload)   — insumo operativo

Reglas:
  - Cada método es idempotente: si operation_id ya fue procesado, es no-op.
  - Cada método registra en financial_trace_log (started/completed/failed).
  - Ningún método hace commit — el caller controla la transacción.
  - Si una tabla no existe, graceful degradation (log warning, continúa).
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Optional

logger = logging.getLogger("spj.finance.trace")


class FinancialTraceService:
    """Trazabilidad financiera end-to-end."""

    def __init__(
        self,
        db,
        journal_service=None,
        document_service=None,
        treasury_service=None,
        asset_service=None,
        maintenance_service=None,
        supply_service=None,
        idempotency_service=None,
    ):
        from core.db.connection import wrap
        self._db   = wrap(db)
        self._je   = journal_service
        self._fd   = document_service
        self._tm   = treasury_service
        self._fa   = asset_service
        self._mnt  = maintenance_service
        self._os   = supply_service
        self._idem = idempotency_service

    # ── VENTAS ────────────────────────────────────────────────────────────────

    def trace_sale(self, payload: Dict) -> Dict:
        """
        Traza venta completada.

        Contado:  treasury_inflow + journal(caja/banco → ventas)
        Crédito:  financial_document(receivable) + journal(cxc → ventas)
        """
        op_id = self._op_id(payload, "sale", "VENTA_TRAZADA")
        result = self._base_result(op_id)
        trace_id = self._trace_start(op_id, "VENTA_COMPLETADA", payload)
        try:
            total          = float(payload.get("total", 0))
            payment_method = str(payload.get("payment_method", payload.get("forma_pago", "Efectivo")))
            sale_id        = payload.get("sale_id") or payload.get("venta_id")
            folio          = str(payload.get("folio", ""))
            branch_id = str(payload.get("branch_id") or payload.get("sucursal_id") or "")
            user           = str(payload.get("user", payload.get("usuario", "sistema")))
            cliente_id     = payload.get("cliente_id")

            if total <= 0:
                self._trace_skip(trace_id, "amount=0")
                return result

            is_credit = payment_method == "Credito"
            is_mp     = payment_method in ("Mercado Pago", "mercado_pago")

            if is_mp:
                # Link de pago NO confirma ingreso — no registrar treasury
                self._trace_skip(trace_id, "MercadoPago pendiente — sin treasury hasta webhook")
                return result

            meta = {"folio": folio, "sale_id": sale_id, "cliente_id": cliente_id,
                    "payment_method": payment_method}

            if is_credit:
                # CxC + asiento (sin treasury)
                if self._fd:
                    result["document_id"] = self._fd.create_receivable(
                        operation_id=f"{op_id}-FD",
                        source_module="ventas",
                        source_id=sale_id,
                        amount=total,
                        party_id=cliente_id,
                        source_folio=folio,
                        branch_id=branch_id,
                        user=user,
                        metadata=meta,
                    )
                if self._je:
                    result["journal_id"] = self._je.post_entry(
                        operation_id=f"{op_id}-JE",
                        event_type="VENTA_CREDITO",
                        source_module="ventas",
                        source_id=sale_id,
                        source_folio=folio,
                        debit_account="130.1-cuentas_por_cobrar",
                        credit_account="401.0-ingresos_ventas",
                        amount=total,
                        branch_id=branch_id,
                        user=user,
                        metadata=meta,
                    )
            else:
                # Contado: treasury + asiento
                if self._tm:
                    result["movement_id"] = self._tm.register_inflow(
                        operation_id=f"{op_id}-TM",
                        amount=total,
                        payment_method=payment_method,
                        source_module="ventas",
                        source_id=sale_id,
                        source_folio=folio,
                        branch_id=branch_id,
                        user=user,
                        metadata=meta,
                    )
                debit = self._payment_account(payment_method)
                if self._je:
                    result["journal_id"] = self._je.post_entry(
                        operation_id=f"{op_id}-JE",
                        event_type="VENTA_CONTADO",
                        source_module="ventas",
                        source_id=sale_id,
                        source_folio=folio,
                        debit_account=debit,
                        credit_account="401.0-ingresos_ventas",
                        amount=total,
                        branch_id=branch_id,
                        user=user,
                        metadata=meta,
                    )

            result["traced"] = True
            self._trace_complete(trace_id)
        except Exception as exc:
            logger.error("trace_sale op=%s: %s", op_id, exc)
            self._trace_fail(trace_id, str(exc))
        return result

    # ── COMPRAS ───────────────────────────────────────────────────────────────

    def trace_purchase(self, payload: Dict) -> Dict:
        """
        Traza compra.

        Contado:  treasury_outflow + journal(costo → caja)
        Crédito:  financial_document(payable) + journal(costo → cxp)
        """
        op_id = self._op_id(payload, "compras", "COMPRA_TRAZADA")
        result = self._base_result(op_id)
        trace_id = self._trace_start(op_id, "COMPRA_REGISTRADA", payload)
        try:
            total       = float(payload.get("total", 0))
            folio       = str(payload.get("folio", ""))
            purchase_id = payload.get("compra_id") or payload.get("purchase_id")
            supplier_id = payload.get("supplier_id") or payload.get("proveedor_id")
            branch_id = str(payload.get("branch_id") or payload.get("sucursal_id") or "")
            user        = str(payload.get("user", payload.get("usuario", "sistema")))
            payment_method = payload.get("payment_method") or payload.get("forma_pago")
            paid_now = bool(payment_method and payment_method not in ("credito", "Credito", ""))
            meta = {"folio": folio, "purchase_id": purchase_id, "supplier_id": supplier_id}

            if total <= 0:
                self._trace_skip(trace_id, "amount=0")
                return result

            if not paid_now:
                if self._fd:
                    result["document_id"] = self._fd.create_payable(
                        operation_id=f"{op_id}-FD",
                        source_module="compras",
                        source_id=purchase_id,
                        amount=total,
                        party_id=supplier_id,
                        source_folio=folio,
                        branch_id=branch_id,
                        user=user,
                        metadata=meta,
                    )
                if self._je:
                    result["journal_id"] = self._je.post_entry(
                        operation_id=f"{op_id}-JE",
                        event_type="COMPRA_CREDITO",
                        source_module="compras",
                        source_id=purchase_id,
                        source_folio=folio,
                        debit_account="501-costo_mercancia",
                        credit_account="210-cuentas_por_pagar",
                        amount=total,
                        branch_id=branch_id,
                        user=user,
                        metadata=meta,
                    )
            else:
                if self._tm:
                    result["movement_id"] = self._tm.register_outflow(
                        operation_id=f"{op_id}-TM",
                        amount=total,
                        payment_method=str(payment_method),
                        source_module="compras",
                        source_id=purchase_id,
                        source_folio=folio,
                        branch_id=branch_id,
                        user=user,
                        metadata=meta,
                    )
                if self._je:
                    result["journal_id"] = self._je.post_entry(
                        operation_id=f"{op_id}-JE",
                        event_type="COMPRA_CONTADO",
                        source_module="compras",
                        source_id=purchase_id,
                        source_folio=folio,
                        debit_account="501-costo_mercancia",
                        credit_account="110-caja",
                        amount=total,
                        branch_id=branch_id,
                        user=user,
                        metadata=meta,
                    )

            result["traced"] = True
            self._trace_complete(trace_id)
        except Exception as exc:
            logger.error("trace_purchase op=%s: %s", op_id, exc)
            self._trace_fail(trace_id, str(exc))
        return result

    # ── PAGOS (cobro CxC / pago CxP) ─────────────────────────────────────────

    def trace_payment(self, payload: Dict) -> Dict:
        """Traza cobro de CxC o pago de CxP."""
        op_id = self._op_id(payload, "pagos", "PAGO_TRAZADO")
        result = self._base_result(op_id)
        trace_id = self._trace_start(op_id, "PAYMENT_CONFIRMED", payload)
        try:
            amount       = float(payload.get("amount", payload.get("monto", 0)))
            direction    = str(payload.get("direction", "in"))
            payment_method = str(payload.get("payment_method", "efectivo"))
            source_module = str(payload.get("source_module", "pagos"))
            source_id    = payload.get("source_id")
            branch_id = str(payload.get("branch_id") or "")
            user         = str(payload.get("user", "sistema"))

            if amount <= 0:
                self._trace_skip(trace_id, "amount=0")
                return result

            if direction == "in":
                if self._tm:
                    result["movement_id"] = self._tm.register_inflow(
                        operation_id=f"{op_id}-TM",
                        amount=amount,
                        payment_method=payment_method,
                        source_module=source_module,
                        source_id=source_id,
                        branch_id=branch_id,
                        user=user,
                        metadata=payload,
                    )
                if self._je:
                    result["journal_id"] = self._je.post_entry(
                        operation_id=f"{op_id}-JE",
                        event_type="CXC_COBRADA",
                        source_module=source_module,
                        source_id=source_id,
                        debit_account=self._payment_account(payment_method),
                        credit_account="130.1-cuentas_por_cobrar",
                        amount=amount,
                        branch_id=branch_id,
                        user=user,
                        metadata=payload,
                    )
            else:
                if self._tm:
                    result["movement_id"] = self._tm.register_outflow(
                        operation_id=f"{op_id}-TM",
                        amount=amount,
                        payment_method=payment_method,
                        source_module=source_module,
                        source_id=source_id,
                        branch_id=branch_id,
                        user=user,
                        metadata=payload,
                    )
                if self._je:
                    result["journal_id"] = self._je.post_entry(
                        operation_id=f"{op_id}-JE",
                        event_type="CXP_ABONADA",
                        source_module=source_module,
                        source_id=source_id,
                        debit_account="210-cuentas_por_pagar",
                        credit_account=self._payment_account(payment_method),
                        amount=amount,
                        branch_id=branch_id,
                        user=user,
                        metadata=payload,
                    )

            result["traced"] = True
            self._trace_complete(trace_id)
        except Exception as exc:
            logger.error("trace_payment op=%s: %s", op_id, exc)
            self._trace_fail(trace_id, str(exc))
        return result

    # ── NÓMINA ────────────────────────────────────────────────────────────────

    def trace_payroll(self, payload: Dict) -> Dict:
        """
        Traza nómina.
        event='generated': obligación (FD payroll) + asiento (nomina_exp → nomina_payable)
        event='paid': treasury_outflow + asiento (nomina_payable → caja)
        """
        op_id = self._op_id(payload, "nomina", "NOMINA_TRAZADA")
        result = self._base_result(op_id)
        trace_id = self._trace_start(op_id, "NOMINA_TRAZADA", payload)
        try:
            total        = float(payload.get("total", 0))
            event        = str(payload.get("event", "paid"))
            payment_method = str(payload.get("payment_method", payload.get("metodo_pago", "efectivo")))
            nomina_id    = payload.get("nomina_id") or payload.get("pago_id")
            empleado_id  = payload.get("empleado_id")
            branch_id = str(payload.get("branch_id") or payload.get("sucursal_id") or "")
            user         = str(payload.get("user", payload.get("usuario", "sistema")))
            meta         = {"nomina_id": nomina_id, "empleado_id": empleado_id}

            if total <= 0:
                self._trace_skip(trace_id, "amount=0")
                return result

            if event == "generated":
                if self._fd:
                    result["document_id"] = self._fd.create_payroll_payable(
                        operation_id=f"{op_id}-FD",
                        source_id=nomina_id,
                        amount=total,
                        party_id=empleado_id,
                        branch_id=branch_id,
                        user=user,
                        metadata=meta,
                    )
                if self._je:
                    result["journal_id"] = self._je.post_entry(
                        operation_id=f"{op_id}-JE",
                        event_type="PAYROLL_GENERATED",
                        source_module="nomina",
                        source_id=nomina_id,
                        debit_account="510-nomina_expense",
                        credit_account="220-nomina_payable",
                        amount=total,
                        branch_id=branch_id,
                        user=user,
                        metadata=meta,
                    )
            else:  # paid
                if self._tm:
                    result["movement_id"] = self._tm.register_outflow(
                        operation_id=f"{op_id}-TM",
                        amount=total,
                        payment_method=payment_method,
                        source_module="nomina",
                        source_id=nomina_id,
                        branch_id=branch_id,
                        user=user,
                        metadata=meta,
                    )
                if self._je:
                    result["journal_id"] = self._je.post_entry(
                        operation_id=f"{op_id}-JE",
                        event_type="PAYROLL_PAID",
                        source_module="nomina",
                        source_id=nomina_id,
                        debit_account="220-nomina_payable",
                        credit_account=self._payment_account(payment_method),
                        amount=total,
                        branch_id=branch_id,
                        user=user,
                        metadata=meta,
                    )

            result["traced"] = True
            self._trace_complete(trace_id)
        except Exception as exc:
            logger.error("trace_payroll op=%s: %s", op_id, exc)
            self._trace_fail(trace_id, str(exc))
        return result

    # ── MERMA ─────────────────────────────────────────────────────────────────

    def trace_waste(self, payload: Dict) -> Dict:
        """Merma: asiento contable SIN treasury movement."""
        op_id = self._op_id(payload, "merma", "MERMA_TRAZADA")
        result = self._base_result(op_id)
        trace_id = self._trace_start(op_id, "MERMA_REGISTRADA", payload)
        try:
            cost      = float(payload.get("costo_estimado", payload.get("total_cost", 0)))
            merma_id  = payload.get("merma_id")
            branch_id = str(payload.get("branch_id") or payload.get("sucursal_id") or "")
            user      = str(payload.get("user", payload.get("usuario", "sistema")))

            if cost <= 0:
                self._trace_skip(trace_id, "costo_estimado=0")
                return result

            if self._je:
                result["journal_id"] = self._je.post_entry(
                    operation_id=f"{op_id}-JE",
                    event_type="WASTE_RECORDED",
                    source_module="merma",
                    source_id=merma_id,
                    debit_account="540-perdida_merma",
                    credit_account="120-inventario",
                    amount=cost,
                    branch_id=branch_id,
                    user=user,
                    metadata=payload,
                )
            result["traced"] = True
            self._trace_complete(trace_id)
        except Exception as exc:
            logger.error("trace_waste op=%s: %s", op_id, exc)
            self._trace_fail(trace_id, str(exc))
        return result

    # ── FIDELIDAD ─────────────────────────────────────────────────────────────

    def trace_loyalty(self, payload: Dict) -> Dict:
        """Puntos: pasivo/asiento SIN treasury movement."""
        op_id = self._op_id(payload, "fidelidad", "LOYALTY_TRAZADA")
        result = self._base_result(op_id)
        trace_id = self._trace_start(op_id, "LOYALTY_EVENT", payload)
        try:
            amount    = float(payload.get("monto_puntos", payload.get("points_value", 0)))
            event     = str(payload.get("event", "earned"))
            branch_id = str(payload.get("branch_id") or "")
            user      = str(payload.get("user", "sistema"))

            if amount <= 0:
                self._trace_skip(trace_id, "amount=0")
                return result

            if event == "earned":
                debit, credit = "570-loyalty_expense", "230-loyalty_liability"
            else:  # redeemed
                debit, credit = "230-loyalty_liability", "401.1-descuento_fidelidad"

            if self._je:
                result["journal_id"] = self._je.post_entry(
                    operation_id=f"{op_id}-JE",
                    event_type=f"LOYALTY_{event.upper()}",
                    source_module="fidelidad",
                    source_id=payload.get("cliente_id"),
                    debit_account=debit,
                    credit_account=credit,
                    amount=amount,
                    branch_id=branch_id,
                    user=user,
                    metadata=payload,
                )
            result["traced"] = True
            self._trace_complete(trace_id)
        except Exception as exc:
            logger.error("trace_loyalty op=%s: %s", op_id, exc)
            self._trace_fail(trace_id, str(exc))
        return result

    # ── DELIVERY ──────────────────────────────────────────────────────────────

    def trace_delivery_payment(self, payload: Dict) -> Dict:
        """Cobro de delivery confirmado al entregar."""
        op_id = self._op_id(payload, "delivery", "DELIVERY_COBRO_TRAZADO")
        result = self._base_result(op_id)
        trace_id = self._trace_start(op_id, "DELIVERY_PAYMENT_CONFIRMED", payload)
        try:
            total     = float(payload.get("total", 0))
            pedido_id = payload.get("pedido_id") or payload.get("delivery_id")
            branch_id = str(payload.get("branch_id") or "")
            user      = str(payload.get("user", "sistema"))

            if total <= 0:
                self._trace_skip(trace_id, "amount=0")
                return result

            if self._tm:
                result["movement_id"] = self._tm.register_inflow(
                    operation_id=f"{op_id}-TM",
                    amount=total,
                    payment_method="efectivo",
                    source_module="delivery",
                    source_id=pedido_id,
                    branch_id=branch_id,
                    user=user,
                    metadata=payload,
                )
            if self._je:
                result["journal_id"] = self._je.post_entry(
                    operation_id=f"{op_id}-JE",
                    event_type="DELIVERY_PAYMENT_CONFIRMED",
                    source_module="delivery",
                    source_id=pedido_id,
                    debit_account="115-caja_delivery",
                    credit_account="401.0-ingresos_ventas",
                    amount=total,
                    branch_id=branch_id,
                    user=user,
                    metadata=payload,
                )

            result["traced"] = True
            self._trace_complete(trace_id)
        except Exception as exc:
            logger.error("trace_delivery_payment op=%s: %s", op_id, exc)
            self._trace_fail(trace_id, str(exc))
        return result

    def trace_driver_settlement(self, payload: Dict) -> Dict:
        """Corte de repartidor — registra diferencia si aplica."""
        op_id = self._op_id(payload, "delivery", "CORTE_REPARTIDOR_TRAZADO")
        result = self._base_result(op_id)
        trace_id = self._trace_start(op_id, "DRIVER_SETTLEMENT_CREATED", payload)
        try:
            expected  = float(payload.get("expected_amount", 0))
            actual    = float(payload.get("actual_amount", 0))
            diff      = round(actual - expected, 2)
            branch_id = str(payload.get("branch_id") or "")
            user      = str(payload.get("user", "sistema"))

            if abs(diff) > 0.01 and self._je:
                debit  = "115-caja_delivery" if diff < 0 else "540-diferencias_corte"
                credit = "540-diferencias_corte" if diff < 0 else "115-caja_delivery"
                result["journal_id"] = self._je.post_entry(
                    operation_id=f"{op_id}-JE",
                    event_type="DRIVER_SETTLEMENT_DIFFERENCE",
                    source_module="delivery",
                    source_id=payload.get("driver_id"),
                    debit_account=debit,
                    credit_account=credit,
                    amount=abs(diff),
                    branch_id=branch_id,
                    user=user,
                    metadata=payload,
                )

            result["traced"] = True
            self._trace_complete(trace_id)
        except Exception as exc:
            logger.error("trace_driver_settlement op=%s: %s", op_id, exc)
            self._trace_fail(trace_id, str(exc))
        return result

    # ── ACTIVOS Y MANTENIMIENTO (delegación) ──────────────────────────────────

    def trace_fixed_asset_purchase(self, payload: Dict) -> Dict:
        op_id = self._op_id(payload, "activos", "ACTIVO_TRAZADO")
        result = self._base_result(op_id)
        trace_id = self._trace_start(op_id, "FIXED_ASSET_PURCHASED", payload)
        try:
            if self._fa:
                result["asset_id"] = self._fa.register_asset_purchase(
                    operation_id=op_id,
                    asset_name=str(payload.get("asset_name", "")),
                    asset_type=str(payload.get("asset_type", "other")),
                    acquisition_cost=float(payload.get("cost", 0)),
                    acquisition_date=payload.get("date"),
                    useful_life_months=int(payload.get("useful_life_months", 60)),
                    supplier_id=payload.get("supplier_id"),
                    source_module=payload.get("source_module", "activos"),
                    source_id=payload.get("source_id"),
                    source_folio=str(payload.get("folio", "")),
                    branch_id = str(payload.get("branch_id") or ""),
                    user=str(payload.get("user", "sistema")),
                    metadata=payload,
                )
            result["traced"] = True
            self._trace_complete(trace_id)
        except Exception as exc:
            logger.error("trace_fixed_asset_purchase op=%s: %s", op_id, exc)
            self._trace_fail(trace_id, str(exc))
        return result

    def trace_asset_depreciation(self, payload: Dict) -> Dict:
        op_id = self._op_id(payload, "activos", f"DEP-{payload.get('period','')}")
        result = self._base_result(op_id)
        trace_id = self._trace_start(op_id, "FIXED_ASSET_DEPRECIATED", payload)
        try:
            if self._fa:
                result["depreciation_id"] = self._fa.depreciate_asset(
                    asset_id=int(payload.get("asset_id", 0)),
                    period=str(payload.get("period", "")),
                    amount=payload.get("amount"),
                    user=str(payload.get("user", "sistema")),
                )
            result["traced"] = True
            self._trace_complete(trace_id)
        except Exception as exc:
            logger.error("trace_asset_depreciation op=%s: %s", op_id, exc)
            self._trace_fail(trace_id, str(exc))
        return result

    def trace_maintenance(self, payload: Dict) -> Dict:
        op_id = self._op_id(payload, "mantenimiento", "MANT_TRAZADO")
        result = self._base_result(op_id)
        trace_id = self._trace_start(op_id, "MAINTENANCE_REGISTERED", payload)
        try:
            if self._mnt:
                r = self._mnt.register_maintenance(
                    operation_id=op_id,
                    amount=float(payload.get("amount", payload.get("monto", 0))),
                    maintenance_type=str(payload.get("maintenance_type", "corrective")),
                    description=str(payload.get("description", "")),
                    asset_id=payload.get("asset_id"),
                    supplier_id=payload.get("supplier_id"),
                    source_module=payload.get("source_module", "mantenimiento"),
                    source_id=payload.get("source_id"),
                    source_folio=str(payload.get("folio", "")),
                    payment_method=payload.get("payment_method"),
                    is_capitalizable=bool(payload.get("capitalizable", False)),
                    branch_id = str(payload.get("branch_id") or ""),
                    user=str(payload.get("user", "sistema")),
                    metadata=payload,
                )
                result.update(r)
            result["traced"] = True
            self._trace_complete(trace_id)
        except Exception as exc:
            logger.error("trace_maintenance op=%s: %s", op_id, exc)
            self._trace_fail(trace_id, str(exc))
        return result

    def trace_operating_supply(self, payload: Dict) -> Dict:
        op_id = self._op_id(payload, "insumos", "INSUMO_TRAZADO")
        result = self._base_result(op_id)
        trace_id = self._trace_start(op_id, "OPERATING_SUPPLY_PURCHASED", payload)
        try:
            if self._os:
                r = self._os.register_supply_purchase(
                    operation_id=op_id,
                    supply_type=str(payload.get("supply_type", "other")),
                    total_amount=float(payload.get("total_amount", payload.get("monto", 0))),
                    description=str(payload.get("description", "")),
                    quantity=float(payload.get("quantity", 1)),
                    unit_cost=payload.get("unit_cost"),
                    supplier_id=payload.get("supplier_id"),
                    source_module=payload.get("source_module", "compras"),
                    source_id=payload.get("source_id"),
                    source_folio=str(payload.get("folio", "")),
                    payment_method=payload.get("payment_method"),
                    branch_id = str(payload.get("branch_id") or ""),
                    user=str(payload.get("user", "sistema")),
                    metadata=payload,
                )
                result.update(r)
            result["traced"] = True
            self._trace_complete(trace_id)
        except Exception as exc:
            logger.error("trace_operating_supply op=%s: %s", op_id, exc)
            self._trace_fail(trace_id, str(exc))
        return result

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _op_id(self, payload: Dict, module: str, event: str) -> str:
        if "operation_id" in payload and payload["operation_id"]:
            return str(payload["operation_id"])
        src_id = (
            payload.get("sale_id") or payload.get("venta_id") or
            payload.get("compra_id") or payload.get("purchase_id") or
            payload.get("nomina_id") or payload.get("source_id") or
            payload.get("asset_id") or payload.get("merma_id") or
            payload.get("pedido_id") or "0"
        )
        return f"{module}-{src_id}-{event}"

    @staticmethod
    def _base_result(op_id: str) -> Dict:
        return {
            "operation_id": op_id, "traced": False,
            "journal_id": 0, "document_id": 0, "movement_id": 0,
        }

    @staticmethod
    def _payment_account(payment_method: str) -> str:
        _MAP = {
            "efectivo": "110-caja", "Efectivo": "110-caja",
            "tarjeta": "112-banco", "Tarjeta": "112-banco",
            "transferencia": "112-banco", "Transferencia": "112-banco",
            "Mercado Pago": "114-pasarela-mp",
            "delivery": "115-caja_delivery",
        }
        return _MAP.get(payment_method, "110-caja")

    # ── Trace log ─────────────────────────────────────────────────────────────

    def _trace_start(self, op_id: str, event_type: str, payload: Dict) -> int:
        try:
            from backend.shared.ids import new_uuid
            trace_id = new_uuid()  # identidad UUIDv7 explícita (REGLA CERO)
            self._db.execute(
                """INSERT INTO financial_trace_log
                       (id, event_type, source_module, source_id, source_folio,
                        operation_id, trace_status, payload_json)
                   VALUES (?,?,?,?,?,?,'started',?)""",
                (
                    trace_id,
                    event_type,
                    payload.get("source_module", ""),
                    payload.get("source_id") or payload.get("sale_id") or payload.get("venta_id"),
                    str(payload.get("folio", "")),
                    op_id,
                    json.dumps(payload, ensure_ascii=False, default=str)[:4000],
                ),
            )
            return trace_id
        except Exception:
            return ""

    def _trace_complete(self, trace_id: int):
        if trace_id:
            try:
                self._db.execute(
                    "UPDATE financial_trace_log SET trace_status='completed' WHERE id=?",
                    (trace_id,),
                )
            except Exception:
                pass

    def _trace_fail(self, trace_id: int, error: str):
        if trace_id:
            try:
                self._db.execute(
                    "UPDATE financial_trace_log SET trace_status='failed', error_message=?"
                    " WHERE id=?",
                    (error[:500], trace_id),
                )
            except Exception:
                pass

    def _trace_skip(self, trace_id: int, reason: str):
        if trace_id:
            try:
                self._db.execute(
                    "UPDATE financial_trace_log SET trace_status='skipped', error_message=?"
                    " WHERE id=?",
                    (reason[:200], trace_id),
                )
            except Exception:
                pass
