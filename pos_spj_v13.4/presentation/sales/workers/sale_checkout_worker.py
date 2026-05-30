from __future__ import annotations

import logging

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

logger = logging.getLogger("spj.sales.checkout_worker")

_DISABLED_MESSAGE = (
    "SaleCheckoutWorker deshabilitado: la venta transaccional debe ejecutarse "
    "en el hilo principal con ProcesarVentaUC.ejecutar(); solo impresión/PDF puede ir en background."
)


class SaleCheckoutWorker(QObject):
    """Bloqueado: no ejecutar ventas en QThread con servicios/SQLite del contenedor UI."""

    started = pyqtSignal()
    progress = pyqtSignal(str)
    success = pyqtSignal(object)
    failed = pyqtSignal(str, str)
    finished = pyqtSignal()

    def __init__(self, uc_venta, items, datos_pago, sucursal_id, usuario):
        super().__init__()
        logger.error(_DISABLED_MESSAGE)
        raise RuntimeError(_DISABLED_MESSAGE)

    @pyqtSlot()
    def run(self):
        logger.error(_DISABLED_MESSAGE)
        self.failed.emit(_DISABLED_MESSAGE, "")
        self.finished.emit()
