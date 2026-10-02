"""Bodegas y puntos de recolección de un proveedor (§13).

Compras (recolección en proveedor) y Logística (origen del embarque) leen de
aquí: el origen ya no es el NOMBRE del proveedor sino una dirección suya, con id
y una foto del domicilio tal como estaba al usarla (la dirección puede cambiar
después; el embarque debe seguir diciendo de dónde salió).
"""

from __future__ import annotations

import sqlite3

ORIGIN_ADDRESS_TYPES = ("WAREHOUSE", "PICKUP")
_TYPE_ES = {"WAREHOUSE": "Bodega", "PICKUP": "Punto de recolección"}


def origin_display(snapshot: dict) -> str:
    """"Bodega Norte · Querétaro" — nombre (o tipo) y la ciudad/estado."""
    name = (snapshot.get("label") or "").strip() or _TYPE_ES.get(
        snapshot.get("address_type") or "", "Dirección")
    place = ", ".join(p for p in ((snapshot.get("city") or "").strip(),
                                  (snapshot.get("state") or "").strip()) if p)
    return f"{name} · {place}" if place else name


class SupplierOriginQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def origin_locations(self, supplier_id: str) -> list[dict]:
        """``[{id, display, snapshot}]`` de las bodegas/puntos de recolección."""
        if not supplier_id:
            return []
        marks = ",".join("?" * len(ORIGIN_ADDRESS_TYPES))
        try:
            cursor = self._conn.execute(
                f"SELECT * FROM supplier_addresses WHERE supplier_id=?"
                f" AND address_type IN ({marks}) ORDER BY address_type, line",
                (supplier_id, *ORIGIN_ADDRESS_TYPES))
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            return []
        columns = [c[0] for c in cursor.description]
        result = []
        for row in rows:
            data = dict(zip(columns, tuple(row)))
            snapshot = {key: data.get(key) for key in (
                "address_type", "label", "line", "city", "state", "postal_code",
                "country_code", "latitude", "longitude")}
            snapshot["supplier_id"] = supplier_id
            result.append({"id": data["id"], "display": origin_display(snapshot),
                           "snapshot": snapshot})
        return result

    def origin_location(self, supplier_id: str, address_id: str) -> dict | None:
        return next((o for o in self.origin_locations(supplier_id) if o["id"] == address_id),
                    None)
