"""
application/purchases/receive_po_adapter.py
─────────────────────────────────────────────
Phase 4 — Adaptador de Recepción de PO.

Permite que la pestaña de Recepción/QR reciba una PO iniciada desde
Compra Tradicional, usando los servicios de inventario existentes sin
duplicar lógica de QR, transferencias ni kardex.

RUTA DE RECEPCIÓN PO:
    UI Recepción → ReceivePOAdapter
                     → inventory_service.add_stock()    (existente)
                     → lote_service.registrar_lote()    (existente, opcional)
                     → purchase_order_repo.update_*()   (estado PO)
                     → purchase_service.register_purchase() (registra compra con po_id)
                     → EventBus RECEPCION_CONFIRMADA    (existente)

REGLAS:
  - NO reimplementa inventario, lotes ni QR
  - NO duplica movimientos de inventario
  - La PO debe estar en estado ABIERTA o PARCIAL para poder recibir
  - Recepción parcial → PO.estado = PARCIAL
  - Recepción completa (todas las líneas ≥ qty esperada) → PO.estado = RECIBIDA
  - Se crea un registro en 'compras' con purchase_order_id para trazabilidad
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("spj.purchases.receive_po_adapter")

# PO states that allow receiving
_RECEIVABLE_STATES = {"ABIERTA", "PARCIAL", "borrador", "pendiente"}


@dataclass
class ReceiptItem:
    """Un item recibido físicamente contra una línea de PO."""
    product_id:      int
    qty_received:    float
    unit_cost:       float
    nombre:          str   = ""
    lote:            str   = ""
    fecha_caducidad: str   = ""
    notas:           str   = ""


@dataclass
class ReceiptResult:
    ok:          bool
    folio:       str  = ""       # folio de compra creada
    po_id:       int  = 0
    po_estado:   str  = ""
    completion:  float = 0.0     # 0.0–1.0, fracción recibida de la PO
    warnings:    list[str] = field(default_factory=list)
    error:       str  = ""


class ReceivePOAdapter:
    """
    Adaptador mínimo para recibir una PO desde la pestaña de Recepción.

    Dependencias inyectadas (no hardcodeadas):
        purchase_order_repo  — PurchaseOrderRepository
        purchase_service     — PurchaseService (registro contable)
        inventory_service    — UnifiedInventoryService.add_stock()
        lote_service         — LoteService.registrar_lote() (opcional)
        event_bus            — EventBus (RECEPCION_CONFIRMADA)
    """

    def __init__(self, container: Any):
        self._container = container

    # ── API pública ───────────────────────────────────────────────────────────

    def get_po_lines(self, po_id: int) -> list[dict]:
        """
        Devuelve las líneas esperadas de la PO con progreso de recepción.
        Usado por la UI para mostrar comparación esperado vs recibido.
        """
        repo = self._po_repo()
        if not repo:
            return []
        po = repo.get_by_id(po_id)
        if not po:
            return []
        return [
            {
                "producto_id":     item.get("producto_id") or item.get("product_id"),
                "nombre":          item.get("nombre", ""),
                "cantidad":        item.get("cantidad", 0),
                "recibido":        item.get("recibido", 0),
                "pendiente":       max(0.0, item.get("cantidad", 0) - item.get("recibido", 0)),
                "precio_unitario": item.get("precio_unitario", 0),
                "unidad":          item.get("unidad", "kg"),
                "lote":            item.get("lote", ""),
            }
            for item in po.get("items", [])
        ]

    def get_po_status(self, po_id: int) -> str:
        """Estado actual de la PO."""
        repo = self._po_repo()
        if not repo:
            return ""
        po = repo.get_by_id(po_id)
        return po["estado"] if po else ""

    def register_partial_receipt(
        self,
        po_id: int,
        received_items: list[ReceiptItem],
        usuario: str,
        sucursal_id: int,
        proveedor_id: int,
        metodo_pago: str = "CREDITO",
    ) -> ReceiptResult:
        """
        Registra la recepción física (parcial o total) de una PO.

        Flujo:
          1. Valida que la PO existe y está en estado recibible
          2. Para cada item recibido → inventory_service.add_stock()
          3. Para cada item con lote → lote_service.registrar_lote() (si disponible)
          4. Actualiza recibido en ordenes_compra_items
          5. Recalcula completion ratio → actualiza estado PO (PARCIAL/RECIBIDA)
          6. Crea registro en 'compras' con purchase_order_id (trazabilidad)
          7. Publica RECEPCION_CONFIRMADA en EventBus
        """
        po_repo = self._po_repo()
        if not po_repo:
            return ReceiptResult(ok=False, error="purchase_order_repo no disponible.")

        # ── 1. Validar PO ─────────────────────────────────────────────────────
        po = po_repo.get_by_id(po_id)
        if not po:
            return ReceiptResult(ok=False, error=f"PO {po_id} no encontrada.")
        if po["estado"] not in _RECEIVABLE_STATES:
            return ReceiptResult(
                ok=False,
                error=f"PO {po_id} no está en estado recibible. Estado: {po['estado']}",
            )
        if not received_items:
            return ReceiptResult(ok=False, error="No hay items para recibir.")

        operation_id = str(uuid.uuid4())
        warnings: list[str] = []

        # ── 2 + 3. Inventario + Lotes ─────────────────────────────────────────
        inv_svc   = getattr(self._container, "inventory_service", None)
        lote_svc  = getattr(self._container, "lote_service", None)

        for item in received_items:
            if item.qty_received <= 0:
                continue
            # add_stock — punto único de afectación de inventario
            if inv_svc:
                try:
                    inv_svc.add_stock(
                        product_id=item.product_id,
                        branch_id=sucursal_id,
                        qty=item.qty_received,
                        unit_cost=item.unit_cost,
                        reference_type="COMPRA_PO",
                        reference_id=str(po_id),
                        operation_id=f"{operation_id}_{item.product_id}",
                        user=usuario,
                        notes=f"Recepción PO {po.get('folio', po_id)}",
                    )
                except Exception as e:
                    logger.error("add_stock prod=%d: %s", item.product_id, e)
                    warnings.append(f"Inventario prod {item.product_id}: {e}")

            # registrar_lote — opcional, solo si viene lote en el item
            if lote_svc and item.lote:
                try:
                    lote_svc.registrar_lote(
                        producto_id=item.product_id,
                        peso_kg=item.qty_received,
                        fecha_caducidad=item.fecha_caducidad or None,
                        proveedor_id=proveedor_id,
                        numero_lote=item.lote,
                        costo_kg=item.unit_cost,
                    )
                except Exception as e:
                    logger.warning("registrar_lote prod=%d lote=%s: %s",
                                   item.product_id, item.lote, e)
                    warnings.append(f"Lote {item.lote}: {e}")

            # ── 4. Actualizar recibido en PO ──────────────────────────────────
            try:
                po_repo.update_item_received(
                    po_id=po_id,
                    producto_id=item.product_id,
                    qty_received=item.qty_received,
                )
            except Exception as e:
                logger.warning("update_item_received: %s", e)

        # ── 5. Calcular completion y actualizar estado PO ──────────────────────
        completion = po_repo.compute_po_completion(po_id)
        nuevo_estado_po = "RECIBIDA" if completion >= 1.0 else "PARCIAL"
        po_repo.update_estado(po_id, nuevo_estado_po)

        # ── 6. Crear registro en 'compras' con purchase_order_id ───────────────
        folio = ""
        purchase_svc = getattr(self._container, "purchase_service", None)
        if purchase_svc:
            try:
                items_svc = [
                    {
                        "product_id": i.product_id,
                        "qty":        i.qty_received,
                        "unit_cost":  i.unit_cost,
                        "nombre":     i.nombre,
                    }
                    for i in received_items if i.qty_received > 0
                ]
                total = sum(i["qty"] * i["unit_cost"] for i in items_svc)
                folio, fin_warnings = purchase_svc.register_purchase(
                    provider_id=proveedor_id,
                    branch_id=sucursal_id,
                    user=usuario,
                    items=items_svc,
                    payment_method=metodo_pago,
                    amount_paid=0.0 if metodo_pago == "CREDITO" else total,
                    notes=f"Recepción PO {po.get('folio', po_id)}",
                )
                warnings.extend(fin_warnings)
                # Vincular compra con PO
                self._link_compra_po(folio, po_id)
            except Exception as e:
                logger.error("register_purchase desde PO %d: %s", po_id, e)
                warnings.append(f"Registro contable: {e}")

        # ── 7. Publicar RECEPCION_CONFIRMADA ──────────────────────────────────
        self._publish_recepcion(po_id, po.get("folio", ""), folio, usuario,
                                sucursal_id, completion)

        return ReceiptResult(
            ok=True,
            folio=folio,
            po_id=po_id,
            po_estado=nuevo_estado_po,
            completion=completion,
            warnings=warnings,
        )

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _po_repo(self):
        return getattr(self._container, "purchase_order_repo", None)

    def _link_compra_po(self, folio: str, po_id: int) -> None:
        """Vincula la compra recién creada con la PO en la tabla compras."""
        try:
            db = getattr(self._container, "db", None)
            if db and folio:
                db.execute(
                    "UPDATE compras SET purchase_order_id=? WHERE folio=?",
                    (po_id, folio),
                )
        except Exception as e:
            logger.debug("_link_compra_po: %s", e)

    def _publish_recepcion(self, po_id: int, po_folio: str, compra_folio: str,
                            usuario: str, sucursal_id: int, completion: float) -> None:
        try:
            from core.events.event_bus import get_bus, RECEPCION_CONFIRMADA
            bus = get_bus()
            bus.publish(RECEPCION_CONFIRMADA, {
                "po_id":         po_id,
                "po_folio":      po_folio,
                "compra_folio":  compra_folio,
                "usuario":       usuario,
                "sucursal_id":   sucursal_id,
                "completion":    completion,
                "source":        "PO",
            })
        except Exception as e:
            logger.debug("publish RECEPCION_CONFIRMADA: %s", e)
