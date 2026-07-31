"""BranchAssortmentQueryService (§10) — read side de asignación sucursal/canal.

Sirve a la página "Sucursales y canales": el estado de habilitación de un producto
por sucursal (`sucursales` ⟕ `branch_product`), los canales disponibles y los
surtidos con su membresía del producto. Read-only.
"""

from __future__ import annotations

from backend.domain.products.channel_enums import SalesChannel

_CHANNEL_ES = {
    SalesChannel.GLOBAL: "Global",
    SalesChannel.POS: "POS",
    SalesChannel.ECOMMERCE: "E-commerce",
    SalesChannel.WHATSAPP: "WhatsApp",
    SalesChannel.DELIVERY: "Delivery",
    SalesChannel.WHOLESALE: "Mayoreo",
    SalesChannel.PLANT: "Planta",
    SalesChannel.CENTRAL_WAREHOUSE: "Almacén central",
}


class BranchAssortmentQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def _table(self, name: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,)).fetchone() is not None

    def branch_assignments(self, product_id: str) -> list[dict]:
        """Sucursales activas con el estado de habilitación del producto
        (``enabled`` = False cuando no hay fila en ``branch_product``)."""
        if not self._table("sucursales"):
            return []
        rows = self._conn.execute(
            "SELECT s.id AS branch_id, s.nombre AS branch_name, "
            "       COALESCE(bp.enabled, 0) AS enabled "
            "FROM sucursales s "
            "LEFT JOIN branch_product bp ON bp.branch_id=s.id AND bp.product_id=? "
            "WHERE COALESCE(s.activa,1)=1 ORDER BY s.nombre",
            (product_id,)).fetchall()
        return [{"branch_id": r["branch_id"], "branch_name": r["branch_name"],
                 "enabled": bool(r["enabled"])} for r in rows]

    def channels(self) -> list[dict]:
        """Canales disponibles como ``{value, label}`` (español visible)."""
        return [{"value": c.value, "label": _CHANNEL_ES[c]} for c in SalesChannel]

    def assortments(self, product_id: str, *, channel: str | None = None) -> list[dict]:
        """Surtidos (opcionalmente de un canal) con la membresía del producto."""
        if not self._table("assortments"):
            return []
        sql = ("SELECT a.id, a.name, a.channel, a.branch_id, a.active, "
               "       COALESCE(ap.enabled, 0) AS contains "
               "FROM assortments a "
               "LEFT JOIN assortment_products ap "
               "  ON ap.assortment_id=a.id AND ap.product_id=? ")
        params: list = [product_id]
        if channel:
            sql += "WHERE a.channel=? "
            params.append(str(channel))
        sql += "ORDER BY a.name"
        rows = self._conn.execute(sql, params).fetchall()
        return [{"id": r["id"], "name": r["name"], "channel": r["channel"],
                 "branch_id": r["branch_id"], "active": bool(r["active"]),
                 "contains": bool(r["contains"])} for r in rows]
