from __future__ import annotations

import copy
import sqlite3
from typing import Any

from core.use_cases.venta import ProcesarVentaUC
from presentation.sales.workers.sale_checkout_worker import SaleCheckoutWorker


class SaleCheckoutWorkerFactory:
    """Crea workers con UC aislado por hilo usando conexión SQLite dedicada."""

    def __init__(self, container):
        self._container = container

    def _new_thread_db(self):
        db = getattr(self._container, "db", None)
        if db is None:
            return None
        row = db.execute("PRAGMA database_list").fetchone()
        db_path = row[2] if row and len(row) > 2 else ""
        if not db_path:
            return None
        conn = sqlite3.connect(db_path, timeout=5.0, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _clone_uc(self, base_uc, db_conn):
        if db_conn is None:
            return base_uc

        sales = copy.copy(getattr(base_uc, "_sales", None))
        inventory = copy.copy(getattr(base_uc, "_inventory", None))
        finance = copy.copy(getattr(base_uc, "_finance", None))
        loyalty = copy.copy(getattr(base_uc, "_loyalty", None))
        ticket = getattr(base_uc, "_ticket", None)
        sync = getattr(base_uc, "_sync", None)
        bus = getattr(base_uc, "_bus", None)
        cfdi = getattr(base_uc, "_cfdi", None)

        for svc in (sales, inventory, finance, loyalty):
            if svc is not None and hasattr(svc, "db"):
                try:
                    svc.db = db_conn
                except Exception:
                    pass

        return ProcesarVentaUC(
            sales_service=sales,
            inventory_service=inventory,
            finance_service=finance,
            loyalty_service=loyalty,
            ticket_engine=ticket,
            sync_service=sync,
            event_bus=bus,
            cfdi_service=cfdi,
        )

    def build(self, uc_venta: Any, items, datos_pago, sucursal_id, usuario) -> SaleCheckoutWorker:
        thread_db = self._new_thread_db()
        uc = self._clone_uc(uc_venta, thread_db)
        return SaleCheckoutWorker(uc, items, datos_pago, sucursal_id, usuario)

