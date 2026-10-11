"""PeriodicTaskService — CRM-43.

La primera implementación real de `BackgroundService`: corre una tarea al
arrancar (en el siguiente ciclo de eventos, ya con la ventana armada) y luego
cada `interval_ms`, con un `QTimer` en el hilo de la interfaz — el mismo hilo
dueño de la conexión SQLite, así que no hay acceso concurrente.

Una tarea que lanza excepción se registra en el log y el temporizador sigue: un
fallo de una pasada no apaga el servicio ni cierra la aplicación.
"""
from __future__ import annotations

import logging
from typing import Callable

from PyQt5.QtCore import QTimer

logger = logging.getLogger(__name__)


class PeriodicTaskService:
    def __init__(self, task: Callable[[], object], *, interval_ms: int,
                 run_on_start: bool = True, name: str = "") -> None:
        if interval_ms <= 0:
            raise ValueError("interval_ms debe ser positivo.")
        self._task = task
        self._interval_ms = interval_ms
        self._run_on_start = run_on_start
        self._name = name or getattr(task, "__name__", "tarea")
        self._timer: QTimer | None = None
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    def start(self) -> None:
        if self._timer is None:
            self._timer = QTimer()
            self._timer.setInterval(self._interval_ms)
            self._timer.timeout.connect(self.run_once)
        self._active = True
        self._timer.start()
        if self._run_on_start:
            QTimer.singleShot(0, self.run_once)

    def stop(self) -> None:
        self._active = False
        if self._timer is not None:
            self._timer.stop()

    def run_once(self) -> None:
        if not self._active:
            return
        try:
            self._task()
        except Exception:  # noqa: BLE001 — una pasada fallida no detiene el servicio
            logger.exception("Falló la tarea periódica %s", self._name)
