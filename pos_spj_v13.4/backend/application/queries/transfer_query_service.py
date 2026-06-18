"""Read-only QueryService for the transfers UI/API read models.

Single canonical read path for transfer data.
All SQL lives here; no SQL is allowed in PyQt modules.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.application.queries.base_query_service import (
    BaseQueryService,
    KpiMetric,
    QueryFilters,
    SearchResult,
    TableRow,
)

logger = logging.getLogger("spj.transfers.query")


class SQLiteTransferQueryDataSource:
    """Transfer read adapter for the desktop until a repository-backed API is wired."""

    def __init__(self, conn: Any) -> None:
        self._db = conn

    # ── BaseQueryService protocol ─────────────────────────────────────────────

    def search(self, scope: str, query: str, filters: QueryFilters | None = None) -> list[SearchResult]:
        if scope != "transfers":
            return []
        like = f"%{query}%"
        try:
            rows = self._db.execute(
                """
                SELECT t.id, t.status, t.branch_origin_id, t.branch_dest_id,
                       t.dispatched_by, t.created_at,
                       s1.nombre AS origin_name, s2.nombre AS dest_name
                FROM transfers t
                LEFT JOIN sucursales s1 ON s1.id = t.branch_origin_id
                LEFT JOIN sucursales s2 ON s2.id = t.branch_dest_id
                WHERE t.id LIKE ?
                   OR COALESCE(s1.nombre,'') LIKE ?
                   OR COALESCE(s2.nombre,'') LIKE ?
                ORDER BY t.created_at DESC
                LIMIT 50
                """,
                (like, like, like),
            ).fetchall()
        except Exception:
            logger.exception("search transfers query failed")
            return []
        return [
            SearchResult(
                id=str(self._v(r, "id", 0)),
                label=f"{str(self._v(r,'id',0))[:8]}… {self._v(r,'status',1)}",
                subtitle=f"{self._v(r,'origin_name',6) or self._v(r,'branch_origin_id',2)} → "
                         f"{self._v(r,'dest_name',7) or self._v(r,'branch_dest_id',3)}",
            )
            for r in rows
        ]

    def list_rows(self, scope: str, filters: QueryFilters | None = None) -> list[TableRow]:
        if scope != "transfers":
            return []
        rows = self._list_transfers(filters=filters)
        return [TableRow(id=str(r.get("id", "")), values=r) for r in rows]

    def metrics(self, scope: str, filters: QueryFilters | None = None) -> list[KpiMetric]:
        if scope != "transfers":
            return []
        counts = self.get_kpi_counts()
        return [
            KpiMetric("pending_reception", "Pendientes de recepción", counts["pending_reception"]),
            KpiMetric("received_month",    "Recibidas (mes)",          counts["received_month"]),
            KpiMetric("in_transit",        "En tránsito",              counts["in_transit"]),
            KpiMetric("cancelled_month",   "Canceladas (mes)",         counts["cancelled_month"]),
        ]

    # ── Specific transfer methods ─────────────────────────────────────────────

    def get_kpi_counts(self, branch_id: int | None = None) -> dict[str, int]:
        """Return KPI counts for the transfers stats bar.

        Replaces the four SQL queries that were previously executed directly in
        the PyQt module (_crear_stats_transferencias).
        """
        branch_clause = ""
        params_branch: list[Any] = []
        if branch_id:
            branch_clause = " AND (branch_origin_id=? OR branch_dest_id=?)"
            params_branch = [branch_id, branch_id]

        def _count(extra_where: str, extra_params: list) -> int:
            try:
                row = self._db.execute(
                    f"SELECT COUNT(*) FROM transfers WHERE 1=1{branch_clause}{extra_where}",
                    params_branch + extra_params,
                ).fetchone()
                return int(row[0]) if row else 0
            except Exception:
                logger.debug("get_kpi_counts fallback to 0: %s", extra_where)
                return 0

        return {
            "pending_reception": _count(" AND status='DISPATCHED'", []),
            "received_month":    _count(
                " AND status='RECEIVED' AND DATE(created_at)>=DATE('now','start of month')", []
            ),
            "in_transit":        _count(" AND status='PENDING'", []),
            "cancelled_month":   _count(
                " AND status='CANCELLED' AND DATE(created_at)>=DATE('now','start of month')", []
            ),
        }

    def list_transfers(
        self,
        branch_id: int | None = None,
        status: str | None = None,
        search: str = "",
    ) -> list[dict]:
        """Return transfer rows enriched with branch names for the UI table."""
        return self._list_transfers(
            filters={"branch_id": branch_id, "status": status, "query": search}
        )

    def _list_transfers(self, *, filters: QueryFilters | None = None) -> list[dict]:
        filters = filters or {}
        conditions: list[str] = []
        params: list[Any] = []

        branch_id = filters.get("branch_id")
        if branch_id:
            conditions.append("(t.branch_origin_id=? OR t.branch_dest_id=?)")
            params.extend([int(branch_id), int(branch_id)])

        status = filters.get("status") or filters.get("estado")
        if status:
            conditions.append("t.status=?")
            params.append(str(status))

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        try:
            rows = self._db.execute(
                f"""
                SELECT t.id, t.branch_origin_id, t.branch_dest_id,
                       t.origin_type, t.destination_type, t.status,
                       t.dispatched_by, t.received_by,
                       t.created_at, t.received_at,
                       t.difference_kg, t.observations,
                       t.operation_id,
                       COALESCE(s1.nombre, CAST(t.branch_origin_id AS TEXT)) AS origin_name,
                       COALESCE(s2.nombre, CAST(t.branch_dest_id  AS TEXT)) AS dest_name,
                       COUNT(ti.id) AS item_count
                FROM transfers t
                LEFT JOIN sucursales s1 ON s1.id = t.branch_origin_id
                LEFT JOIN sucursales s2 ON s2.id = t.branch_dest_id
                LEFT JOIN transfer_items ti ON ti.transfer_id = t.id
                {where}
                GROUP BY t.id
                ORDER BY t.created_at DESC
                LIMIT 500
                """,
                params,
            ).fetchall()
        except Exception:
            logger.exception("_list_transfers query failed")
            return []

        out = []
        for r in rows:
            d = self._row_to_dict(r)
            # apply text search locally (avoids complex SQL LIKE on joined columns)
            text = str(filters.get("query") or filters.get("search") or "").strip().lower()
            if text:
                haystack = (
                    str(d.get("id", "")).lower()
                    + str(d.get("origin_name", "")).lower()
                    + str(d.get("dest_name", "")).lower()
                )
                if text not in haystack:
                    continue
            out.append(d)
        return out

    def get_branches(self, *, exclude_branch_id: int | None = None) -> list[dict]:
        """Return active branches for the destination combo in dispatch dialog."""
        try:
            rows = self._db.execute(
                "SELECT id, nombre FROM sucursales WHERE COALESCE(activa,1)=1 ORDER BY nombre"
            ).fetchall()
        except Exception:
            logger.exception("get_branches query failed")
            return [{"id": 1, "nombre": "Principal"}]
        result = [{"id": int(self._v(r,"id",0)), "nombre": str(self._v(r,"nombre",1))} for r in rows]
        if exclude_branch_id is not None:
            result = [b for b in result if b["id"] != exclude_branch_id]
        return result

    def list_products_for_dispatch(self, sucursal_id: int) -> list[dict]:
        """Return active products with current stock for the dispatch SearchSelector."""
        try:
            has_ia = bool(
                self._db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventario_actual'"
                ).fetchone()
            )
            stock_expr = (
                "COALESCE(ia.cantidad, p.existencia, 0)"
                if has_ia
                else "COALESCE(p.existencia, 0)"
            )
            ia_join = (
                f"LEFT JOIN inventario_actual ia "
                f"ON ia.producto_id=p.id AND ia.sucursal_id={int(sucursal_id)}"
                if has_ia
                else ""
            )
            rows = self._db.execute(
                f"""
                SELECT p.id, p.nombre,
                       COALESCE(p.unidad,'kg') AS unidad,
                       {stock_expr} AS existencia
                FROM productos p
                {ia_join}
                WHERE COALESCE(p.activo,1)=1
                ORDER BY p.nombre
                """,
            ).fetchall()
        except Exception:
            logger.exception("list_products_for_dispatch failed")
            return []
        return [
            {
                "id":        self._v(r, "id", 0),
                "nombre":    str(self._v(r, "nombre", 1)),
                "unidad":    str(self._v(r, "unidad", 2) or "kg"),
                "existencia": float(self._v(r, "existencia", 3) or 0),
            }
            for r in rows
        ]

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _v(row: Any, key: str, index: int) -> Any:
        try:
            return row[key] if hasattr(row, "keys") else row[index]
        except (KeyError, IndexError):
            return None

    @staticmethod
    def _row_to_dict(row: Any) -> dict:
        if hasattr(row, "keys"):
            return {k: row[k] for k in row.keys()}
        return dict(enumerate(row))  # fallback — callers expect named keys


class TransferQueryService(BaseQueryService):
    """Canonical read-only service for transfers UI/API."""

    scope = "transfers"

    def __init__(self, data_source: SQLiteTransferQueryDataSource | None = None) -> None:
        super().__init__(data_source)
        self._src = data_source

    @classmethod
    def from_connection(cls, conn: Any) -> "TransferQueryService":
        src = SQLiteTransferQueryDataSource(conn)
        return cls(data_source=src)

    # ── Thin wrappers (delegate to data source) ───────────────────────────────

    def get_kpi_counts(self, branch_id: int | None = None) -> dict[str, int]:
        """KPI counts for the stats bar — replaces direct SQL in the UI module."""
        if self._src is None:
            return {"pending_reception": 0, "received_month": 0, "in_transit": 0, "cancelled_month": 0}
        return self._src.get_kpi_counts(branch_id=branch_id)

    def list_transfers(
        self,
        branch_id: int | None = None,
        status: str | None = None,
        search: str = "",
    ) -> list[dict]:
        if self._src is None:
            return []
        return self._src.list_transfers(branch_id=branch_id, status=status, search=search)

    def get_branches(self, *, exclude_branch_id: int | None = None) -> list[dict]:
        """Active branches list for destination combo."""
        if self._src is None:
            return []
        return self._src.get_branches(exclude_branch_id=exclude_branch_id)

    def list_products_for_dispatch(self, sucursal_id: int) -> list[dict]:
        """Products with stock for the dispatch SearchSelector."""
        if self._src is None:
            return []
        return self._src.list_products_for_dispatch(sucursal_id=sucursal_id)

    # ── BaseQueryService convenience wrappers ─────────────────────────────────

    def search_transfers(self, query: str, filters: QueryFilters | None = None) -> list[SearchResult]:
        return list(self.search(query, filters))

    def list_for_table(self, filters: QueryFilters | None = None) -> list[TableRow]:
        return list(self.list_rows(filters))

    def get_kpis(self, filters: QueryFilters | None = None) -> list[KpiMetric]:
        return list(self.metrics(filters))
