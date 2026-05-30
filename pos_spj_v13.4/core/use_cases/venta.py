# core/use_cases/venta.py — SPJ POS v13.1
"""
Caso de uso: Procesar Venta

Orquesta el flujo completo:
  1. Validar items y stock
  2. Ejecutar venta (SalesService)
  3. Convertir respuesta a ResultadoVenta

Nota Fase 4:
- UC NO publica VENTA_COMPLETADA.
- UC NO acredita fidelidad.
- UC NO registra sync.
- Los efectos post-venta viven en SalesService + handlers.

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
from typing import Any, Dict, List, Optional

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
    puntos_canjeados: int   = 0
    descuento_puntos: float = 0.0
    notas:            str   = ""
    sucursal_id:      Optional[int] = None
    usuario:          str = ""
    operation_id:     str = ""
    descuento_lineas: float = 0.0
    mercado_pago_ref: str = ""
    pago_mixto:       Dict[str, float] = field(default_factory=dict)
    payment_breakdown: Dict[str, float] = field(default_factory=dict)
    total_pagado:     float = 0.0
    reserva_id:       Optional[int] = None

    def __post_init__(self) -> None:
        self.forma_pago = _normalize_payment_label(self.forma_pago)
        self.monto_pagado = float(self.monto_pagado or 0.0)
        self.total_pagado = float(self.total_pagado or self.monto_pagado or 0.0)
        self.descuento_global = float(self.descuento_global or 0.0)
        self.descuento_lineas = float(self.descuento_lineas or 0.0)
        self.puntos_canjeados = int(self.puntos_canjeados or 0)
        self.descuento_puntos = float(self.descuento_puntos or 0.0)
        self.pago_mixto = {str(k): float(v or 0.0) for k, v in (self.pago_mixto or {}).items()}
        self.payment_breakdown = {str(k): float(v or 0.0) for k, v in (self.payment_breakdown or self.pago_mixto or {}).items()}


@dataclass
class ClienteVentaDTO:
    cliente_id: Optional[int] = None
    nombre: str = ""
    telefono: str = ""
    email: str = ""
    saldo_credito: float = 0.0
    puntos: int = 0
    nivel: str = ""


@dataclass
class PaymentBreakdown:
    metodo: str = "Efectivo"
    total: float = 0.0
    recibido: float = 0.0
    cambio: float = 0.0
    pendiente: float = 0.0
    lineas: Dict[str, float] = field(default_factory=dict)
    mercado_pago_ref: str = ""
    operation_id: str = ""


@dataclass
class LoyaltyRedemptionRequest:
    cliente_id: Optional[int] = None
    puntos: int = 0
    subtotal: float = 0.0
    operation_id: str = ""


@dataclass
class LoyaltyRedemptionPreview:
    cliente_id: Optional[int] = None
    puntos_solicitados: int = 0
    puntos_aplicables: int = 0
    descuento_aplicable: float = 0.0
    subtotal: float = 0.0
    total_estimado: float = 0.0
    mensaje: str = ""


@dataclass
class SaleContext:
    items: List[ItemCarrito] = field(default_factory=list)
    datos_pago: DatosPago = field(default_factory=DatosPago)
    cliente: ClienteVentaDTO = field(default_factory=ClienteVentaDTO)
    payment_breakdown: PaymentBreakdown = field(default_factory=PaymentBreakdown)
    loyalty_redemption: LoyaltyRedemptionRequest = field(default_factory=LoyaltyRedemptionRequest)
    sucursal_id: int = 0
    usuario: str = ""
    notas: str = ""
    operation_id: str = ""


@dataclass
class ResultadoVenta:
    ok:            bool
    venta_id:      int        = 0
    folio:         str        = ""
    total:         float      = 0.0
    cambio:        float      = 0.0
    puntos_ganados:Optional[int] = None
    puntos_totales:Optional[int] = None
    nivel_cliente: Optional[str] = None
    ticket_html:   str        = ""
    error:         str        = ""
    operation_id:  str        = ""
    ticket_payload: Dict       = field(default_factory=dict)
    payment_breakdown: Dict    = field(default_factory=dict)
    loyalty_result: Dict       = field(default_factory=dict)
    warnings: List[str]        = field(default_factory=list)


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

        # ── 2. Normalizar método de pago sin perder estructura ────────────────
        from core.services.payment_normalization import normalize_payment_method as _npm
        datos_pago.forma_pago = _npm(datos_pago.forma_pago)
        # ── Construir payload para SalesService ──────────────────────────────
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
        warnings: List[str] = []
        ticket_payload: Dict = {}
        payment_breakdown: Dict = {}
        loyalty_result: Dict = {}
        operation_id: str = ""

        try:
            if hasattr(self._sales, "execute_sale_result"):
                rich = self._sales.execute_sale_result(
                    branch_id=sucursal_id,
                    user=usuario,
                    items=items_svc,
                    payment_method=datos_pago.forma_pago,
                    amount_paid=monto_pagado,
                    payment_breakdown=dict(datos_pago.payment_breakdown or datos_pago.pago_mixto or {}),
                    client_id=datos_pago.cliente_id,
                    discount=datos_pago.descuento_global,
                    loyalty_redemption_pts=int(datos_pago.puntos_canjeados or 0),
                    notes=datos_pago.notas,
                    reservation_id=datos_pago.reserva_id,
                )
                folio = rich.folio
                ticket_html = rich.ticket_html
                venta_id = int(rich.venta_id or 0)
                total = float(rich.total or total)
                operation_id = str(getattr(rich, "operation_id", "") or "")
                ticket_payload = dict(getattr(rich, "ticket_payload", {}) or {})
                _payment = getattr(rich, "payment", None)
                if _payment is not None:
                    payment_breakdown = {
                        "forma_pago": getattr(_payment, "forma_pago", getattr(_payment, "method", "")),
                        "total_pagado": float(getattr(_payment, "total_pagado", getattr(_payment, "amount_paid", 0.0)) or 0.0),
                        "efectivo_recibido": float(getattr(_payment, "efectivo_recibido", 0.0) or 0.0),
                        "tarjeta": float(getattr(_payment, "tarjeta", 0.0) or 0.0),
                        "transferencia": float(getattr(_payment, "transferencia", 0.0) or 0.0),
                        "credito": float(getattr(_payment, "credito", 0.0) or 0.0),
                        "mercado_pago": float(getattr(_payment, "mercado_pago", 0.0) or 0.0),
                        "cambio": float(getattr(_payment, "cambio", getattr(_payment, "change", 0.0)) or 0.0),
                        "saldo_credito": float(getattr(_payment, "saldo_credito", 0.0) or 0.0),
                        "amount_paid": float(getattr(_payment, "amount_paid_real", getattr(_payment, "amount_paid", 0.0)) or 0.0),
                        "amount_paid_real": float(getattr(_payment, "amount_paid_real", getattr(_payment, "amount_paid", 0.0)) or 0.0),
                        "lineas": dict(getattr(_payment, "lineas", getattr(_payment, "breakdown", {})) or {}),
                        "breakdown": dict(getattr(_payment, "lineas", getattr(_payment, "breakdown", {})) or {}),
                    }
                _loyalty = getattr(rich, "loyalty", None)
                if _loyalty is not None:
                    loyalty_result = {
                        "cliente_id": getattr(_loyalty, "cliente_id", None),
                        "puntos_canjeados": int(getattr(_loyalty, "puntos_canjeados", 0) or 0),
                        "descuento_puntos": float(getattr(_loyalty, "descuento_puntos", 0.0) or 0.0),
                        "puntos_ganados": getattr(_loyalty, "puntos_ganados", None),
                        "puntos_totales": getattr(_loyalty, "puntos_totales", None),
                        "nivel": getattr(_loyalty, "nivel", None),
                        "available": bool(getattr(_loyalty, "available", False)),
                        "mensaje": str(getattr(_loyalty, "mensaje", "") or ""),
                        "operation_id": str(getattr(_loyalty, "operation_id", "") or ""),
                    }
                warnings.extend(list(getattr(rich, "warnings", []) or []))
            else:
                raise RuntimeError("Ruta legacy SalesService.execute_sale bloqueada: use execute_sale_result")

            puntos_ganados = loyalty_result.get("puntos_ganados") if loyalty_result else None
            puntos_totales = loyalty_result.get("puntos_totales") if loyalty_result else None
            nivel_cliente = loyalty_result.get("nivel") if loyalty_result else None
            if datos_pago.cliente_id and self._loyalty and getattr(self._loyalty, "enabled", True):
                if puntos_totales in (None, "") or not (loyalty_result or {}).get("available", False):
                    try:
                        puntos_totales = int(self._loyalty.saldo(datos_pago.cliente_id))
                        loyalty_result = dict(loyalty_result or {})
                        loyalty_result["puntos_totales"] = puntos_totales
                        loyalty_result["available"] = True
                        warnings.append("loyalty_result_incomplete_saldo_consultado")
                    except Exception as _ly_exc:
                        warnings.append("loyalty_balance_unavailable")
                        logger.warning("Loyalty saldo unavailable cliente=%s: %s", datos_pago.cliente_id, _ly_exc)
        except Exception as e:
            logger.error("ProcesarVentaUC.execute_sale: %s", e)
            return ResultadoVenta(ok=False, error=str(e))

        # ── 4. Post-venta: fidelidad ──────────────────────────────────────────
        # Fase 2: la acreditación ocurre exclusivamente en wiring.py -> loyalty_venta
        # al recibir VENTA_COMPLETADA. El UC no acredita puntos directamente.
        puntos_ganados = locals().get("puntos_ganados", None)
        puntos_totales = locals().get("puntos_totales", None)
        nivel_cliente  = locals().get("nivel_cliente", None)

        # ── 5. Post-venta: ticket ──────────────────────────────────────────
        # El UC no reconstruye tickets desde items de entrada. La única fuente
        # válida es SalesService/SaleExecutionResult.ticket_payload.
        if not ticket_payload:
            ticket_html = ""
            warnings.append("ticket_html_missing_from_sales_service")

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
            operation_id   = operation_id,
            ticket_payload = ticket_payload,
            payment_breakdown = payment_breakdown,
            loyalty_result = loyalty_result,
            warnings       = warnings,
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


def _normalize_payment_label(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Efectivo"
    key = raw.lower()
    aliases = {
        "efectivo": "Efectivo",
        "cash": "Efectivo",
        "tarjeta": "Tarjeta",
        "card": "Tarjeta",
        "transferencia": "Transferencia",
        "transfer": "Transferencia",
        "credito": "Crédito",
        "crédito": "Crédito",
        "credito normalizado": "Crédito",
        "mixto": "Mixto",
        "pago mixto": "Mixto",
        "mercadopago": "Mercado Pago",
        "mercado pago": "Mercado Pago",
    }
    return aliases.get(key, raw)
