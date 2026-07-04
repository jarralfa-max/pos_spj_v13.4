"""Write repository for the QR-containers purchasing flow (Fase A).

Extracted from modulos/compras_pro.py: container generation and assignment
writes. PyQt-free. Executes statements only — it does NOT commit/rollback; the
calling application service / UI drives the transaction via ConnectionUnitOfWork
(REGLA: repositories must not own transactions).
"""

from __future__ import annotations

from typing import Any, Iterable


class ComprasWriteRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def insert_container(
        self, *, codigo: str, tipo: str, descripcion: str | None,
        usuario_creado: str, parent_id: Any, sucursal_destino: Any,
        observaciones: str | None,
    ) -> None:
        self._connection.execute(
            "INSERT INTO contenedores "
            "(codigo, tipo, descripcion, estado, usuario_creado, parent_id, "
            "sucursal_destino, observaciones) "
            "VALUES (?,?,?,'generado',?,?,?,?)",
            (codigo, tipo, descripcion, usuario_creado, parent_id,
             sucursal_destino, observaciones),
        )

    def assign_container(
        self, container_id: Any, *, proveedor_id: Any, comprador: str | None,
        folio_factura: str | None, fecha_factura: str | None, metodo_pago: str,
        forma_pago: str, plazo_dias: int, vence_pago: str | None,
        sucursal_destino: Any, total: float, usuario_asign: str,
    ) -> None:
        self._connection.execute(
            "UPDATE contenedores SET "
            "proveedor_id=?, comprador=?, folio_factura=?, fecha_factura=?, "
            "metodo_pago=?, forma_pago=?, plazo_dias=?, vence_pago=?, "
            "sucursal_destino=?, total=?, estado='asignado', "
            "fecha_asignado=CURRENT_TIMESTAMP, usuario_asign=? WHERE id=?",
            (proveedor_id, comprador, folio_factura, fecha_factura, metodo_pago,
             forma_pago, int(plazo_dias), vence_pago, sucursal_destino, total,
             usuario_asign, container_id),
        )

    def replace_container_products(self, container_id: Any, items: Iterable[dict]) -> None:
        """Atomically replace a container's product lines (DELETE then re-INSERT).

        Must run inside a UnitOfWork so the delete+insert commit together."""
        self._connection.execute(
            "DELETE FROM contenedor_productos WHERE contenedor_id=?", (container_id,)
        )
        for it in items:
            self._connection.execute(
                "INSERT INTO contenedor_productos "
                "(contenedor_id, producto_id, cantidad, costo_unitario) VALUES (?,?,?,?)",
                (container_id, it["producto_id"], float(it["cantidad"]), float(it["costo"])),
            )

    # ── reception ───────────────────────────────────────────────────────────────
    def mark_container_received(
        self, container_id: Any, *, estado: str, usuario_recibe: str,
        recibido_por: str, observaciones: str | None,
    ) -> None:
        self._connection.execute(
            "UPDATE contenedores SET estado=?, fecha_recibido=CURRENT_TIMESTAMP, "
            "usuario_recibe=?, recibido_por=?, observaciones=? WHERE id=?",
            (estado, usuario_recibe, recibido_por, observaciones, container_id),
        )

    def set_received_quantity(self, container_id: Any, producto_id: Any, cantidad_recibida: float) -> None:
        self._connection.execute(
            "UPDATE contenedor_productos SET cantidad_recibida=? "
            "WHERE contenedor_id=? AND producto_id=?",
            (cantidad_recibida, container_id, producto_id),
        )

    def increase_product_stock(self, producto_id: Any, delta: float) -> None:
        """Raw stock increment used by container reception. NOTE: this bypasses
        movimientos_inventario; routing it through the canonical inventory service
        is a follow-up (regla 12) — kept behaviour-preserving for Fase A."""
        self._connection.execute(
            "UPDATE productos SET existencia=COALESCE(existencia,0)+? WHERE id=?",
            (delta, producto_id),
        )

    def update_purchase_status(self, purchase_id: Any, estado: str) -> None:
        self._connection.execute(
            "UPDATE compras SET estado=? WHERE id=?", (estado, purchase_id)
        )

    def update_purchase_status_by_folio(self, folio: str, estado: str) -> None:
        self._connection.execute(
            "UPDATE compras SET estado=? WHERE folio=?", (estado, folio)
        )

    def decrease_product_stock(self, producto_id: Any, qty: float) -> None:
        """Raw stock decrement — legacy fallback for recipe consumption when the
        inventory service is unavailable. Routing through the canonical service is
        the preferred path (regla 12); kept behaviour-preserving for Fase A."""
        self._connection.execute(
            "UPDATE productos SET existencia=existencia-? WHERE id=?", (qty, producto_id)
        )

