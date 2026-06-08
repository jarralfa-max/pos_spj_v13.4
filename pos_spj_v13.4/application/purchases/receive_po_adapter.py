"""
application/purchases/receive_po_adapter.py
─────────────────────────────────────────────
Phase 4 — Adaptador de Recepción de PO.

Permite que la pestaña de Recepción/QR reciba una PO iniciada desde
Compra Tradicional, usando los servicios de inventario existentes sin
duplicar lógica de QR, transferencias ni kardex.

RUTA DE RECEPCIÓN PO:
    UI Recepción → ReceivePOAdapter
                     → inventory_service.increase_stock()    (existente)
                     → lote_service.registrar_lote()    (existente, opcional)
                     → purchase_order_repo.update_*()   (estado PO)
                     → PurchaseRepository.create_purchase() (trazabilidad sin stock)
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
        purchase_repo        — PurchaseRepository opcional (trazabilidad, sin stock)
        inventory_service    — InventoryApplicationService.increase_stock()
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
          2. Para cada item recibido → inventory_service.increase_stock()
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
        container_attrs = getattr(self._container, "__dict__", {})
        inv_svc = container_attrs.get("inventory_application_service")
        if inv_svc is None:
            inv_svc = container_attrs.get("inventory_service") or getattr(self._container, "inventory_service", None)
        lote_svc = container_attrs.get("lote_service") or getattr(self._container, "lote_service", None)

        for item in received_items:
            if item.qty_received <= 0:
                continue
            # increase_stock — ruta canónica de afectación de inventario
            if inv_svc:
                try:
                    inventory_result = inv_svc.increase_stock(
                        product_id=int(item.product_id),
                        branch_id=int(sucursal_id),
                        quantity=float(item.qty_received),
                        unit="unit",
                        reason=f"Recepción PO {po.get('folio', po_id)}",
                        operation_id=f"{operation_id}:{item.product_id}",
                        source_module="purchase_reception",
                        reference_type="PURCHASE_ORDER_RECEIPT",
                        reference_id=str(po_id),
                        user_name=usuario or "system",
                    )
                    if not getattr(inventory_result, "success", False):
                        raise RuntimeError(getattr(inventory_result, "message", "PURCHASE_RECEPTION_INVENTORY_FAILED"))
                except Exception as e:
                    logger.error("increase_stock prod=%d: %s", item.product_id, e)
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
        # Fase 6: NO usar el servicio de compra directa desde una ruta PO.
        # Ese servicio vuelve a afectar inventario/lotes/finanzas; aquí el stock
        # ya fue recibido arriba por inventory_service.increase_stock().
        folio = self._create_receipt_purchase_record(
            po=po,
            po_id=po_id,
            items=received_items,
            proveedor_id=proveedor_id,
            sucursal_id=sucursal_id,
            usuario=usuario,
            metodo_pago=metodo_pago,
            warnings=warnings,
        )
        if folio:
            self._link_compra_po(folio, po_id)

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

    def _purchase_repo(self):
        # MagicMock containers fabricate attributes on getattr(); read __dict__
        # first so an unconfigured mock does not masquerade as a repository.
        repo = getattr(self._container, "__dict__", {}).get("purchase_repo")
        if repo is not None:
            return repo
        db = getattr(self._container, "db", None)
        if db is None:
            return None
        from repositories.purchase_repository import PurchaseRepository
        return PurchaseRepository(db)

    def _create_receipt_purchase_record(
        self, po: dict, po_id: int, items: list[ReceiptItem], proveedor_id: int,
        sucursal_id: int, usuario: str, metodo_pago: str, warnings: list[str],
    ) -> str:
        """Crea cabecera/partidas de compra para trazabilidad de recepción PO.

        No llama el servicio de compra directa: el inventario ya fue
        afectado una sola vez por esta ruta de recepción física.
        """
        repo = self._purchase_repo()
        if repo is None:
            warnings.append("Compra trazabilidad: purchase_repo no disponible")
            return ""
        items_repo = [
            {
                "product_id": i.product_id,
                "qty": i.qty_received,
                "unit_cost": i.unit_cost,
                "nombre": i.nombre,
            }
            for i in items if i.qty_received > 0
        ]
        if not items_repo:
            return ""
        total = round(sum(i["qty"] * i["unit_cost"] for i in items_repo), 2)
        try:
            _compra_id, folio = repo.create_purchase(
                provider_id=proveedor_id,
                branch_id=sucursal_id,
                user=usuario,
                subtotal=total,
                tax=0.0,
                total=total,
                status="credito" if metodo_pago == "CREDITO" else "completada",
                notes=f"Recepción PO {po.get('folio', po_id)}",
                payment_method=metodo_pago,
            )
            try:
                repo.save_purchase_items(_compra_id, items_repo)
            except Exception as e:
                logger.warning("save_purchase_items recepción PO %d: %s", po_id, e)
                warnings.append(f"Partidas compra PO: {e}")
            return folio
        except Exception as e:
            logger.error("create_purchase recepción PO %d: %s", po_id, e)
            warnings.append(f"Compra trazabilidad: {e}")
            return ""

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
