import traceback
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


class TicketOutputWorker(QObject):
    started = pyqtSignal()
    success = pyqtSignal(str)
    failed = pyqtSignal(str, str)
    finished = pyqtSignal()

    def __init__(self, save_pdf_fn, ticket_data, printer_service=None):
        super().__init__()
        self._save_pdf_fn = save_pdf_fn
        self._ticket_data = ticket_data
        self._printer_service = printer_service

    @pyqtSlot()
    def run(self):
        self.started.emit()
        try:
            if self._printer_service is not None:
                self._printer_service.print_ticket(self._ticket_data)
            self._save_pdf_fn(self._ticket_data)
            self.success.emit("PDF generado")
        except Exception as exc:
            self.failed.emit(str(exc), traceback.format_exc())
        finally:
            self.finished.emit()
