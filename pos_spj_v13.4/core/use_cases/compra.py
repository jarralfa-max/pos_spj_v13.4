# core/use_cases/compra.py — SPJ POS v13.5
"""
Caso de uso: Procesar Compra

Orquesta el flujo completo de recepción de mercancía:
  1. Validar items (cantidad > 0, proveedor_id set)
  2. Registrar compra + entrada de stock (PurchaseService — SAVEPOINT)
  3. Asiento contable inventario/CxP  [1201/2101] (FinanceService)
  4. Asiento pago contado CxP/Caja    [2101/1101] (si forma_pago != CREDITO)
  5. Crear CxP en accounts_payable    (si queda deuda)
  6. Publicar COMPRA_REGISTRADA al EventBus

Brecha que cierra: PurchaseService ya maneja DB + inventario pero nunca llama
registrar_asiento() para el asiento de entrada de mercancía (1201/2101).
Este UC agrega ese paso sin tocar PurchaseService.

Acceso desde AppContainer: container.uc_compra
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("spj.use_cases.compra")


# ── DTOs ─────────────────────────────────────────────────────────────────────

@dataclass
class ItemCompra:
    producto_id: int
    nombre:      str
    cantidad:    float
    costo_unit:  float

    @property
    def subtotal(self) -> float:
        return round(self.cantidad * self.costo_unit, 4)


@dataclass
class DatosCompra:
    proveedor_id:       int
    forma_pago:         str   = "CONTADO"
    monto_pagado:       float = 0.0
    notas:              str   = ""
    referencia_factura: str   = ""


@dataclass
class ResultadoCompra:
    ok:         bool
    compra_id:  int   = 0
    folio:      str   = ""
    total:      float = 0.0
    asiento_id: int   = 0
    ap_id:      int   = 0
    error:      str   = ""


# ── Caso de uso ───────────────────────────────────────────────────────────────

class ProcesarCompraUC:
    """
    Orquestador del flujo de recepción de mercancía.

    Uso desde AppContainer:
        uc = container.uc_compra
        resultado = uc.ejecutar(items, datos, sucursal_id, usuario)
    """

    def __init__(
        self,
        purchase_service,
        finance_service,
        inventory_service,
        event_bus=None,
    ):
        self._purchase  = purchase_service
        self._finance   = finance_service
        self._inventory = inventory_service
        self._bus       = event_bus

    @classmethod
    def desde_container(cls, container) -> "ProcesarCompraUC":
        from core.events.event_bus import EventBus
        return cls(
            purchase_service  = container.purchase_service,
            finance_service   = container.finance_service,
            inventory_service = container.inventory_service,
            event_bus         = EventBus(),
        )

    # ── Punto de entrada ─────────────────────────────────────────────────────

    def ejecutar(
        self,
        items:       List[ItemCompra],
        datos:       DatosCompra,
        sucursal_id: int,
        usuario:     str,
    ) -> ResultadoCompra:
        """
        Ejecuta el flujo completo de compra.
        PurchaseService maneja la transacción DB; este UC agrega los asientos
        contables que faltaban en ese flujo.
        """
        # ── 1. Validar ───────────────────────────────────────────────────────
        if not items:
            return ResultadoCompra(ok=False, error="La compra no tiene items.")
        for it in items:
            if it.cantidad <= 0:
                return ResultadoCompra(
                    ok=False,
                    error=f"Cantidad inválida para '{it.nombre}': {it.cantidad}",
                )
        if not datos.proveedor_id:
            return ResultadoCompra(ok=False, error="proveedor_id es obligatorio.")

        total = round(sum(it.subtotal for it in items), 2)

        # ── 2. Registrar compra + inventario (crítico) ───────────────────────
        items_svc = [
            {
                "product_id": it.producto_id,
                "qty":        it.cantidad,
                "unit_cost":  it.costo_unit,
                "nombre":     it.nombre,
            }
            for it in items
        ]
        try:
            folio = self._purchase.register_purchase(
                provider_id    = datos.proveedor_id,
                branch_id      = sucursal_id,
                user           = usuario,
                items          = items_svc,
                payment_method = datos.forma_pago,
                amount_paid    = datos.monto_pagado,
                notes          = datos.notas,
            )
        except Exception as exc:
            logger.error("ProcesarCompraUC.register_purchase: %s", exc)
            return ResultadoCompra(ok=False, error=str(exc))

        # Recuperar compra_id por folio
        compra_id = 0
        try:
            row = self._purchase.db.execute(
                "SELECT id FROM compras WHERE folio=? ORDER BY id DESC LIMIT 1",
                (folio,),
            ).fetchone()
            compra_id = row[0] if row else 0
        except Exception:
            pass

        # ── 3. Asiento inventario/CxP  [1201 / 2101] ────────────────────────
        asiento_id = 0
        try:
            asiento_id = self._finance.registrar_asiento(
                debe         = "1201",
                haber        = "2101",
                concepto     = f"Entrada mercancía {folio}",
                monto        = total,
                modulo       = "compras",
                referencia_id= compra_id,
                evento       = "COMPRA_INVENTARIO",
                sucursal_id  = sucursal_id,
            )
        except Exception as exc:
            logger.warning("ProcesarCompraUC asiento 1201/2101: %s", exc)

        # ── 4. Asiento pago contado  [2101 / 1101] ──────────────────────────
        ap_id = 0
        if datos.forma_pago != "CREDITO" and datos.monto_pagado > 0:
            try:
                self._finance.registrar_asiento(
                    debe         = "2101",
                    haber        = "1101",
                    concepto     = f"Pago contado compra {folio}",
                    monto        = min(datos.monto_pagado, total),
                    modulo       = "compras",
                    referencia_id= compra_id,
                    evento       = "PAGO_COMPRA_CONTADO",
                    sucursal_id  = sucursal_id,
                )
            except Exception as exc:
                logger.warning("ProcesarCompraUC asiento pago contado: %s", exc)

        # ── 5. Crear CxP si queda deuda ──────────────────────────────────────
        deuda = round(total - datos.monto_pagado, 2)
        if deuda > 0 and hasattr(self._finance, "crear_cxp"):
            try:
                ap_id = self._finance.crear_cxp(
                    supplier_id  = datos.proveedor_id,
                    concepto     = f"Compra {folio}",
                    amount       = deuda,
                    due_date     = None,
                    referencia   = folio,
                    ref_type     = "compra",
                    usuario      = usuario,
                )
            except Exception as exc:
                logger.warning("ProcesarCompraUC crear_cxp: %s", exc)

        # ── 6. Publicar evento ───────────────────────────────────────────────
        if self._bus:
            try:
                from core.events.event_bus import COMPRA_REGISTRADA
                self._bus.publish(
                    COMPRA_REGISTRADA,
                    {
                        "compra_id":   compra_id,
                        "folio":       folio,
                        "total":       total,
                        "proveedor_id":datos.proveedor_id,
                        "sucursal_id": sucursal_id,
                        "usuario":     usuario,
                    },
                    async_=True,
                )
            except Exception as exc:
                logger.warning("ProcesarCompraUC publish: %s", exc)

        return ResultadoCompra(
            ok=True,
            compra_id=compra_id,
            folio=folio,
            total=total,
            asiento_id=asiento_id,
            ap_id=ap_id,
        )
