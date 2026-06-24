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
