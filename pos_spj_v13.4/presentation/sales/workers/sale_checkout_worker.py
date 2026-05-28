import traceback
import threading
import sqlite3
import logging
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

logger = logging.getLogger("spj.sales.checkout_worker")


class SaleCheckoutWorker(QObject):
    started = pyqtSignal()
    progress = pyqtSignal(str)
    success = pyqtSignal(object)
    failed = pyqtSignal(str, str)
    finished = pyqtSignal()

    def __init__(self, uc_venta, items, datos_pago, sucursal_id, usuario):
        super().__init__()
        self._uc_venta = uc_venta
        self._items = items
        self._datos_pago = datos_pago
        self._sucursal_id = sucursal_id
        self._usuario = usuario
        self._ui_thread_id = threading.get_ident()

    def _db_conn_id(self):
        try:
            sales = getattr(self._uc_venta, "_sales", None)
            db = getattr(sales, "db", None)
            return id(db) if db is not None else 0
        except Exception:
            return 0

    @pyqtSlot()
    def run(self):
        self.started.emit()
        self.progress.emit("Procesando venta...")
        worker_tid = threading.get_ident()
        logger.info(
            "SaleCheckoutWorker start ui_tid=%s worker_tid=%s db_conn_id=%s",
            self._ui_thread_id,
            worker_tid,
            self._db_conn_id(),
        )
        try:
            result = self._uc_venta.ejecutar(self._items, self._datos_pago, self._sucursal_id, self._usuario)
            self.success.emit(result)
        except sqlite3.ProgrammingError as exc:
            logger.exception("SQLite thread error in checkout worker")
            self.failed.emit(str(exc), traceback.format_exc())
        except Exception as exc:
            self.failed.emit(str(exc), traceback.format_exc())
        finally:
            self.finished.emit()
