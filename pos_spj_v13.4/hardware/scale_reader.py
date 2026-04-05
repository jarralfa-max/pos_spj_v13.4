# hardware/scale_reader.py — SPJ POS v13.30
"""
Lectura de báscula serial. Extraído de hardware_utils.py (Fase 12).
Solo contiene safe_serial_read — todo lo de impresión está en PrinterService.
"""
from __future__ import annotations
import re
import logging
from typing import Optional

logger = logging.getLogger("spj.scale")

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False


def safe_serial_read(
    port: str, baud: int, timeout: float = 2.0, encoding: str = "utf-8"
) -> float:
    """
    Lee un valor numérico (peso) desde un puerto serial.
    Retorna 0.0 si no hay lectura válida — nunca lanza.
    """
    if not HAS_SERIAL:
        return 0.0
    try:
        with serial.Serial(port, baud, timeout=timeout) as ser:
            ser.flushInput()
            line = ser.readline()
            if not line:
                return 0.0
            text = line.decode(encoding, errors="replace").strip()
            match = re.search(r"[\d]+\.?[\d]*", text)
            if match:
                return float(match.group())
            return 0.0
    except Exception as exc:
        logger.debug("safe_serial_read: %s", exc)
        return 0.0
