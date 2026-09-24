"""PricingReadService — read side for the enterprise pricing/costing UI (PRC-7).

Returns display rows and overview counts for the module. Read-only, parametrized
SQL over the canonical pricing schema (``price_list`` / ``product_price`` /
``volume_price`` / ``product_cost`` / ``price_change_log``). The presenter/UI never
issue SQL — they consume these results.

Product name/code come from the canonical ``products`` master via LEFT JOIN when
present (never from the legacy ``productos`` — see the pricing boundary guardrail).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def _dec(v):
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


class PricingReadService:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── overview ────────────────────────────────────────────────────────────
    def overview_counts(self) -> dict:
        c = self._conn
        lists_active = c.execute(
            "SELECT COUNT(*) FROM price_list WHERE status='ACTIVE'").fetchone()[0]
        lists_pending = c.execute(
            "SELECT COUNT(*) FROM price_list WHERE status IN ('DRAFT','UNDER_REVIEW')"
        ).fetchone()[0]
        priced = c.execute(
            "SELECT COUNT(DISTINCT product_id) FROM product_price").fetchone()[0]
        costed = c.execute(
            "SELECT COUNT(DISTINCT product_id) FROM product_cost").fetchone()[0]
        volume_tiers = c.execute("SELECT COUNT(*) FROM volume_price").fetchone()[0]
        # Decimal-only: comparación en Python (nunca CAST AS REAL)
        below_min = 0
        for r in c.execute("SELECT sale_price, min_price FROM product_price "
                           "WHERE min_price IS NOT NULL").fetchall():
            sale, mn = _dec(r["sale_price"]), _dec(r["min_price"])
            if sale is not None and mn is not None and sale < mn:
                below_min += 1
        return {"lists_active": lists_active, "lists_pending": lists_pending,
                "priced": priced, "costed": costed, "volume_tiers": volume_tiers,
                "below_min": below_min}

    # ── price lists ─────────────────────────────────────────────────────────
    def list_price_lists(self, *, kind: str | None = None, limit: int = 200) -> list[dict]:
        sql = ("SELECT id, code, name, kind, status, discount_pct FROM price_list "
               "WHERE 1=1")
        params: list = []
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        sql += " ORDER BY kind, name LIMIT ?"
        params.append(int(limit))
        rows = self._conn.execute(sql, params).fetchall()
        return [{"id": r["id"], "code": r["code"], "name": r["name"], "kind": r["kind"],
                 "status": r["status"], "discount_pct": r["discount_pct"]} for r in rows]

    # ── product prices ──────────────────────────────────────────────────────
    def get_product_price(self, price_id: str) -> dict | None:
        """Una fila de precio por su id, para precargar el diálogo de edición.

        Existe en vez de rebuscar dentro de `list_product_prices` porque esa
        lista va truncada a `limit`: un precio fuera de la primera página no se
        encontraría y el botón Editar fallaría sin motivo visible.
        """
        filas = self.list_product_prices(price_id=price_id, limit=1)
        return filas[0] if filas else None

    def list_product_prices(self, *, query: str | None = None, list_id: str | None = None,
                            price_id: str | None = None,
                            limit: int = 200) -> list[dict]:
        has_products = self._table_exists("products")
        name_sel = "p.code AS product_code, p.name AS product_name" if has_products \
            else "NULL AS product_code, NULL AS product_name"
        join = "LEFT JOIN products p ON p.id = pp.product_id" if has_products else ""
        # `price_list_id` va en la proyección a propósito: la tabla de la UI usa
        # el id del PRECIO como identificador de fila, así que sin este campo
        # una fila seleccionada no permite saber a qué lista pertenece — y
        # editar un precio exige la lista, porque una lista APROBADA o ACTIVA es
        # inmutable y la operación debe rechazarse.
        sql = (f"SELECT pp.id, pp.price_list_id, pp.product_id, {name_sel}, pp.branch_id, "
               f"pp.sale_price, pp.sale_price_currency, pp.min_price, pp.effective_from, "
               f"pp.effective_to, pl.code AS list_code, pl.name AS list_name, "
               f"pl.status AS list_status "
               f"FROM product_price pp "
               f"JOIN price_list pl ON pl.id = pp.price_list_id {join} WHERE 1=1")
        params: list = []
        if price_id:
            sql += " AND pp.id=?"
            params.append(price_id)
        if list_id:
            sql += " AND pp.price_list_id=?"
            params.append(list_id)
        if query and has_products:
            sql += " AND (p.name_normalized LIKE ? OR p.code LIKE ?)"
            params += [f"%{query.strip().lower()}%", f"%{query.strip().upper()}%"]
        sql += " ORDER BY pl.name LIMIT ?"
        params.append(int(limit))
        rows = self._conn.execute(sql, params).fetchall()
        return [{"id": r["id"], "price_list_id": r["price_list_id"],
                 "product_id": r["product_id"],
                 "product_code": r["product_code"], "product_name": r["product_name"],
                 "branch_id": r["branch_id"], "sale_price": r["sale_price"],
                 "currency": r["sale_price_currency"], "min_price": r["min_price"],
                 "effective_from": r["effective_from"], "effective_to": r["effective_to"],
                 "list_code": r["list_code"], "list_name": r["list_name"],
                 "list_status": r["list_status"]} for r in rows]

    # ── costs ───────────────────────────────────────────────────────────────
    def list_costs(self, *, limit: int = 200) -> list[dict]:
        has_products = self._table_exists("products")
        name_sel = "p.code AS product_code, p.name AS product_name" if has_products \
            else "NULL AS product_code, NULL AS product_name"
        join = "LEFT JOIN products p ON p.id = pc.product_id" if has_products else ""
        rows = self._conn.execute(
            f"SELECT pc.product_id, {name_sel}, pc.average_cost, pc.average_cost_currency, "
            f"pc.last_cost, pc.standard_cost, pc.cost_method "
            f"FROM product_cost pc {join} ORDER BY pc.updated_at DESC LIMIT ?",
            (int(limit),)).fetchall()
        return [{"product_id": r["product_id"], "product_code": r["product_code"],
                 "product_name": r["product_name"], "average_cost": r["average_cost"],
                 "currency": r["average_cost_currency"], "last_cost": r["last_cost"],
                 "standard_cost": r["standard_cost"], "cost_method": r["cost_method"]}
                for r in rows]

    # ── price change history / audit ────────────────────────────────────────
    def list_price_history(self, *, product_id: str | None = None, limit: int = 100
                           ) -> list[dict]:
        sql = ("SELECT product_id, field, old_value, new_value, currency, user_id, "
               "authorized_by, created_at FROM price_change_log WHERE 1=1")
        params: list = []
        if product_id:
            sql += " AND product_id=?"
            params.append(product_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(int(limit))
        rows = self._conn.execute(sql, params).fetchall()
        return [{"product_id": r["product_id"], "field": r["field"],
                 "old_value": r["old_value"], "new_value": r["new_value"],
                 "currency": r["currency"], "user_id": r["user_id"],
                 "authorized_by": r["authorized_by"], "created_at": r["created_at"]}
                for r in rows]

    # ── configuración del módulo ────────────────────────────────────────────
    def settings_summary(self) -> dict:
        """Parámetros EFECTIVOS con los que opera hoy el módulo.

        No hay tabla de configuración de Precios y no se inventa una: los
        parámetros de este módulo no son interruptores guardados aparte, son
        consecuencia de los datos. Cuál lista manda, en qué moneda se cobra, con
        qué método se costea y cuántos productos tienen red de seguridad son
        preguntas con respuesta exacta en el esquema, y son justo las que no se
        podían contestar desde ninguna pantalla.

        Las tres primeras se devuelven como LISTAS, no como un valor único, a
        propósito: cero listas base activas o dos monedas conviviendo son
        configuraciones rotas que el usuario necesita ver, y un campo único
        obligaría a elegir una en silencio y dar el problema por inexistente.
        """
        c = self._conn
        base_lists = [
            {"id": r["id"], "code": r["code"], "name": r["name"]}
            for r in c.execute(
                "SELECT id, code, name FROM price_list "
                "WHERE kind='BASE' AND status='ACTIVE' ORDER BY code").fetchall()]
        lists_by_kind = {
            r["kind"]: r["total"] for r in c.execute(
                "SELECT kind, COUNT(*) AS total FROM price_list GROUP BY kind").fetchall()}
        currencies = [r[0] for r in c.execute(
            "SELECT DISTINCT sale_price_currency FROM product_price "
            "WHERE sale_price_currency IS NOT NULL AND sale_price_currency <> '' "
            "ORDER BY sale_price_currency").fetchall()]
        cost_methods = [r[0] for r in c.execute(
            "SELECT DISTINCT cost_method FROM product_cost "
            "WHERE cost_method IS NOT NULL AND cost_method <> '' "
            "ORDER BY cost_method").fetchall()]
        priced = c.execute("SELECT COUNT(*) FROM product_price").fetchone()[0]
        with_minimum = c.execute(
            "SELECT COUNT(*) FROM product_price "
            "WHERE min_price IS NOT NULL AND min_price <> ''").fetchone()[0]
        # Precios acotados a una sucursal concreta frente a los que valen para
        # todas (`branch_id = ''`). Es lo que decide si Precios opera por
        # sucursal o de forma central, y no se ve en ninguna otra pantalla.
        branch_specific = c.execute(
            "SELECT COUNT(*) FROM product_price WHERE branch_id <> ''").fetchone()[0]
        hot_authorizations = c.execute(
            "SELECT COUNT(*) FROM pricing_authorization_log").fetchone()[0] \
            if self._table_exists("pricing_authorization_log") else 0
        return {
            "base_lists": base_lists,
            "lists_by_kind": lists_by_kind,
            "currencies": currencies,
            "cost_methods": cost_methods,
            "priced": priced,
            "with_minimum": with_minimum,
            "branch_specific": branch_specific,
            "hot_authorizations": hot_authorizations,
        }

    # ── helpers ─────────────────────────────────────────────────────────────
    def _table_exists(self, name: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None
