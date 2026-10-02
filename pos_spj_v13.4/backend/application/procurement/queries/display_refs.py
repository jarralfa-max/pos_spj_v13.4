"""Referencias de presentación de Compras (§19): la pantalla nunca muestra un UUID.

Cada referencia lleva el id interno (para operar) y lo que una persona reconoce
(código y nombre). ``label`` es lo único que la UI pinta:
``CAR-RES-001 · Diezmillo de res``. Si el registro ya no existe se muestra un
texto genérico ("Producto no disponible"), NUNCA el id.

Lectura pura y tolerante: una tabla que falta (pruebas con esquemas reducidos,
instalaciones a medio migrar) degrada al texto genérico en vez de reventar.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class DisplayRef:
    id: str
    code: str = ""
    name: str = ""

    @property
    def label(self) -> str:
        if self.code and self.name and self.code != self.name:
            return f"{self.code} · {self.name}"
        return self.name or self.code


class ProductDisplayRef(DisplayRef):
    pass


class SupplierDisplayRef(DisplayRef):
    pass


class BranchDisplayRef(DisplayRef):
    pass


class WarehouseDisplayRef(DisplayRef):
    pass


class UserDisplayRef(DisplayRef):
    pass


class ContainerDisplayRef(DisplayRef):
    pass


#: (clase, SQL que devuelve id, código, nombre, texto si no existe)
_SOURCES = {
    ProductDisplayRef: ("SELECT id, code, name FROM products WHERE id IN ({marks})",
                        "Producto no disponible"),
    SupplierDisplayRef: ("SELECT id, supplier_code, COALESCE(NULLIF(trade_name,''), legal_name)"
                         " FROM supplier_master WHERE id IN ({marks})",
                         "Proveedor no disponible"),
    BranchDisplayRef: ("SELECT id, '', nombre FROM sucursales WHERE id IN ({marks})",
                       "Sucursal no disponible"),
    WarehouseDisplayRef: ("SELECT id, code, name FROM warehouses WHERE id IN ({marks})",
                          "Almacén no disponible"),
    UserDisplayRef: ("SELECT id, '', nombre FROM usuarios WHERE id IN ({marks})",
                     "Usuario"),
    ContainerDisplayRef: ("SELECT id, container_code, container_code"
                          " FROM logistics_physical_containers WHERE id IN ({marks})",
                          "Contenedor no disponible"),
}


class DisplayRefResolver:
    """Resuelve ids a referencias de presentación, en lote."""

    def __init__(self, connection) -> None:
        self._conn = connection

    def resolve(self, kind: type[DisplayRef], ids: Iterable[str | None]) -> dict[str, DisplayRef]:
        wanted = sorted({str(i) for i in ids if i})
        if not wanted:
            return {}
        sql, missing = _SOURCES[kind]
        found: dict[str, DisplayRef] = {}
        try:
            rows = self._conn.execute(sql.format(marks=",".join("?" * len(wanted))),
                                      wanted).fetchall()
        except sqlite3.OperationalError:
            rows = []
        for row in rows:
            found[str(row[0])] = kind(id=str(row[0]), code=str(row[1] or ""),
                                      name=str(row[2] or ""))
        return {i: found.get(i) or kind(id=i, name=missing) for i in wanted}

    def one(self, kind: type[DisplayRef], ref_id: str | None) -> DisplayRef | None:
        if not ref_id:
            return None
        return self.resolve(kind, [ref_id])[str(ref_id)]

    def label(self, kind: type[DisplayRef], ref_id: str | None, default: str = "—") -> str:
        ref = self.one(kind, ref_id)
        return ref.label if ref is not None else default
