# repositories/purchase_request_repository.py — SPJ POS v13.4
"""
Purchase Request Repository.
All SQL for purchase_requests, purchase_request_items, purchase_request_events.
"""
from __future__ import annotations
import logging

logger = logging.getLogger("spj.repositories.purchase_request")

_TABLE_EXISTS_SQL = (
    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='purchase_requests'"
)


class PurchaseRequestRepository:
    def __init__(self, db):
        self.db = db

    def schema_ready(self) -> bool:
        try:
            return bool(self.db.execute(_TABLE_EXISTS_SQL).fetchone())
        except Exception:
            return False

    def create(self, *, folio: str, solicitante: str, sucursal_id: int,
               proveedor_id: int | None = None, notas: str = "",
               total_est: float = 0.0) -> int:
        cur = self.db.execute(
            """INSERT INTO purchase_requests
               (folio, estado, solicitante, sucursal_id, proveedor_id, notas, total_est)
               VALUES (?, 'borrador', ?, ?, ?, ?, ?)""",
            (folio, solicitante, sucursal_id, proveedor_id, notas, total_est),
        )
        self.db.commit()
        return cur.lastrowid

    def add_item(self, pr_id: int, producto_id: int, cantidad: float,
                 costo_estimado: float = 0.0, unidad: str = "pz",
                 notas: str = "") -> None:
        self.db.execute(
            """INSERT INTO purchase_request_items
               (pr_id, producto_id, cantidad_solicitada, costo_estimado, unidad, notas)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (pr_id, producto_id, cantidad, costo_estimado, unidad, notas),
        )
        self.db.commit()

    def add_event(self, pr_id: int, evento: str, usuario: str,
                  detalle: str = "") -> None:
        self.db.execute(
            """INSERT INTO purchase_request_events (pr_id, evento, usuario, detalle)
               VALUES (?, ?, ?, ?)""",
            (pr_id, evento, usuario, detalle),
        )
        self.db.commit()

    def get(self, pr_id: int) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM purchase_requests WHERE id=?", (pr_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_by_branch(self, sucursal_id: int, estado: str | None = None,
                       limit: int = 100) -> list[dict]:
        if estado:
            rows = self.db.execute(
                """SELECT * FROM purchase_requests
                   WHERE sucursal_id=? AND estado=?
                   ORDER BY creado_en DESC LIMIT ?""",
                (sucursal_id, estado, limit),
            ).fetchall()
        else:
            rows = self.db.execute(
                """SELECT * FROM purchase_requests
                   WHERE sucursal_id=?
                   ORDER BY creado_en DESC LIMIT ?""",
                (sucursal_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_items(self, pr_id: int) -> list[dict]:
        rows = self.db.execute(
            """SELECT pri.*, p.nombre
               FROM purchase_request_items pri
               LEFT JOIN productos p ON p.id = pri.producto_id
               WHERE pri.pr_id = ?""",
            (pr_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_estado(self, pr_id: int, estado: str) -> None:
        self.db.execute(
            "UPDATE purchase_requests SET estado=?, actualizado=datetime('now') WHERE id=?",
            (estado, pr_id),
        )
        self.db.commit()
