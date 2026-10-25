"""Margen mínimo protegido (auditoría Fidelidad 968e0bc FID-03)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid


class LoyaltyMarginFloorRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def schema_ready(self) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='loyalty_margin_floors'"
        ).fetchone() is not None

    def floors(self) -> dict[tuple[str, str], Decimal]:
        if not self.schema_ready():
            return {}
        return {(str(f[0]), str(f[1])): Decimal(str(f[2])) for f in self._conn.execute(
            "SELECT scope_type, scope_id, min_margin_percent FROM loyalty_margin_floors")}

    def list(self) -> list[dict]:
        if not self.schema_ready():
            return []
        filas = self._conn.execute(
            "SELECT f.id, f.scope_type, f.scope_id, f.min_margin_percent, f.updated_at,"
            " COALESCE(c.name, p.name, f.scope_id) FROM loyalty_margin_floors f"
            " LEFT JOIN product_categories c ON f.scope_type='CATEGORY' AND c.id=f.scope_id"
            " LEFT JOIN products p ON f.scope_type='PRODUCT' AND p.id=f.scope_id"
            " ORDER BY f.scope_type, 6").fetchall()
        return [{"id": f[0], "scope_type": f[1], "scope_id": f[2],
                 "min_margin_percent": f[3], "updated_at": f[4], "scope_name": f[5]}
                for f in filas]

    def save(self, *, scope_type: str, scope_id: str, min_margin_percent: Decimal,
             actor_user_id: str) -> None:
        self._conn.execute(
            "INSERT INTO loyalty_margin_floors (id, scope_type, scope_id, min_margin_percent,"
            " updated_by, updated_at) VALUES (?,?,?,?,?,?) ON CONFLICT(scope_type, scope_id)"
            " DO UPDATE SET min_margin_percent=excluded.min_margin_percent,"
            " updated_by=excluded.updated_by, updated_at=excluded.updated_at",
            (new_uuid(), scope_type, scope_id, str(min_margin_percent), actor_user_id,
             datetime.now(timezone.utc).isoformat(timespec="seconds")))

    def delete(self, floor_id: str) -> None:
        self._conn.execute("DELETE FROM loyalty_margin_floors WHERE id=?", (floor_id,))

    def category_chain(self, product_ids) -> dict[str, list[str]]:
        """Por producto, su categoría y sus ancestros, de la MÁS cercana a la raíz."""
        ids = [str(p) for p in product_ids if p]
        if not ids:
            return {}
        marcas = ",".join("?" * len(ids))
        try:
            directa = {str(f[0]): f[1] for f in self._conn.execute(
                f"SELECT id, category_id FROM products WHERE id IN ({marcas})", tuple(ids))}
            padres = {str(f[0]): f[1] for f in self._conn.execute(
                "SELECT id, parent_id FROM product_categories")}
        except Exception:  # noqa: BLE001 - catálogo reducido: sólo rige el margen general
            return {}
        cadenas = {}
        for producto, categoria in directa.items():
            cadena, actual = [], categoria
            while actual and actual not in cadena and len(cadena) < 20:
                cadena.append(str(actual))
                actual = padres.get(str(actual))
            cadenas[producto] = cadena
        return cadenas
