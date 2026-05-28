import traceback
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


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

    @pyqtSlot()
    def run(self):
        self.started.emit()
        self.progress.emit("Procesando venta...")
        try:
            result = self._uc_venta.ejecutar(self._items, self._datos_pago, self._sucursal_id, self._usuario)
            self.success.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc), traceback.format_exc())
        finally:
            self.finished.emit()
