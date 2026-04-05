
# hardware/cajon_dinero.py — SPJ POS v11
"""
Control del cajón de dinero.
Se activa vía:
  1. Impresora ESC/POS (DK2 pin 2) — lo más común
  2. Puerto serie (RS-232) con pulso
  3. Puerto paralelo / GPIO (Raspberry Pi)
  4. Relé USB

El cajón se abre automáticamente al completar una venta en efectivo.
"""
from __future__ import annotations
import logging, threading
from PyQt5.QtCore import QObject, pyqtSignal

logger = logging.getLogger("spj.hw.cajon")

# Secuencia ESC/POS estándar para abrir cajón
# ESC p  <pin> <t1> <t2>
CMD_ABRIR_PIN2 = bytes([0x1B, 0x70, 0x00, 0x19, 0xFA])   # pin 2
CMD_ABRIR_PIN5 = bytes([0x1B, 0x70, 0x01, 0x19, 0xFA])   # pin 5


class CajonDinero(QObject):
    """Controla el cajón de dinero."""
    cajon_abierto = pyqtSignal()

    def __init__(self, modo: str = "escpos",
                 dispositivo: str = None,
                 ip: str = None, puerto: int = 9100,
                 pin: int = 2):
        super().__init__()
        self.modo       = modo          # escpos | serial | archivo | noop
        self.dispositivo = dispositivo
        self.ip          = ip
        self.puerto      = puerto
        self.pin         = pin          # 2 ó 5
        self._lock       = threading.Lock()

    def abrir(self) -> bool:
        cmd = CMD_ABRIR_PIN2 if self.pin == 2 else CMD_ABRIR_PIN5
        ok  = False
        with self._lock:
            if self.modo == "escpos":
                ok = self._abrir_escpos(cmd)
            elif self.modo == "serial":
                ok = self._abrir_serial(cmd)
            elif self.modo == "escpos_red":
                ok = self._abrir_tcp(cmd)
            elif self.modo == "archivo":
                ok = self._abrir_archivo(cmd)
            else:
                logger.debug("Cajón modo noop — no se abre físicamente")
                ok = True
        if ok:
            self.cajon_abierto.emit()
        return ok

    def _abrir_escpos(self, cmd: bytes) -> bool:
        try:
            from escpos.printer import Usb, Serial, Network
            # Intentar con python-escpos
            try:
                p = Usb(0x04B8, 0x0202)   # Epson TM-T20
            except Exception:
                try:
                    p = Serial(self.dispositivo or "/dev/ttyUSB0")
                except Exception:
                    return self._abrir_archivo(cmd)
            p._raw(cmd)
            logger.info("Cajón abierto via ESC/POS")
            return True
        except Exception as e:
            logger.warning("escpos abrir cajón: %s — fallback", e)
            return self._abrir_archivo(cmd)

    def _abrir_tcp(self, cmd: bytes) -> bool:
        import socket
        try:
            with socket.create_connection((self.ip, self.puerto), timeout=3) as s:
                s.sendall(cmd)
            logger.info("Cajón abierto via TCP %s:%d", self.ip, self.puerto)
            return True
        except Exception as e:
            logger.error("TCP cajón: %s", e)
            return False

    def _abrir_serial(self, cmd: bytes) -> bool:
        try:
            import serial
            with serial.Serial(self.dispositivo or "/dev/ttyS0", 9600, timeout=1) as s:
                s.write(cmd)
            return True
        except Exception as e:
            logger.error("Serial cajón: %s", e)
            return False

    def _abrir_archivo(self, cmd: bytes) -> bool:
        try:
            with open(self.dispositivo, "wb") as f:
                f.write(cmd)
            return True
        except Exception as e:
            logger.debug("Archivo cajón: %s", e)
            return False

    @staticmethod
    def from_config(conn) -> "CajonDinero":
        def _c(k, d=""):
            try:
                row = conn.execute("SELECT valor FROM configuraciones WHERE clave=?", (k,)).fetchone()
                return row[0] if row else d
            except Exception:
                return d
        return CajonDinero(
            modo        = _c("cajon_modo", "escpos"),
            dispositivo = _c("cajon_dispositivo") or None,
            ip          = _c("cajon_ip") or None,
            puerto      = int(_c("cajon_puerto", "9100")),
            pin         = int(_c("cajon_pin", "2")),
        )
