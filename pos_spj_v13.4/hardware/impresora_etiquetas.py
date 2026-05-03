
# hardware/impresora_etiquetas.py — SPJ POS v11
"""
Driver para impresoras de etiquetas térmicas.
Soporta: Zebra (ZPL), TSC (TSPL), Brother (PT-P), impresión por USB/red/serie.
Fallback automático: guarda PDF + HTML si no hay impresora.
"""
from __future__ import annotations
import socket, os, logging, threading
from typing import Literal

logger = logging.getLogger("spj.hw.labels")

Protocolo = Literal["zpl", "tspl", "brother", "auto"]


class ImpresoraEtiquetas:
    """
    Interfaz unificada para impresoras de etiquetas.
    Detecta automáticamente el protocolo si protocolo='auto'.
    """

    def __init__(self, protocolo: Protocolo = "auto",
                 puerto_usb: str = None,
                 ip: str = None, puerto_tcp: int = 9100,
                 puerto_serial: str = None, baud: int = 9600):
        self.protocolo    = protocolo
        self.puerto_usb   = puerto_usb
        self.ip           = ip
        self.puerto_tcp   = puerto_tcp
        self.puerto_serial = puerto_serial
        self.baud         = baud
        self._lock        = threading.Lock()

    # ── Impresión ──────────────────────────────────────────────────
    def imprimir(self, comandos: str, copias: int = 1) -> bool:
        """Envía comandos a la impresora. Retorna True si OK."""
        payload = (comandos * copias).encode("utf-8", errors="replace")
        with self._lock:
            if self.ip:
                return self._imprimir_tcp(payload)
            if self.puerto_serial:
                return self._imprimir_serial(payload)
            if self.puerto_usb:
                return self._imprimir_usb(payload)
            return self._imprimir_archivo(comandos)

    def imprimir_etiqueta(self, tipo: str, datos: dict,
                          formato: str = None, copias: int = 1) -> bool:
        """Genera y envía etiqueta de un tipo determinado."""
        from labels.diseno_etiquetas import DisenoEtiquetas
        fmt = formato or (
            "tspl" if self.protocolo == "tspl" else "zpl"
        )
        if self.protocolo == "auto":
            fmt = self._detectar_formato()
        comandos = DisenoEtiquetas.get_commands(tipo, datos, fmt)
        return self.imprimir(comandos, copias)

    def imprimir_imagen(self, png_bytes: bytes, copias: int = 1) -> bool:
        """Imprime imagen PNG directamente (para impresoras con driver)."""
        try:
            import tempfile, subprocess
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(png_bytes); tmp = f.name
            if os.name == "nt":
                os.startfile(tmp, "print")
            else:
                subprocess.run(["lp", tmp], capture_output=True)
            return True
        except Exception as e:
            logger.error("imprimir_imagen: %s", e)
            return False

    # ── Canales ────────────────────────────────────────────────────
    def _imprimir_tcp(self, payload: bytes) -> bool:
        try:
            with socket.create_connection((self.ip, self.puerto_tcp), timeout=5) as s:
                s.sendall(payload)
            logger.info("Etiqueta enviada a %s:%d (%d bytes)",
                        self.ip, self.puerto_tcp, len(payload))
            return True
        except Exception as e:
            logger.error("TCP label print error: %s", e)
            return False

    def _imprimir_serial(self, payload: bytes) -> bool:
        try:
            import serial
            with serial.Serial(self.puerto_serial, self.baud, timeout=3) as s:
                s.write(payload)
            return True
        except Exception as e:
            logger.error("Serial label print error: %s", e)
            return False

    def _imprimir_usb(self, payload: bytes) -> bool:
        try:
            with open(self.puerto_usb, "wb") as f:
                f.write(payload)
            return True
        except Exception as e:
            logger.error("USB label print error: %s", e)
            return False

    def _imprimir_archivo(self, comandos: str) -> bool:
        """Fallback: guarda los comandos en archivo para debug."""
        os.makedirs("exports/labels", exist_ok=True)
        from datetime import datetime
        fname = f"exports/labels/etiqueta_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(comandos)
        logger.warning("Sin impresora configurada — guardado en %s", fname)
        return True

    def _detectar_formato(self) -> str:
        """Intenta detectar el protocolo enviando un comando de status."""
        try:
            if self.ip:
                with socket.create_connection((self.ip, self.puerto_tcp), timeout=2) as s:
                    s.sendall(b"~HS\r\n")   # ZPL status
                    resp = s.recv(64)
                    if resp:
                        return "zpl"
        except Exception:
            pass
        return "zpl"    # default

    # ── Utilidades ──────────────────────────────────────────────────
    def test_conexion(self) -> dict:
        if self.ip:
            try:
                socket.create_connection((self.ip, self.puerto_tcp), timeout=2).close()
                return {"ok": True, "canal": f"TCP {self.ip}:{self.puerto_tcp}"}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if self.puerto_usb:
            ok = os.path.exists(self.puerto_usb)
            return {"ok": ok, "canal": self.puerto_usb}
        return {"ok": False, "error": "Sin impresora configurada"}

    @staticmethod
    def from_config(conn) -> "ImpresoraEtiquetas":
        """Construye instancia desde configuración en BD."""
        def _cfg(k, default=""):
            try:
                row = conn.execute(
                    "SELECT valor FROM configuraciones WHERE clave=?", (k,)).fetchone()
                return row[0] if row else default
            except Exception:
                return default
        return ImpresoraEtiquetas(
            protocolo   = _cfg("label_printer_protocol", "zpl"),
            ip          = _cfg("label_printer_ip")          or None,
            puerto_tcp  = int(_cfg("label_printer_port", "9100")),
            puerto_usb  = _cfg("label_printer_usb")         or None,
            puerto_serial=_cfg("label_printer_serial")      or None,
        )
