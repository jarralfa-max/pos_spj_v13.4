# core/use_cases/venta.py — SPJ POS v13.1
"""
Caso de uso: Procesar Venta

Orquesta el flujo completo:
  1. Validar items y stock
  2. Ejecutar venta (SalesService)
  3. Registrar en caja (FinanceService)
  4. Acumular puntos (LoyaltyService)
  5. Generar ticket (TicketTemplateEngine)
  6. Encolar sync (SyncService)
  7. Publicar VENTA_COMPLETADA al EventBus

Este UC reemplaza la lógica duplicada entre:
  - services.py (legacy)
  - core/services/ventas_facade.py (legacy)
  - core/services/sales/unified_sales_service.py (legacy)
  - modulos/ventas.py (UI directamente)

Compatibilidad: AppContainer expone este UC como container.uc_venta
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("spj.use_cases.venta")


# ── DTOs de entrada y salida ──────────────────────────────────────────────────

@dataclass
class ItemCarrito:
    producto_id:   int
    cantidad:      float
    precio_unit:   float
    nombre:        str = ""
    es_compuesto:  int = 0
    descuento:     float = 0.0

    @property
    def subtotal(self) -> float:
        return round(self.cantidad * self.precio_unit - self.descuento, 4)


@dataclass
class DatosPago:
    forma_pago:       str   = "Efectivo"
    monto_pagado:     float = 0.0
    cliente_id:       Optional[int] = None
    descuento_global: float = 0.0
    notas:            str   = ""


@dataclass
class ResultadoVenta:
    ok:            bool
    venta_id:      int        = 0
    folio:         str        = ""
    total:         float      = 0.0
    cambio:        float      = 0.0
    puntos_ganados:int        = 0
    puntos_totales:int        = 0
    nivel_cliente: str        = "Bronce"
    ticket_html:   str        = ""
    error:         str        = ""


# ── Caso de uso ───────────────────────────────────────────────────────────────

class ProcesarVentaUC:
    """
    Orquestador del flujo de venta.

    Uso desde la UI (modulos/ventas.py):
        uc = container.uc_venta
        resultado = uc.ejecutar(items, datos_pago, sucursal_id, usuario)

    Uso desde el bot WhatsApp:
        uc = ProcesarVentaUC.desde_container(container)
        resultado = uc.ejecutar(items, datos_pago, sucursal_id, "bot_wa")
    """

    def __init__(
        self,
        sales_service,
        inventory_service,
        finance_service,
        loyalty_service,
        ticket_engine,
        sync_service   = None,
        event_bus      = None,
        cfdi_service   = None,
    ):
        self._sales     = sales_service
        self._inventory = inventory_service
        self._finance   = finance_service
        self._loyalty   = loyalty_service
        self._ticket    = ticket_engine
        self._sync      = sync_service
        self._bus       = event_bus
        self._cfdi      = cfdi_service

    @classmethod
    def desde_container(cls, container) -> "ProcesarVentaUC":
        """Factory que extrae servicios del AppContainer."""
        return cls(
            sales_service     = container.sales_service,
            inventory_service = container.inventory_service,
            finance_service   = container.finance_service,
            loyalty_service   = container.loyalty_service,
            ticket_engine     = container.ticket_template_engine,
            sync_service      = getattr(container, "sync_service",   None),
            event_bus         = _get_bus(),
            cfdi_service      = getattr(container, "cfdi_service",  None),
        )

    # ── Punto de entrada principal ────────────────────────────────────────────

    def ejecutar(
        self,
        items:       List[ItemCarrito],
        datos_pago:  DatosPago,
        sucursal_id: int,
        usuario:     str,
    ) -> ResultadoVenta:
        """
        Ejecuta el flujo completo de venta de forma atómica.
        Si cualquier paso crítico falla, retorna ResultadoVenta(ok=False, error=...).
        Los pasos post-transacción (fidelidad, ticket, sync) fallan de forma blanda.
        """
        if not items:
            return ResultadoVenta(ok=False, error="El carrito está vacío.")

        # ── 1. Validar stock disponible ───────────────────────────────────────
        stock_error = self._validar_stock(items, sucursal_id)
        if stock_error:
            return ResultadoVenta(ok=False, error=stock_error)

        # ── 2. Construir payload para SalesService ────────────────────────────
        items_svc = [
            {
                "product_id":  it.producto_id,
                "qty":         it.cantidad,
                "unit_price":  it.precio_unit,
                "name":        it.nombre,
                "es_compuesto": it.es_compuesto,
            }
            for it in items
        ]
        subtotal      = round(sum(it.subtotal for it in items), 2)
        total         = round(max(subtotal - datos_pago.descuento_global, 0), 2)
        monto_pagado  = datos_pago.monto_pagado
        cambio        = round(monto_pagado - total, 2) if monto_pagado > 0 else 0.0

        # ── 3. Ejecutar venta (transacción crítica) ───────────────────────────
        try:
            # execute_sale returns (folio, ticket_html)
            result = self._sales.execute_sale(
                branch_id      = sucursal_id,
                user           = usuario,
                items          = items_svc,
                payment_method = datos_pago.forma_pago,
                amount_paid    = monto_pagado,
                client_id      = datos_pago.cliente_id,
                discount       = datos_pago.descuento_global,
                notes          = datos_pago.notas,
            )
            if isinstance(result, (tuple, list)) and len(result) >= 2:
                folio        = result[0]
                ticket_html  = result[1] if len(result) > 1 else ""
            else:
                folio        = str(result)
                ticket_html  = ""
            # Get venta_id from DB (folio is unique)
            row = self._sales.db.execute(
                "SELECT id FROM ventas WHERE folio=? ORDER BY id DESC LIMIT 1", (folio,)
            ).fetchone()
            venta_id = row[0] if row else 0
        except Exception as e:
            logger.error("ProcesarVentaUC.execute_sale: %s", e)
            return ResultadoVenta(ok=False, error=str(e))

        # ── 4. Post-venta: fidelidad ──────────────────────────────────────────
        puntos_ganados = 0
        puntos_totales = 0
        nivel_cliente  = "Bronce"
        if datos_pago.cliente_id:
            try:
                pts = self._loyalty.process_loyalty_for_sale(
                    client_id  = datos_pago.cliente_id,
                    total_sale = total,
                    branch_id  = sucursal_id,
                )
                puntos_ganados = pts.get("puntos_ganados", 0)
                puntos_totales = pts.get("puntos_totales", 0)
                nivel_cliente  = pts.get("nivel", "Bronce")
            except Exception as e:
                logger.warning("Fidelidad post-venta venta_id=%s: %s", venta_id, e)

        # ── 5. Post-venta: ticket (execute_sale ya generó uno; re-gen si no hay) ──
        if not ticket_html and self._ticket:
            try:
                ticket_html = self._ticket.generar_ticket(
                    template_db = "",
                    venta_data  = {
                        "venta_id":          venta_id,
                        "fecha":             _now(),
                        "cajero":            usuario,
                        "cliente":           "Público General",
                        "totales": {
                            "subtotal":      subtotal,
                            "descuento":     datos_pago.descuento_global,
                            "total_final":   total,
                        },
                        "efectivo_recibido": monto_pagado,
                        "cambio":            cambio,
                        "forma_pago":        datos_pago.forma_pago,
                        "puntos_ganados":    puntos_ganados,
                        "puntos_totales":    puntos_totales,
                        "items": [
                            {
                                "nombre":          it.nombre,
                                "cantidad":        it.cantidad,
                                "precio_unitario": it.precio_unit,
                                "total":           it.subtotal,
                            }
                            for it in items
                        ],
                    },
                    mensaje_psicologico = "¡Gracias por tu compra!",
                )
            except Exception as e:
                logger.warning("Ticket post-venta venta_id=%s: %s", venta_id, e)

        # ── 6. Post-venta: sync ───────────────────────────────────────────────
        if self._sync:
            try:
                self._sync.registrar_evento(
                    cursor      = None,
                    tabla       = "ventas",
                    operacion   = "INSERT",
                    registro_id = venta_id,
                    payload     = {
                        "folio":      folio,
                        "total":      total,
                        "metodo_pago": datos_pago.forma_pago,
                    },
                    sucursal_id = sucursal_id,
                )
            except Exception as e:
                logger.warning("Sync post-venta venta_id=%s: %s", venta_id, e)

        # ── 7. Publicar evento ────────────────────────────────────────────────
        if self._bus:
            try:
                self._bus.publish(
                    "VENTA_COMPLETADA",
                    {
                        "venta_id":    venta_id,
                        "folio":       folio,
                        "sucursal_id": sucursal_id,
                        "total":       total,
                        "usuario":     usuario,
                        "cliente_id":  datos_pago.cliente_id,
                        "forma_pago":  datos_pago.forma_pago,
                    },
                    async_=True,
                )
            except Exception as e:
                logger.debug("EventBus post-venta: %s", e)

        logger.info(
            "Venta %s OK — total=$%.2f puntos=%d sucursal=%s usuario=%s",
            folio, total, puntos_ganados, sucursal_id, usuario,
        )
        return ResultadoVenta(
            ok             = True,
            venta_id       = venta_id,
            folio          = folio,
            total          = total,
            cambio         = cambio,
            puntos_ganados = puntos_ganados,
            puntos_totales = puntos_totales,
            nivel_cliente  = nivel_cliente,
            ticket_html    = ticket_html,
        )

    # ── Validación de stock ───────────────────────────────────────────────────

    def _validar_stock(
        self, items: List[ItemCarrito], sucursal_id: int
    ) -> str | None:
        """Verifica stock antes de ejecutar la venta. Retorna error o None."""
        for item in items:
            if item.es_compuesto:
                continue  # inventario de combos se valida en SalesService
            try:
                disponible = self._inventory.get_stock(
                    item.producto_id, sucursal_id
                )
                if disponible < item.cantidad:
                    return (
                        f"Stock insuficiente para '{item.nombre}': "
                        f"disponible {disponible:.3f}, requerido {item.cantidad:.3f}"
                    )
            except Exception as e:
                logger.warning("Validar stock producto=%s: %s", item.producto_id, e)
        return None

    def validar_precios_bajo_costo(
        self, items: List[ItemCarrito]
    ) -> List[dict]:
        """
        Detecta ítems con precio de venta por debajo del costo.
        Retorna lista de dicts con {nombre, precio_venta, costo, perdida}.
        La UI puede usar esto para advertir al usuario sin bloquear la venta.
        """
        alertas = []
        for item in items:
            try:
                row = self._sales.db.execute(
                    "SELECT COALESCE(precio_compra, 0) FROM productos WHERE id=?",
                    (item.producto_id,)
                ).fetchone()
                costo = float(row[0]) if row and row[0] else 0.0
                if costo > 0 and item.precio_unit < costo:
                    alertas.append({
                        "nombre":       item.nombre,
                        "precio_venta": item.precio_unit,
                        "costo":        costo,
                        "perdida":      round(costo - item.precio_unit, 4),
                    })
            except Exception as e:
                logger.warning("validar_precios_bajo_costo prod=%s: %s",
                               item.producto_id, e)
        return alertas


# ── Helpers privados ──────────────────────────────────────────────────────────

def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _get_bus():
    try:
        from core.events.event_bus import get_bus
        return get_bus()
    except Exception:
        return None
