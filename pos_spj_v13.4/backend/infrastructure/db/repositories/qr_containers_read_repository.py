"""Read-only repository for the QR-containers purchasing flow (Fase A).

Extracted from modulos/compras_pro.py: container lookup, child containers, and
container products (assignment and reception views). PyQt-free, headless-testable.
Returns dict(row) so the UI's `r["col"]` access keeps working unchanged.
"""

from __future__ import annotations

import sqlite3
from typing import Any


class QrContainersReadRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        try:
            if getattr(self._connection, "row_factory", None) is None:
                self._connection.row_factory = sqlite3.Row
        except Exception:
            pass

    def _dicts(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in self._connection.execute(sql, params).fetchall()]

    def search_containers(self, query: str, *, exclude_codigo: str = "", limit: int = 50) -> list[dict[str, Any]]:
        like = f"%{query}%"
        return self._dicts(
            "SELECT id, codigo, tipo, COALESCE(descripcion,'') AS desc "
            "FROM contenedores "
            "WHERE (codigo LIKE ? OR descripcion LIKE ?) "
            "AND id != COALESCE((SELECT id FROM contenedores WHERE codigo=? LIMIT 1), -1) "
            "ORDER BY fecha_creado DESC LIMIT ?",
            (like, like, exclude_codigo, int(limit)),
        )

    def get_container_by_code(self, codigo: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT id, codigo, tipo, descripcion, estado, fecha_creado "
            "FROM contenedores WHERE codigo=?",
            (codigo,),
        ).fetchone()
        return None if row is None else dict(row)

    def get_container_code(self, container_id: str) -> str | None:
        row = self._connection.execute(
            "SELECT codigo FROM contenedores WHERE id=? LIMIT 1", (container_id,)
        ).fetchone()
        return None if row is None else row[0]

    def list_child_containers(self, parent_id: str) -> list[dict[str, Any]]:
        return self._dicts(
            "SELECT id, codigo, tipo, COALESCE(descripcion,'') AS desc "
            "FROM contenedores WHERE parent_id=? ORDER BY codigo",
            (parent_id,),
        )

    def get_container_products(self, container_id: str) -> list[dict[str, Any]]:
        return self._dicts(
            "SELECT cp.producto_id, cp.cantidad, cp.costo_unitario, "
            "p.nombre, COALESCE(p.unidad,'pz') AS unidad "
            "FROM contenedor_productos cp "
            "JOIN productos p ON p.id = cp.producto_id "
            "WHERE cp.contenedor_id=?",
            (container_id,),
        )

    def get_container_for_reception(self, codigo: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT c.id, c.codigo, c.tipo, c.estado, c.total, c.folio_factura, "
            "c.comprador, COALESCE(p.nombre,'(sin proveedor)') AS proveedor "
            "FROM contenedores c LEFT JOIN proveedores p ON p.id = c.proveedor_id "
            "WHERE c.codigo=?",
            (codigo,),
        ).fetchone()
        return None if row is None else dict(row)

    def get_container_products_for_reception(self, container_id: str) -> list[dict[str, Any]]:
        return self._dicts(
            "SELECT cp.producto_id, cp.cantidad, cp.costo_unitario, "
            "COALESCE(cp.cantidad_recibida, cp.cantidad) AS recibida, "
            "p.nombre, COALESCE(p.unidad,'pz') AS unidad "
            "FROM contenedor_productos cp "
            "JOIN productos p ON p.id = cp.producto_id "
            "WHERE cp.contenedor_id=?",
            (container_id,),
        )
