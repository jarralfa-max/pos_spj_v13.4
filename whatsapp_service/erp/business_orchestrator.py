# erp/business_orchestrator.py — SPJ POS v13.4 — FASE WA
"""
BusinessOrchestrator — Coordina flujos de negocio entre WhatsApp y el ERP.

RESPONSABILIDADES:
  - Cotización → Venta real (validando crédito + inventario)
  - Validación y cálculo de anticipos (usando reglas del ERP)
  - Generación automática de OC cuando no hay stock
  - Scheduling de delivery (sin modificar flujo existente)
  - Publicación de todos los eventos de negocio al EventBus

REGLA CRÍTICA:
  NO modifica procesar_venta() ni programar_delivery() del ERP.
  SOLO emite eventos y escribe en tablas vía ERPBridge.

FEATURE FLAG: whatsapp_advanced_enabled (module_toggles en BD)
"""
from __future__ import annotations

import logging
from typing import List, Dict, Optional, Any

from erp.bridge import ERPBridge
from erp.events import (
    WAEventEmitter,
    QUOTE_CREATED, SALE_CREATED, PAYMENT_REQUIRED, PAYMENT_RECEIVED,
    PURCHASE_ORDER_CREATED, DELIVERY_SCHEDULED, DELIVERY_CONFIRMED,
    STAFF_NOTIFICATION, FORECAST_DEMAND_UPDATED,
    WA_PEDIDO_CREADO, WA_COTIZACION_CREADA, WA_ANTICIPO_REQUERIDO,
    WA_ANTICIPO_PAGADO, WA_VENTA_CONFIRMADA,
)

logger = logging.getLogger("wa.orchestrator")


class BusinessOrchestrator:
    """
    Orquestador central de flujos WA ↔ ERP.
    Una instancia por sesión de bot (reutilizable en tests).
    """

    def __init__(self, erp: ERPBridge, events: WAEventEmitter,
                 sucursal_id: int = 1):
        self.erp = erp
        self.events = events
        self.sucursal_id = sucursal_id
        self._advanced_enabled = self._check_flag("whatsapp_advanced_enabled")

    def _check_flag(self, flag: str) -> bool:
        """Verifica feature flag en module_toggles."""
        try:
            row = self.erp.db.execute(
                "SELECT activo FROM module_toggles WHERE clave=?", (flag,)
            ).fetchone()
            return bool(row[0]) if row else True  # Default habilitado
        except Exception:
            return True

    # ── 6.1 + 6.2: Cotización → Venta ────────────────────────────────────────

    def confirmar_cotizacion(self, cotizacion_id: int, cliente_id: int,
                              items: List[Dict]) -> Dict:
        """
        Guarda cotización en ERP y emite QUOTE_CREATED.
        NO convierte a venta aún — espera confirmación explícita del cliente.
        """
        result = self.erp.crear_cotizacion_wa(
            items=items,
            cliente_id=cliente_id,
            sucursal_id=self.sucursal_id,
        )

        self.events.emit(QUOTE_CREATED, {
            "cotizacion_id": result["cotizacion_id"],
            "folio": result["folio"],
            "total": result["total"],
            "cliente_id": cliente_id,
        }, sucursal_id=self.sucursal_id, prioridad=5)

        # Alias WA
        self.events.emit(WA_COTIZACION_CREADA, {
            "folio": result["folio"],
            "total": result["total"],
            "cliente_id": cliente_id,
        }, sucursal_id=self.sucursal_id, prioridad=5)

        return result

    def convertir_cotizacion_a_venta(self, cotizacion_id: int,
                                      cliente_id: int) -> Optional[Dict]:
        """
        Convierte cotización aprobada → venta real.
        Valida: crédito, stock; genera OC si falta stock; calcula anticipo.
        Emite: SALE_CREATED, PAYMENT_REQUIRED (si aplica), PURCHASE_ORDER_CREATED.
        """
        result = self.erp.convertir_cotizacion_a_venta(cotizacion_id)
        if not result:
            logger.warning("convertir_cotizacion_a_venta: cotizacion %d no encontrada",
                           cotizacion_id)
            return None

        venta_id = result["venta_id"]
        total = result["total"]

        # Emitir SALE_CREATED
        self.events.emit(SALE_CREATED, {
            "venta_id": venta_id,
            "folio": result["folio"],
            "total": total,
            "cliente_id": cliente_id,
            "origen": "cotizacion",
            "cotizacion_id": cotizacion_id,
        }, sucursal_id=self.sucursal_id, prioridad=2)

        self.events.emit(WA_VENTA_CONFIRMADA, {
            "folio": result["folio"], "total": total, "cliente_id": cliente_id,
        }, sucursal_id=self.sucursal_id, prioridad=2)

        # Verificar stock y generar OC si falta
        if self._advanced_enabled:
            items_cot = self.erp.db.execute(
                "SELECT producto_id, nombre, cantidad FROM cotizaciones_detalle "
                "WHERE cotizacion_id=?", (cotizacion_id,)
            ).fetchall()
            self._verificar_y_generar_oc(
                [dict(i) for i in items_cot], venta_id)

        # Calcular anticipo
        anticipo = self.erp.calcular_anticipo_rules(cliente_id, total)
        if anticipo["requiere"]:
            self.erp.registrar_anticipo(venta_id, anticipo["monto"])
            self.events.emit(PAYMENT_REQUIRED, {
                "venta_id": venta_id,
                "folio": result["folio"],
                "monto": anticipo["monto"],
                "razon": anticipo["razon"],
                "tipo": "anticipo",
            }, sucursal_id=self.sucursal_id, prioridad=2)
            self.events.emit(WA_ANTICIPO_REQUERIDO, {
                "folio": result["folio"],
                "monto": anticipo["monto"],
            }, sucursal_id=self.sucursal_id, prioridad=2)
            result["anticipo_requerido"] = True
            result["anticipo_monto"] = anticipo["monto"]
        else:
            result["anticipo_requerido"] = False

        return result

    # ── 6.3: Pedido directo ───────────────────────────────────────────────────

    def procesar_pedido_wa(self, venta_id: int, folio: str, total: float,
                            cliente_id: int, items: List[Dict],
                            tipo_entrega: str = "sucursal",
                            direccion: str = "",
                            fecha_entrega: str = "") -> Dict:
        """
        Post-procesamiento tras crear un pedido WA:
        1. Verifica stock y genera OC
        2. Calcula anticipo
        3. Programa delivery si aplica
        4. Emite eventos correspondientes
        """
        result: Dict[str, Any] = {
            "venta_id": venta_id,
            "folio": folio,
            "anticipo_requerido": False,
        }

        # Emitir SALE_CREATED
        self.events.emit(SALE_CREATED, {
            "venta_id": venta_id, "folio": folio, "total": total,
            "cliente_id": cliente_id, "origen": "whatsapp",
        }, sucursal_id=self.sucursal_id, prioridad=2)

        if self._advanced_enabled:
            # Verificar stock
            self._verificar_y_generar_oc(items, venta_id)

            # Calcular anticipo con reglas ERP
            anticipo = self.erp.calcular_anticipo_rules(cliente_id, total, items)
            if anticipo["requiere"]:
                self.erp.registrar_anticipo(venta_id, anticipo["monto"])
                self.events.emit(PAYMENT_REQUIRED, {
                    "venta_id": venta_id, "folio": folio,
                    "monto": anticipo["monto"], "tipo": "anticipo",
                    "razon": anticipo["razon"],
                }, sucursal_id=self.sucursal_id, prioridad=2)
                self.events.emit(WA_ANTICIPO_REQUERIDO, {
                    "folio": folio, "monto": anticipo["monto"],
                }, sucursal_id=self.sucursal_id, prioridad=2)
                result["anticipo_requerido"] = True
                result["anticipo_monto"] = anticipo["monto"]

        # Programar delivery si es domicilio
        if tipo_entrega == "domicilio" and direccion:
            self.erp.programar_delivery(venta_id, direccion, fecha_entrega)
            self.events.emit(DELIVERY_SCHEDULED, {
                "venta_id": venta_id, "folio": folio,
                "tipo_entrega": tipo_entrega,
                "fecha": fecha_entrega,
            }, sucursal_id=self.sucursal_id, prioridad=5)

        # Emitir evento WA
        self.events.emit(WA_PEDIDO_CREADO, {
            "folio": folio, "total": total, "cliente_id": cliente_id,
        }, sucursal_id=self.sucursal_id, prioridad=3)

        # Notificar staff
        staff_phones = self.erp.get_staff_phones(self.sucursal_id)
        if staff_phones:
            self.events.emit(STAFF_NOTIFICATION, {
                "mensaje": f"Nuevo pedido WA folio {folio} — ${total:.2f}",
                "tipo": "nuevo_pedido",
                "folio": folio,
                "phones": staff_phones,
            }, sucursal_id=self.sucursal_id, prioridad=5)

        return result

    # ── 6.3: Confirmar pago de anticipo ──────────────────────────────────────

    def confirmar_anticipo(self, venta_id: int, monto: float,
                            referencia: str = "",
                            metodo: str = "mercadopago") -> bool:
        """
        Registra pago de anticipo y emite PAYMENT_RECEIVED.
        Si el pago cubre el total, emite DELIVERY_CONFIRMED.
        """
        ok = self.erp.confirmar_pago_anticipo(venta_id, monto, referencia, metodo)
        if not ok:
            return False

        folio = self._get_folio(venta_id)
        self.events.emit(PAYMENT_RECEIVED, {
            "venta_id": venta_id, "folio": folio,
            "monto": monto, "metodo": metodo, "referencia": referencia,
        }, sucursal_id=self.sucursal_id, prioridad=2)

        self.events.emit(WA_ANTICIPO_PAGADO, {
            "folio": folio, "monto": monto,
        }, sucursal_id=self.sucursal_id, prioridad=2)

        # Notificar staff que anticipo fue recibido
        staff = self.erp.get_staff_phones(self.sucursal_id)
        if staff:
            self.events.emit(STAFF_NOTIFICATION, {
                "mensaje": f"Anticipo recibido folio {folio} — ${monto:.2f}",
                "tipo": "anticipo_pagado", "folio": folio, "phones": staff,
            }, sucursal_id=self.sucursal_id, prioridad=3)

        return True

    # ── 6.7: Forecast ─────────────────────────────────────────────────────────

    def registrar_demanda_forecast(self, producto_id: int, cantidad: float,
                                    periodo: str = "") -> None:
        """
        Emite FORECAST_DEMAND_UPDATED sin ejecutar ninguna acción.
        El ForecastService del ERP reacciona si está suscrito.
        """
        self.events.emit(FORECAST_DEMAND_UPDATED, {
            "producto_id": producto_id,
            "demanda_est": cantidad,
            "periodo": periodo,
            "fuente": "whatsapp",
        }, sucursal_id=self.sucursal_id, prioridad=10)

    # ── Helpers privados ──────────────────────────────────────────────────────

    def _verificar_y_generar_oc(self, items: List[Dict], venta_id: int) -> None:
        """Verifica stock de cada item y genera OC si hay faltante."""
        items_check = self.erp.verificar_stock_items(items, self.sucursal_id)
        for it in items_check:
            if it.get("falta", 0) > 0:
                oc_id = self.erp.generar_orden_compra(
                    producto_id=it["producto_id"],
                    cantidad=it["falta"],
                    sucursal_id=self.sucursal_id,
                    notas=f"OC automática por pedido WA #{venta_id}",
                )
                if oc_id:
                    self.events.emit(PURCHASE_ORDER_CREATED, {
                        "oc_id": oc_id,
                        "producto_id": it["producto_id"],
                        "nombre": it.get("nombre", ""),
                        "cantidad": it["falta"],
                        "venta_id": venta_id,
                    }, sucursal_id=self.sucursal_id, prioridad=3)
                    # Notificar compras
                    compras_phones = self.erp.get_compras_phones(self.sucursal_id)
                    if compras_phones:
                        self.events.emit(STAFF_NOTIFICATION, {
                            "mensaje": (f"OC automática: {it.get('nombre','')} "
                                        f"x{it['falta']:.1f} para pedido #{venta_id}"),
                            "tipo": "oc_generada",
                            "phones": compras_phones,
                        }, sucursal_id=self.sucursal_id, prioridad=3)
                    # Emitir forecast de demanda
                    self.registrar_demanda_forecast(
                        it["producto_id"], it["cantidad"])

    def _get_folio(self, venta_id: int) -> str:
        try:
            row = self.erp.db.execute(
                "SELECT folio FROM ventas WHERE id=?", (venta_id,)
            ).fetchone()
            return row[0] if row else str(venta_id)
        except Exception:
            return str(venta_id)
