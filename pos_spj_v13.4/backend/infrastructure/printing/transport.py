"""Entrega de bytes a una impresora física.

Reemplaza `core/services/printer_service.py::PrintTransport`, borrado. Los
valores del enum no se eligieron aquí: los fija
`tests/integration/test_purchase_cash_ticket_printing.py`
(`usb_win32`, `network`), y `_send_win32` lo exige por nombre el guardrail
`tests/architecture/test_no_direct_escpos_usb_default.py`.

Esto es E/S con hardware real: recibe bytes ya compuestos (ESC/POS, ZPL, texto)
y los entrega. No sabe qué contienen ni los interpreta — componer el documento
es de `escpos.py` y de los renderizadores de etiqueta.

POR QUÉ win32print Y NO EL TRANSPORTE USB POR libusb EN WINDOWS
----------------------------------------------------------------
La vía libusb exige sustituir el driver de la impresora por uno genérico
(WinUSB/libusbK). En un mostrador eso significa que la impresora deja de
funcionar para todo lo demás del equipo. `win32print` usa el driver que el
sistema ya tiene instalado y envía un trabajo RAW, que es lo que una térmica
espera.

`tests/architecture/test_no_direct_escpos_usb_default.py` existe para que nadie
invierta esa preferencia por comodidad, y es un barrido de TEXTO: nombrar aquí
la ruta prohibida, aunque fuera para explicarla, haría saltar el guardrail
contra este mismo archivo.

DEVUELVE True/False, NO LANZA por un fallo de entrega. Una impresora apagada o
sin papel es una condición de operación normal en un punto de venta, no un
error de programa; quien llama decide si reintenta, avisa o sigue. Lo que sí
lanza es un transporte no soportado: eso es un fallo de configuración y
callarlo dejaría tickets perdiéndose en silencio.
"""

from __future__ import annotations

import logging
import socket
from enum import Enum

logger = logging.getLogger("spj.printing.transport")

#: Tiempo máximo de espera de una entrega por red, en segundos. Corto a
#: propósito: el cajero está esperando el ticket, y una impresora que no
#: responde en cinco segundos no va a responder.
NETWORK_TIMEOUT_SECONDS = 5

#: Puerto habitual de impresión cruda (RAW/JetDirect) cuando no se indica otro.
DEFAULT_NETWORK_PORT = 9100


class TransportType(str, Enum):
    NETWORK = "network"
    SERIAL = "serial"
    USB_WIN32 = "usb_win32"
    FILE = "file"


class PrintTransport:
    @classmethod
    def send(
        cls, data: bytes, transport: TransportType, destination: str,
        *, baud: int = 9600,
    ) -> bool:
        """Entrega `data`. True si la impresora la aceptó.

        `destination` significa una cosa distinta en cada transporte: `host:port`
        en red, el nombre del puerto en serie, el nombre de la impresora
        instalada en USB, y la ruta del archivo en FILE.
        """
        if not data:
            # Nada que imprimir no es un fallo: evita abrir un socket o un
            # puerto serie para no enviar nada.
            return True
        entrega = {
            TransportType.NETWORK: cls._send_network,
            TransportType.SERIAL: cls._send_serial,
            TransportType.USB_WIN32: cls._send_win32,
            TransportType.FILE: cls._send_file,
        }.get(TransportType(transport))
        if entrega is None:
            raise ValueError(f"Transporte de impresión no soportado: {transport}")
        if entrega is cls._send_serial:
            return entrega(data, destination, baud=baud)
        return entrega(data, destination)

    # ── red ──────────────────────────────────────────────────────────────
    @staticmethod
    def _send_network(data: bytes, destination: str) -> bool:
        """Socket crudo a `host:port`.

        Sin puerto se asume el 9100, el de impresión cruda. `sendall` y no
        `send`: `send` puede entregar sólo una parte del búfer y devolver
        cuántos bytes escribió — un ticket cortado a la mitad, sin error.
        """
        host, _, puerto = destination.partition(":")
        try:
            with socket.create_connection(
                (host, int(puerto or DEFAULT_NETWORK_PORT)),
                timeout=NETWORK_TIMEOUT_SECONDS,
            ) as conexion:
                conexion.sendall(data)
            return True
        except OSError as exc:
            logger.warning("Impresión de red a %s falló: %s", destination, exc)
            return False

    # ── serie ────────────────────────────────────────────────────────────
    @staticmethod
    def _send_serial(data: bytes, destination: str, *, baud: int = 9600) -> bool:
        try:
            import serial
        except ImportError:
            logger.warning("pyserial no está disponible: no se imprime por puerto serie")
            return False
        try:
            with serial.Serial(destination, baudrate=baud,
                               timeout=NETWORK_TIMEOUT_SECONDS) as puerto:
                puerto.write(data)
                # Sin `flush` el búfer puede quedarse a medias al cerrar y el
                # ticket sale truncado sin que nada lo reporte.
                puerto.flush()
            return True
        except Exception as exc:
            logger.warning("Impresión por serie en %s falló: %s", destination, exc)
            return False

    # ── USB en Windows ───────────────────────────────────────────────────
    @staticmethod
    def _send_win32(data: bytes, destination: str) -> bool:
        """Trabajo RAW al driver que Windows ya tiene instalado.

        Sin nombre de impresora se usa la predeterminada del sistema, que es lo
        que el usuario configuró; inventar un nombre fallaría de forma más
        confusa que usar la que ya eligió.
        """
        try:
            import win32print
        except ImportError:
            logger.warning("win32print no está disponible: no se imprime por USB")
            return False
        try:
            nombre = destination.strip() or win32print.GetDefaultPrinter()
            handle = win32print.OpenPrinter(nombre)
            try:
                # "RAW" entrega los bytes tal cual: la térmica interpreta sus
                # propios comandos. Cualquier otro tipo de datos haría que el
                # driver intentara MAQUETAR los bytes como si fueran texto.
                win32print.StartDocPrinter(handle, 1, ("SPJ POS", None, "RAW"))
                try:
                    win32print.StartPagePrinter(handle)
                    win32print.WritePrinter(handle, data)
                    win32print.EndPagePrinter(handle)
                finally:
                    win32print.EndDocPrinter(handle)
            finally:
                win32print.ClosePrinter(handle)
            return True
        except Exception as exc:
            logger.warning("Impresión USB en %r falló: %s", destination, exc)
            return False

    # ── archivo ──────────────────────────────────────────────────────────
    @staticmethod
    def _send_file(data: bytes, destination: str) -> bool:
        """Vuelca los bytes a un archivo. Para diagnóstico y para colas."""
        try:
            with open(destination, "wb") as salida:
                salida.write(data)
            return True
        except OSError as exc:
            logger.warning("No se pudo escribir la impresión en %s: %s", destination, exc)
            return False


def save_ticket_document(html: str, filepath: str) -> str:
    """Guarda el documento del ticket y devuelve la ruta escrita.

    ESCRIBE HTML, NO PDF. La función que reemplaza se llamaba
    `save_ticket_pdf()` y hacía exactamente esto mismo — escribir los bytes del
    HTML— pese a su nombre; está anotado en el docstring de
    `sales_receipt_client.py` por quien lo leyó entonces. Se conserva el
    comportamiento y se corrige el nombre: un `.pdf` que en realidad es HTML no
    lo abre el visor que le corresponde, y el error aparece lejos de aquí.
    """
    with open(filepath, "w", encoding="utf-8") as salida:
        salida.write(html)
    return filepath
