
# hardware/lector_qr.py — SPJ POS v11
"""
Lector de código de barras / QR por USB HID (modo teclado).
Funciona con cualquier lector estándar: Honeywell, Datalogic, Symbol, etc.
También soporta lectores via puerto serie (RS-232).

Flujo:
  - LectorQR captura la cadena que el lector "escribe" terminada en Enter.
  - Analiza el prefijo para determinar el tipo (SPJ:CONT, SPJ:PROD, etc.)
  - Emite señal PyQt5 con la info parseada.
"""
from __future__ import annotations
import re, logging
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtWidgets import QApplication

logger = logging.getLogger("spj.hw.qr")

# Prefijos reconocidos por el sistema
PREFIJOS_QR = {
    "SPJ:CONT":   "contenedor",
    "SPJ:PROD":   "producto",
    "SPJ:FIDEL":  "cliente_fidelidad",
    "SPJ:DEL":    "ticket_delivery",
    "SPJ:MAP":    "mapa_entrega",
}


class LectorQR(QObject):
    """
    Intercepta la entrada del lector de QR/barras como event filter de teclado.
    El lector envía dígitos/letras seguidos de Enter en < 100ms.
    """
    codigo_leido   = pyqtSignal(str, str)   # (raw_code, tipo_qr)
    qr_contenedor  = pyqtSignal(str)         # uuid_qr
    qr_producto    = pyqtSignal(str)
    qr_fidelidad   = pyqtSignal(str)
    qr_delivery    = pyqtSignal(str)
    barcode_simple = pyqtSignal(str)         # código EAN/UPC
    qr_desconocido = pyqtSignal(str)         # QR sin prefijo SPJ (flujo legacy)

    _TIMEOUT_MS   = 120    # chars del lector en < 120ms
    _MIN_LEN      = 4
    _MAX_LEN      = 256

    def __init__(self, parent: QObject = None, activo: bool = True):
        super().__init__(parent)
        self._buffer  = []
        self._timer   = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._flush)
        self._activo  = activo

    def activar(self):
        self._activo = True
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    def desactivar(self):
        self._activo = False
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if not self._activo:
            return False
        from PyQt5.QtCore import QEvent
        from PyQt5.QtGui import QKeyEvent
        if event.type() == QEvent.KeyPress:
            key = event.key()
            from PyQt5.QtCore import Qt
            if key == Qt.Key_Return or key == Qt.Key_Enter:
                self._timer.stop()
                self._flush()
            elif event.text() and event.text().isprintable():
                self._buffer.append(event.text())
                self._timer.start(self._TIMEOUT_MS)
        return False

    def _flush(self):
        raw = "".join(self._buffer).strip()
        self._buffer.clear()
        if not raw or len(raw) < self._MIN_LEN or len(raw) > self._MAX_LEN:
            return
        tipo, uuid_qr = self._parsear(raw)
        logger.debug("QR leído: tipo=%s raw=%s", tipo, raw[:30])
        self.codigo_leido.emit(raw, tipo)
        if tipo == "contenedor":
            self.qr_contenedor.emit(uuid_qr)
        elif tipo == "producto":
            self.qr_producto.emit(uuid_qr)
        elif tipo == "cliente_fidelidad":
            self.qr_fidelidad.emit(uuid_qr)
        elif tipo == "ticket_delivery":
            self.qr_delivery.emit(uuid_qr)
        else:
            self.barcode_simple.emit(raw)
            self.qr_desconocido.emit(raw)

    def _parsear(self, raw: str) -> tuple:
        # Normalizar: eliminar espacios y comparar prefijo en mayúsculas
        # para tolerancia a lectores que envíen minúsculas o espacios extra.
        cleaned = raw.strip()
        upper = cleaned.upper()
        for prefijo, tipo in PREFIJOS_QR.items():
            needle = prefijo + ":"
            if upper.startswith(needle):
                uuid_qr = cleaned[len(needle):]
                return tipo, uuid_qr
        return "barcode", cleaned

    def simular_lectura(self, codigo: str):
        """Para pruebas: simula una lectura de QR."""
        self._buffer = list(codigo)
        self._flush()


class LectorQRSerial(QObject):
    """Lector conectado por puerto serie (RS-232 / USB-Serie)."""
    codigo_leido = pyqtSignal(str, str)

    def __init__(self, puerto: str = "/dev/ttyUSB0", baud: int = 9600):
        super().__init__()
        self._puerto = puerto
        self._baud   = baud
        self._serial = None
        self._thread = None
        self._activo = False

    def iniciar(self) -> bool:
        try:
            import serial, threading
            self._serial = serial.Serial(self._puerto, self._baud, timeout=1)
            self._activo = True
            self._thread = threading.Thread(
                target=self._loop, daemon=True, name="QRSerial")
            self._thread.start()
            logger.info("Lector QR serial en %s@%d", self._puerto, self._baud)
            return True
        except Exception as e:
            logger.error("QRSerial error: %s", e)
            return False

    def detener(self):
        self._activo = False
        if self._serial:
            try: self._serial.close()
            except Exception: pass

    def _loop(self):
        buf = b""
        while self._activo:
            try:
                ch = self._serial.read(1)
                if ch in (b"\r", b"\n"):
                    raw = buf.decode(errors="replace").strip()
                    buf = b""
                    if raw:
                        tipo = "barcode"
                        uuid_qr = raw
                        for p, t in PREFIJOS_QR.items():
                            if raw.startswith(p + ":"):
                                tipo   = t
                                uuid_qr = raw[len(p)+1:]
                        self.codigo_leido.emit(uuid_qr, tipo)
                else:
                    buf += ch
            except Exception:
                break
