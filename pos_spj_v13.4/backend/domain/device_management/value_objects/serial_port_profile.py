"""SerialPortProfile — connection details for SERIAL-connected devices
(most scales, some legacy printers). See §18-19.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.device_management.exceptions import DeviceInvalidValueError

_STANDARD_BAUD_RATES = frozenset({300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200})
_PARITIES = frozenset({"N", "E", "O"})
_STOP_BITS = frozenset({"1", "1.5", "2"})


@dataclass(frozen=True, slots=True)
class SerialPortProfile:
    port: str
    baud_rate: int
    parity: str = "N"
    data_bits: int = 8
    stop_bits: str = "1"
    read_timeout_seconds: Decimal = Decimal("2")

    @classmethod
    def create(
        cls, *, port: str, baud_rate: int, parity: str = "N", data_bits: int = 8,
        stop_bits: str = "1", read_timeout_seconds: Decimal = Decimal("2"),
    ) -> "SerialPortProfile":
        if not port.strip():
            raise DeviceInvalidValueError("port es obligatorio (p. ej. 'COM3', '/dev/ttyUSB0')")
        if baud_rate not in _STANDARD_BAUD_RATES:
            raise DeviceInvalidValueError(
                f"baud_rate {baud_rate!r} no es un valor estándar {sorted(_STANDARD_BAUD_RATES)}"
            )
        normalized_parity = parity.strip().upper()
        if normalized_parity not in _PARITIES:
            raise DeviceInvalidValueError(f"parity debe ser uno de {sorted(_PARITIES)}, recibido {parity!r}")
        if data_bits not in (5, 6, 7, 8):
            raise DeviceInvalidValueError(f"data_bits debe estar entre 5 y 8, recibido {data_bits!r}")
        normalized_stop_bits = str(stop_bits).strip()
        if normalized_stop_bits not in _STOP_BITS:
            raise DeviceInvalidValueError(f"stop_bits debe ser uno de {sorted(_STOP_BITS)}, recibido {stop_bits!r}")
        if isinstance(read_timeout_seconds, bool) or isinstance(read_timeout_seconds, float) or not isinstance(read_timeout_seconds, Decimal):
            raise DeviceInvalidValueError("read_timeout_seconds debe ser Decimal, nunca float")
        if read_timeout_seconds <= 0:
            raise DeviceInvalidValueError("read_timeout_seconds debe ser positivo")
        return cls(port.strip(), baud_rate, normalized_parity, data_bits, normalized_stop_bits, read_timeout_seconds)
