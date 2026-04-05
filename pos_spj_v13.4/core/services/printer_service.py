# core/services/printer_service.py — SPJ POS v13.30 — FASE 1
"""
PrinterService — servicio ÚNICO de impresión para todo el ERP.

Elimina la duplicación de 6 implementaciones separadas de envío a impresora.
Soporta: tickets ESC/POS, etiquetas ZPL/TSPL, documentos HTML→PDF.

Arquitectura:
    Módulo (ventas, etiquetas, caja, delivery...)
        ↓ submit_job()
    PrinterService
        ├── PrintQueue (thread-safe, prioridad)
        ├── Formatter (ESC/POS, ZPL, HTML)
        └── Transport (TCP, Serial, USB/Win32)

USO:
    printer = container.printer_service
    printer.print_ticket(ticket_data)           # ticket ESC/POS
    printer.print_label(label_data, printer_cfg) # etiqueta ZPL
    printer.print_html(html, paper_cfg)          # HTML→impresora sistema
"""
from __future__ import annotations
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, Callable, List
from datetime import datetime

logger = logging.getLogger("spj.printer")


# ══════════════════════════════════════════════════════════════════════════════
#  Enums y modelos
# ══════════════════════════════════════════════════════════════════════════════

class PrintJobType(str, Enum):
    TICKET = "ticket"
    LABEL = "label"
    HTML = "html"
    RAW = "raw"


class TransportType(str, Enum):
    NETWORK = "network"     # TCP/IP (ip:port)
    SERIAL = "serial"       # COM port
    USB_WIN32 = "usb_win32" # Windows print spooler
    SYSTEM = "system"       # QPrinter del sistema
    AUTO = "auto"           # Detectar por ubicación


class PrintJobStatus(str, Enum):
    QUEUED = "queued"
    PRINTING = "printing"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class PrintJob:
    """Trabajo de impresión encolable."""
    id: str = ""
    job_type: PrintJobType = PrintJobType.TICKET
    data: bytes = b""                  # Bytes listos para enviar
    raw_data: Dict[str, Any] = field(default_factory=dict)  # Datos originales
    transport: TransportType = TransportType.AUTO
    destination: str = ""              # IP:port, COM port, o printer name
    priority: int = 5                  # 1=urgente, 10=baja
    retries: int = 2
    status: PrintJobStatus = PrintJobStatus.QUEUED
    on_success: Optional[Callable] = None
    on_error: Optional[Callable] = None
    created_at: float = field(default_factory=time.time)
    error_msg: str = ""

    def __lt__(self, other):
        return self.priority < other.priority


# ══════════════════════════════════════════════════════════════════════════════
#  Transport Layer — envío unificado
# ══════════════════════════════════════════════════════════════════════════════

class PrintTransport:
    """Capa de transporte — envía bytes a cualquier tipo de impresora."""

    @staticmethod
    def send(data: bytes, transport: TransportType, destination: str) -> bool:
        """Envía bytes a la impresora según el tipo de transporte."""
        if transport == TransportType.AUTO:
            transport = PrintTransport.detect_type(destination)

        if transport == TransportType.NETWORK:
            return PrintTransport._send_tcp(data, destination)
        elif transport == TransportType.SERIAL:
            return PrintTransport._send_serial(data, destination)
        elif transport == TransportType.USB_WIN32:
            return PrintTransport._send_win32(data, destination)
        else:
            raise ValueError(f"Transporte no soportado: {transport}")

    @staticmethod
    def detect_type(destination: str) -> TransportType:
        """Auto-detecta el tipo de transporte por la ubicación."""
        if not destination:
            return TransportType.USB_WIN32
        d = destination.strip()
        if ':' in d and d.split(':')[0].replace('.', '').isdigit():
            return TransportType.NETWORK
        if d.upper().startswith('COM') or '/dev/tty' in d:
            return TransportType.SERIAL
        return TransportType.USB_WIN32

    @staticmethod
    def _send_tcp(data: bytes, destination: str) -> bool:
        import socket
        parts = destination.split(':')
        ip = parts[0].strip()
        port = int(parts[1]) if len(parts) > 1 else 9100
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        try:
            s.connect((ip, port))
            s.sendall(data)
            return True
        finally:
            s.close()

    @staticmethod
    def _send_serial(data: bytes, destination: str) -> bool:
        import serial
        with serial.Serial(destination, 9600, timeout=3) as sp:
            sp.write(data)
        return True

    @staticmethod
    def _send_win32(data: bytes, destination: str) -> bool:
        import win32print
        printer_name = destination or win32print.GetDefaultPrinter()
        hp = win32print.OpenPrinter(printer_name)
        try:
            hj = win32print.StartDocPrinter(hp, 1, ("SPJ Print", None, "RAW"))
            win32print.StartPagePrinter(hp)
            win32print.WritePrinter(hp, data)
            win32print.EndPagePrinter(hp)
            win32print.EndDocPrinter(hp)
            return True
        finally:
            win32print.ClosePrinter(hp)

    @staticmethod
    def is_available(transport: TransportType, destination: str) -> bool:
        """Verifica si la impresora está accesible."""
        try:
            if transport == TransportType.NETWORK or (
                    transport == TransportType.AUTO and ':' in destination):
                import socket
                parts = destination.split(':')
                s = socket.socket()
                s.settimeout(2)
                s.connect((parts[0].strip(), int(parts[1]) if len(parts) > 1 else 9100))
                s.close()
                return True
            return True  # Serial/USB: assume available
        except Exception:
            return False


# ══════════════════════════════════════════════════════════════════════════════
#  Print Queue — cola thread-safe con prioridad
# ══════════════════════════════════════════════════════════════════════════════

class PrintQueue:
    """Cola de impresión con worker thread y reintentos."""

    def __init__(self, max_size: int = 100):
        self._queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=max_size)
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        self._job_counter = 0
        self._lock = threading.Lock()
        # Stats
        self.total_printed = 0
        self.total_failed = 0

    def start(self):
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker, name="SPJ-PrintWorker", daemon=True)
        self._worker_thread.start()
        logger.info("Cola de impresión iniciada")

    def stop(self):
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        logger.info("Cola de impresión detenida (impresos=%d, fallos=%d)",
                     self.total_printed, self.total_failed)

    def submit(self, job: PrintJob):
        """Encola un trabajo de impresión."""
        with self._lock:
            self._job_counter += 1
            if not job.id:
                job.id = f"PJ-{self._job_counter:05d}"
        try:
            self._queue.put_nowait((job.priority, job.created_at, job))
            logger.debug("Job encolado: %s (%s → %s)",
                         job.id, job.job_type.value, job.destination or "default")
        except queue.Full:
            logger.error("Cola de impresión llena — trabajo descartado: %s", job.id)
            if job.on_error:
                job.on_error(Exception("Cola de impresión llena"))

    def _worker(self):
        while self._running:
            try:
                _, _, job = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            job.status = PrintJobStatus.PRINTING
            success = False

            for attempt in range(1, job.retries + 1):
                try:
                    PrintTransport.send(job.data, job.transport, job.destination)
                    success = True
                    job.status = PrintJobStatus.SUCCESS
                    self.total_printed += 1
                    logger.info("✅ Impreso: %s (%s, intento %d)",
                                job.id, job.job_type.value, attempt)
                    if job.on_success:
                        try:
                            job.on_success()
                        except Exception:
                            pass
                    break
                except Exception as e:
                    logger.warning("Impresión %s intento %d/%d falló: %s",
                                   job.id, attempt, job.retries, e)
                    if attempt < job.retries:
                        time.sleep(1)  # Esperar antes de reintentar

            if not success:
                job.status = PrintJobStatus.FAILED
                job.error_msg = str(e) if 'e' in dir() else "Unknown"
                self.total_failed += 1
                logger.error("❌ Impresión falló: %s tras %d intentos",
                             job.id, job.retries)
                if job.on_error:
                    try:
                        job.on_error(Exception(job.error_msg))
                    except Exception:
                        pass

            self._queue.task_done()

    @property
    def pending(self) -> int:
        return self._queue.qsize()


# ══════════════════════════════════════════════════════════════════════════════
#  PrinterService — API pública
# ══════════════════════════════════════════════════════════════════════════════

class PrinterService:
    """
    Servicio central de impresión para todo el ERP.
    Reemplaza: hardware_utils, ticket_escpos_renderer.send(),
               impresora_etiquetas, etiquetas._send_to_printer.
    """

    def __init__(self, db_conn=None, module_config=None):
        self.db = db_conn
        self._module_config = module_config
        self.queue = PrintQueue()
        self._ticket_cfg: Dict = {}
        self._label_cfg: Dict = {}
        self._enabled = True
        self.queue.start()
        self._load_configs()

    @property
    def enabled(self) -> bool:
        if self._module_config:
            return self._module_config.is_enabled('printing')
        return self._enabled

    def _load_configs(self):
        """Carga configuración de impresoras desde la BD."""
        if not self.db:
            return
        try:
            # Ticket printer
            for key in ('ticket', 'impresora'):
                rows = self.db.execute(
                    "SELECT clave, valor FROM configuraciones_hardware "
                    "WHERE tipo=?", (key,)
                ).fetchall()
                if rows:
                    self._ticket_cfg = {r[0]: r[1] for r in rows}
                    break
        except Exception:
            pass
        try:
            # Label printer
            for key in ('etiquetas', 'impresora_etiquetas'):
                rows = self.db.execute(
                    "SELECT clave, valor FROM configuraciones_hardware "
                    "WHERE tipo=?", (key,)
                ).fetchall()
                if rows:
                    self._label_cfg = {r[0]: r[1] for r in rows}
                    break
        except Exception:
            pass

    def reload_configs(self):
        self._load_configs()

    # ── API de tickets ────────────────────────────────────────────────────────

    def print_ticket(self, ticket_data: Dict[str, Any],
                     on_success: Callable = None,
                     on_error: Callable = None) -> str:
        """
        Imprime un ticket de venta/corte. Retorna el job_id.
        Genera ESC/POS automáticamente usando TicketESCPOSRenderer.
        """
        if not self._enabled:
            logger.debug("Impresión deshabilitada")
            return ""

        try:
            from core.ticket_escpos_renderer import TicketESCPOSRenderer
            paper_w = int(self._ticket_cfg.get('paper_width',
                          self._get_cfg('ticket_paper_width', '80')))
            renderer = TicketESCPOSRenderer(paper_width_mm=paper_w)

            logo_b64 = self._get_cfg('ticket_logo_b64', '')
            qr_content = ""
            if self._get_cfg('ticket_qr_enabled', '0') == '1':
                qr_content = (self._get_cfg('ticket_qr_url', '') or
                              ticket_data.get('folio', ''))

            # Enriquecer datos
            ticket_data.setdefault('empresa', self._get_cfg('nombre_empresa', 'SPJ POS'))
            ticket_data.setdefault('direccion', self._get_cfg('direccion', ''))
            ticket_data.setdefault('telefono', self._get_cfg('telefono_empresa', ''))

            data = renderer.render(ticket_data, logo_b64=logo_b64,
                                   qr_content=qr_content)
        except Exception as e:
            logger.error("Error formateando ticket: %s", e)
            if on_error:
                on_error(e)
            return ""

        dest = self._ticket_cfg.get('ubicacion', '')
        job = PrintJob(
            job_type=PrintJobType.TICKET,
            data=data,
            raw_data=ticket_data,
            destination=dest,
            priority=2,  # Tickets tienen alta prioridad
            on_success=on_success,
            on_error=on_error,
        )
        self.queue.submit(job)
        return job.id

    # ── API de etiquetas ──────────────────────────────────────────────────────

    def print_label(self, label_data: bytes,
                    printer_cfg: Dict = None,
                    on_success: Callable = None,
                    on_error: Callable = None) -> str:
        """Imprime una etiqueta (bytes ZPL/TSPL/imagen ya formateados)."""
        if not self._enabled:
            return ""

        cfg = printer_cfg or self._label_cfg
        dest = cfg.get('ubicacion', '')

        job = PrintJob(
            job_type=PrintJobType.LABEL,
            data=label_data,
            destination=dest,
            priority=5,
            on_success=on_success,
            on_error=on_error,
        )
        self.queue.submit(job)
        return job.id

    # ── API raw ───────────────────────────────────────────────────────────────

    def print_raw(self, data: bytes, destination: str = "",
                  priority: int = 5) -> str:
        """Envía bytes raw a cualquier impresora."""
        if not self._enabled:
            return ""
        dest = destination or self._ticket_cfg.get('ubicacion', '')
        job = PrintJob(
            job_type=PrintJobType.RAW,
            data=data,
            destination=dest,
            priority=priority,
        )
        self.queue.submit(job)
        return job.id

    # ── Config helpers ────────────────────────────────────────────────────────

    def _get_cfg(self, key: str, default: str = "") -> str:
        if not self.db:
            return default
        try:
            r = self.db.execute(
                "SELECT valor FROM configuraciones WHERE clave=?", (key,)
            ).fetchone()
            return r[0] if r and r[0] else default
        except Exception:
            return default

    def has_ticket_printer(self) -> bool:
        return bool(self._ticket_cfg.get('ubicacion', ''))

    def has_label_printer(self) -> bool:
        return bool(self._label_cfg.get('ubicacion', ''))

    def get_status(self) -> Dict:
        return {
            "enabled": self._enabled,
            "queue_pending": self.queue.pending,
            "total_printed": self.queue.total_printed,
            "total_failed": self.queue.total_failed,
            "ticket_printer": self._ticket_cfg.get('ubicacion', 'N/A'),
            "label_printer": self._label_cfg.get('ubicacion', 'N/A'),
        }

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        logger.info("PrinterService %s", "activado" if enabled else "desactivado")

    def close(self):
        self.queue.stop()
