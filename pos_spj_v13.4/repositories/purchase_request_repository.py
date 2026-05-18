"""
repositories/purchase_request_repository.py
────────────────────────────────────────────
Acceso a datos para Purchase Requests (PR).

Tabla: purchase_requests + purchase_request_items
Sin lógica de negocio — solo CRUD + queries.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger("spj.repo.purchase_request")


class PurchaseRequestRepository:

    def __init__(self, conn):
        self.conn = conn
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create PR tables if migration 076 hasn't run yet (defensive fallback)."""
        try:
            self.conn.execute("SELECT 1 FROM purchase_requests LIMIT 1")
        except Exception:
            try:
                self.conn.executescript("""
                    CREATE TABLE IF NOT EXISTS purchase_requests (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        folio           TEXT UNIQUE,
                        proveedor_id    INTEGER,
                        proveedor_nombre TEXT,
                        sucursal_id     INTEGER NOT NULL DEFAULT 1,
                        usuario         TEXT NOT NULL,
                        subtotal        REAL NOT NULL DEFAULT 0,
                        iva_monto       REAL NOT NULL DEFAULT 0,
                        total           REAL NOT NULL DEFAULT 0,
                        metodo_pago     TEXT DEFAULT 'CONTADO',
                        condicion_pago  TEXT DEFAULT 'liquidado',
                        plazo_dias      INTEGER DEFAULT 0,
                        moneda          TEXT DEFAULT 'MXN',
                        notas           TEXT,
                        doc_ref         TEXT,
                        estado          TEXT NOT NULL DEFAULT 'BORRADOR',
                        aprobado_por    TEXT,
                        rechazado_por   TEXT,
                        motivo_rechazo  TEXT,
                        fecha_aprobacion DATETIME,
                        fecha_creacion  DATETIME DEFAULT (datetime('now')),
                        fecha_actualizacion DATETIME DEFAULT (datetime('now'))
                    );
                    CREATE INDEX IF NOT EXISTS idx_pr_estado
                        ON purchase_requests(estado, fecha_creacion DESC);
                    CREATE INDEX IF NOT EXISTS idx_pr_proveedor
                        ON purchase_requests(proveedor_id);
                    CREATE INDEX IF NOT EXISTS idx_pr_sucursal
                        ON purchase_requests(sucursal_id, estado);
                    CREATE TABLE IF NOT EXISTS purchase_request_items (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        pr_id           INTEGER NOT NULL REFERENCES purchase_requests(id),
                        producto_id     INTEGER NOT NULL,
                        nombre          TEXT NOT NULL,
                        cantidad        REAL NOT NULL DEFAULT 0,
                        unidad          TEXT DEFAULT 'kg',
                        precio_unitario REAL NOT NULL DEFAULT 0,
                        descuento       REAL DEFAULT 0,
                        subtotal        REAL NOT NULL DEFAULT 0,
                        lote            TEXT,
                        fecha_caducidad DATE,
                        notas           TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_pr_items_pr
                        ON purchase_request_items(pr_id);
                """)
                logger.warning("purchase_requests tables created via fallback (migration 076 not applied)")
            except Exception as e:
                logger.error("Could not create purchase_requests tables: %s", e)

    # ── Creación ──────────────────────────────────────────────────────────────

    def create(
        self,
        proveedor_id: int,
        proveedor_nombre: str,
        sucursal_id: int,
        usuario: str,
        items: list[dict],
        metodo_pago: str,
        subtotal: float,
        iva_monto: float,
        total: float,
        condicion_pago: str = "liquidado",
        plazo_dias: int = 0,
        moneda: str = "MXN",
        notas: str = "",
        doc_ref: str = "",
        estado: str = "BORRADOR",
    ) -> tuple[int, str]:
        """
        Crea una PR en estado inicial.
        Retorna (pr_id, folio).
        NO afecta inventario, finanzas ni eventos.
        """
        folio = f"PR-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        cur = self.conn.execute(
            """INSERT INTO purchase_requests
               (folio, proveedor_id, proveedor_nombre, sucursal_id, usuario,
                subtotal, iva_monto, total, metodo_pago, condicion_pago,
                plazo_dias, moneda, notas, doc_ref, estado)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (folio, proveedor_id, proveedor_nombre, sucursal_id, usuario,
             subtotal, iva_monto, total, metodo_pago, condicion_pago,
             plazo_dias, moneda, notas, doc_ref, estado),
        )
        pr_id = cur.lastrowid
        self._save_items(pr_id, items)
        logger.info("PR creada: %s id=%d proveedor=%s total=%.2f", folio, pr_id, proveedor_nombre, total)
        return pr_id, folio

    def _save_items(self, pr_id: int, items: list[dict]) -> None:
        for item in items:
            self.conn.execute(
                """INSERT INTO purchase_request_items
                   (pr_id, producto_id, nombre, cantidad, unidad,
                    precio_unitario, subtotal, lote, fecha_caducidad, notas)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (pr_id,
                 item["product_id"],
                 item.get("nombre", ""),
                 item["qty"],
                 item.get("unidad", "kg"),
                 item["unit_cost"],
                 round(item["qty"] * item["unit_cost"], 4),
                 item.get("lote", ""),
                 item.get("fecha_caducidad"),
                 item.get("notas", "")),
            )

    # ── Lectura ───────────────────────────────────────────────────────────────

    def get_by_id(self, pr_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM purchase_requests WHERE id=?", (pr_id,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["items"] = self._get_items(pr_id)
        return result

    def get_by_folio(self, folio: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM purchase_requests WHERE folio=?", (folio,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["items"] = self._get_items(result["id"])
        return result

    def _get_items(self, pr_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM purchase_request_items WHERE pr_id=? ORDER BY id",
            (pr_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_items(self, pr_id: int) -> list[dict]:
        """Public read helper for UI/use cases; keeps SQL inside repository."""
        return self._get_items(pr_id)

    def list_by_estado(self, estado: str, sucursal_id: Optional[int] = None,
                       limit: int = 100) -> list[dict]:
        if sucursal_id:
            rows = self.conn.execute(
                """SELECT * FROM purchase_requests
                   WHERE estado=? AND sucursal_id=?
                   ORDER BY fecha_creacion DESC LIMIT ?""",
                (estado, sucursal_id, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM purchase_requests
                   WHERE estado=?
                   ORDER BY fecha_creacion DESC LIMIT ?""",
                (estado, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_pending(self, sucursal_id: Optional[int] = None) -> list[dict]:
        return self.list_by_estado("PENDIENTE_APROBACION", sucursal_id)

    def list_approved(self, sucursal_id: Optional[int] = None) -> list[dict]:
        return self.list_by_estado("APROBADA", sucursal_id)

    # ── Transiciones de estado ────────────────────────────────────────────────

    def update_estado(self, pr_id: int, nuevo_estado: str,
                      usuario: Optional[str] = None,
                      motivo: Optional[str] = None) -> bool:
        now = datetime.now().isoformat()
        if nuevo_estado in ("APROBADA",):
            self.conn.execute(
                """UPDATE purchase_requests
                   SET estado=?, aprobado_por=?, fecha_aprobacion=?, fecha_actualizacion=?
                   WHERE id=?""",
                (nuevo_estado, usuario, now, now, pr_id),
            )
        elif nuevo_estado in ("RECHAZADA",):
            self.conn.execute(
                """UPDATE purchase_requests
                   SET estado=?, rechazado_por=?, motivo_rechazo=?, fecha_actualizacion=?
                   WHERE id=?""",
                (nuevo_estado, usuario, motivo, now, pr_id),
            )
        else:
            self.conn.execute(
                """UPDATE purchase_requests
                   SET estado=?, fecha_actualizacion=?
                   WHERE id=?""",
                (nuevo_estado, now, pr_id),
            )
        changed = self.conn.execute(
            "SELECT changes()"
        ).fetchone()[0]
        return changed > 0
