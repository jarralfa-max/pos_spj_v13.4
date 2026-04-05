
# core/auth/session_timeout.py — SPJ POS v10
"""
Monitor de inactividad de sesion.
Si el usuario no interactua en N minutos, cierra la sesion automaticamente.
Configurable en BD (clave: session_timeout_minutes, default: 30).
"""
from __future__ import annotations
import time, threading, logging
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtWidgets import QApplication

logger = logging.getLogger("spj.auth.timeout")

DEFAULT_TIMEOUT_MINUTES = 30
WARNING_SECONDS_BEFORE  = 60   # aviso 1 minuto antes


class SessionTimeoutMonitor(QObject):
    """
    Instalado como event filter en QApplication.
    Resetea el timer en cada evento del usuario.
    Emite sesion_expirada cuando se agota el tiempo.
    """
    sesion_expirada = pyqtSignal()
    advertencia     = pyqtSignal(int)   # segundos restantes

    def __init__(self, timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES,
                 parent: QObject = None):
        super().__init__(parent)
        self._timeout_ms  = timeout_minutes * 60 * 1000
        self._warning_ms  = self._timeout_ms - (WARNING_SECONDS_BEFORE * 1000)
        self._activo      = False
        self._warned      = False

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

        self._warn_timer = QTimer(self)
        self._warn_timer.setSingleShot(True)
        self._warn_timer.timeout.connect(self._on_warning)

    def iniciar(self) -> None:
        self._activo = True
        self._warned = False
        self._reset()
        logger.debug("Session timeout monitor iniciado (%d min)", self._timeout_ms // 60000)

    def detener(self) -> None:
        self._activo = False
        self._timer.stop()
        self._warn_timer.stop()

    def _reset(self) -> None:
        if not self._activo:
            return
        self._warned = False
        self._timer.stop()
        self._warn_timer.stop()
        self._timer.start(self._timeout_ms)
        if self._warning_ms > 0:
            self._warn_timer.start(self._warning_ms)

    def eventFilter(self, obj, event) -> bool:
        """Intercepta eventos de teclado/mouse para resetear el timer."""
        from PyQt5.QtCore import QEvent
        if self._activo and event.type() in (
            QEvent.MouseMove, QEvent.MouseButtonPress,
            QEvent.KeyPress, QEvent.TouchBegin,
        ):
            self._reset()
        return False  # no bloquear el evento

    def _on_warning(self) -> None:
        if self._activo and not self._warned:
            self._warned = True
            secs = (self._timeout_ms - self._warning_ms) // 1000
            self.advertencia.emit(secs)
            logger.debug("Session timeout warning: %d segundos restantes", secs)

    def _on_timeout(self) -> None:
        if self._activo:
            self.detener()
            logger.info("Session expirada por inactividad")
            self.sesion_expirada.emit()

    @staticmethod
    def from_config(conn) -> "SessionTimeoutMonitor":
        mins = DEFAULT_TIMEOUT_MINUTES
        try:
            row = conn.execute(
                "SELECT valor FROM configuraciones WHERE clave='session_timeout_minutes'"
            ).fetchone()
            if row:
                mins = max(5, int(row[0]))
        except Exception:
            pass
        return SessionTimeoutMonitor(timeout_minutes=mins)
