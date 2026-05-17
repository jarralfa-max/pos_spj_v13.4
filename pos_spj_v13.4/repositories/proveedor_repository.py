# repositories/proveedor_repository.py — SPJ POS v13.4
"""
Proveedor Repository.
All SQL for proveedores, compras recientes, alertas CxP, plantillas, sucursales.
Extracted from modulos/compras_pro.py (FASE 2 refactor).
"""
from __future__ import annotations
import logging

logger = logging.getLogger("spj.repositories.proveedor")


class ProveedorRepository:
    def __init__(self, db):
        self.db = db

    # ── Proveedores ───────────────────────────────────────────────────────────

    def get_activos(self) -> list[dict]:
        """Return all active providers ordered by name."""
        try:
            rows = self.db.execute(
                "SELECT id, nombre FROM proveedores WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            return [{"id": r["id"], "nombre": r["nombre"]} for r in rows]
        except Exception as e:
            logger.debug("get_activos: %s", e)
            return []

    def get_by_id(self, prov_id: int) -> dict | None:
        """Return full provider row as dict, or None if not found."""
        try:
            row = self.db.execute(
                "SELECT * FROM proveedores WHERE id=?", (prov_id,)
            ).fetchone()
            if row is None:
                return None
            return dict(row) if hasattr(row, "keys") else self._row_to_dict(row)
        except Exception as e:
            logger.debug("get_by_id(%s): %s", prov_id, e)
            return None

    # ── Compras recientes ─────────────────────────────────────────────────────

    def get_compras_recientes(self, prov_id: int, sucursal_id: int,
                              limit: int = 5) -> list[dict]:
        """Return last `limit` purchases from this provider in this branch."""
        try:
            rows = self.db.execute(
                """SELECT id, folio, fecha, total, estado
                   FROM compras
                   WHERE proveedor_id=? AND sucursal_id=?
                   ORDER BY fecha DESC, id DESC LIMIT ?""",
                (prov_id, sucursal_id, limit),
            ).fetchall()
            return [self._safe_row(r, ["id", "folio", "fecha", "total", "estado"])
                    for r in rows]
        except Exception as e:
            logger.debug("get_compras_recientes(%s): %s", prov_id, e)
            return []

    # ── Alertas CxP ──────────────────────────────────────────────────────────

    def get_alertas_cxp(self, prov_id: int, sucursal_id: int) -> dict:
        """
        Return {count, monto} of pending/credit purchases for this provider.
        Returns {count:0, monto:0.0} if none or on error.
        """
        try:
            row = self.db.execute(
                """SELECT COUNT(*), COALESCE(SUM(total), 0)
                   FROM compras
                   WHERE proveedor_id=? AND sucursal_id=?
                     AND estado IN ('credito', 'pendiente')""",
                (prov_id, sucursal_id),
            ).fetchone()
            return {
                "count": int(row[0] or 0),
                "monto": float(row[1] or 0),
            }
        except Exception as e:
            logger.debug("get_alertas_cxp(%s): %s", prov_id, e)
            return {"count": 0, "monto": 0.0}

    # ── Plantillas ────────────────────────────────────────────────────────────

    def get_plantillas(self, limit: int = 20) -> list[dict]:
        """Return purchase templates ordered by name."""
        try:
            rows = self.db.execute(
                "SELECT id, nombre FROM plantillas_compra ORDER BY nombre LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._safe_row(r, ["id", "nombre"]) for r in rows]
        except Exception as e:
            logger.debug("get_plantillas: %s", e)
            return []

    def get_plantilla_items(self, plantilla_id: int) -> list[dict]:
        """Return items of a template joined with product name and cost."""
        try:
            rows = self.db.execute(
                """SELECT ti.producto_id, p.nombre, ti.cantidad,
                          ti.costo_unitario, p.precio_compra
                   FROM plantillas_compra_items ti
                   JOIN productos p ON p.id = ti.producto_id
                   WHERE ti.plantilla_id = ?""",
                (plantilla_id,),
            ).fetchall()
            return [self._safe_row(r, [
                "producto_id", "nombre", "cantidad", "costo_unitario", "precio_compra"
            ]) for r in rows]
        except Exception as e:
            logger.debug("get_plantilla_items(%s): %s", plantilla_id, e)
            return []

    # ── Sucursales ────────────────────────────────────────────────────────────

    def get_sucursales_activas(self) -> list[dict]:
        """Return all active branches ordered by name."""
        try:
            rows = self.db.execute(
                "SELECT id, nombre FROM sucursales WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            return [self._safe_row(r, ["id", "nombre"]) for r in rows]
        except Exception as e:
            logger.debug("get_sucursales_activas: %s", e)
            return []

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_row(row, keys: list[str]) -> dict:
        """Convert sqlite3.Row or tuple to dict using provided key list."""
        if hasattr(row, "keys"):
            return {k: row.get(k) if hasattr(row, "get") else row[k]
                    for k in keys}
        return dict(zip(keys, row))

    @staticmethod
    def _row_to_dict(row) -> dict:
        """Convert sqlite3.Row to dict regardless of interface."""
        try:
            return dict(row)
        except Exception:
            return {}
