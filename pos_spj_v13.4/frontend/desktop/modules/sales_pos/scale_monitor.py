"""Qt delivery of hardware snapshots. The worker never touches widgets or SQL."""
from PyQt5.QtCore import QCoreApplication, QObject, QThread, QTimer, pyqtSignal


class _ScaleWorker(QThread):
    sample = pyqtSignal(object)

    def __init__(self, service):
        super().__init__()
        self.service = service

    def run(self):
        try:
            self.sample.emit(self.service.poll())
        finally:
            close = getattr(self.service.gateway, "close", None)
            if callable(close):
                close()


class ScaleMonitor(QObject):
    changed = pyqtSignal(object)
    # Retain a running thread through widget destruction until bounded I/O ends.
    _running = set()

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self._worker = None
        self._active = False
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self._active = True
        self._timer.start()
        self._tick()

    def stop(self):
        self._active = False
        self._timer.stop()
        self.service.invalidate("DISCONNECTED", "desconectada")

    def _tick(self):
        if not self._active:
            return
        self.changed.emit(self.service.current())
        if self._worker is not None:
            return
        worker = _ScaleWorker(self.service)
        QCoreApplication.instance().aboutToQuit.connect(worker.wait)
        self._worker = worker
        self._running.add(worker)
        worker.sample.connect(self._deliver)
        worker.finished.connect(lambda w=worker: self._running.discard(w))
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(self._finished)
        worker.start()

    def _finished(self):
        self._worker = None

    def _deliver(self, state):
        if self._active:
            self.changed.emit(state)
