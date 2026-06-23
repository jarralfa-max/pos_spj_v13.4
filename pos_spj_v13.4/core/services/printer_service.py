# core/services/printer_service.py — SPJ POS
"""Canonical printing service.

The printing service is the last defensive boundary before ESC/POS rendering.
It must not invent sale totals, but it may hydrate display-only ticket metadata
(product name, product unit and customer name) from the canonical database when
upstream sales payloads are incomplete.
"""
from __future__ import annotations

import logging
import os
import queue
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("spj.printer")


class PrintJobType(str, Enum):
    TICKET = "ticket"
    RAFFLE_TICKET = "raffle_ticket"
    LABEL = "label"
    HTML = "html"
    RAW = "raw"


class TransportType(str, Enum):
    NETWORK = "network"
    SERIAL = "serial"
    USB_WIN32 = "usb_win32"
    SYSTEM = "system"
    FILE = "file"
    AUTO = "auto"


class PrintJobStatus(str, Enum):
    QUEUED = "queued"
    PRINTING = "printing"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class ValidationResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    transport: str = ""
    destination: str = ""


@dataclass
class PrintJob:
    id: str = ""
    job_type: PrintJobType = PrintJobType.TICKET
    data: bytes = b""
    raw_data: Dict[str, Any] = field(default_factory=dict)
    transport: TransportType = TransportType.AUTO
    destination: str = ""
    baud: int = 9600
    priority: int = 5
    retries: int = 2
    status: PrintJobStatus = PrintJobStatus.QUEUED
    on_success: Optional[Callable] = None
    on_error: Optional[Callable] = None
    created_at: float = field(default_factory=time.time)
    error_msg: str = ""

    def __lt__(self, other):
        return self.priority < other.priority


class PrintTransport:
    @staticmethod
    def detect_type(destination: str) -> TransportType:
        if not destination:
            return TransportType.USB_WIN32
        d = str(destination).strip()
        if ":" in d and d.split(":")[0].replace(".", "").isdigit():
            return TransportType.NETWORK
        if d.upper().startswith("COM") or "/dev/tty" in d:
            return TransportType.SERIAL
        if d.startswith(("/", "./", "../")) or d.endswith(".prn") or "/dev/usb/" in d:
            return TransportType.FILE
        return TransportType.USB_WIN32

    @staticmethod
    def send(data: bytes, transport: TransportType, destination: str, baud: int = 9600) -> bool:
        if transport == TransportType.AUTO:
            transport = PrintTransport.detect_type(destination)
        if transport == TransportType.NETWORK:
            return PrintTransport._send_tcp(data, destination)
        if transport == TransportType.SERIAL:
            return PrintTransport._send_serial(data, destination, baud=baud)
        if transport == TransportType.FILE:
            return PrintTransport._send_file(data, destination)
        if transport in (TransportType.USB_WIN32, TransportType.SYSTEM):
            return PrintTransport._send_win32(data, destination)
        raise ValueError(f"Transporte no soportado: {transport}")

    @staticmethod
    def _send_tcp(data: bytes, destination: str) -> bool:
        parts = str(destination).split(":")
        host = parts[0].strip()
        port = int(parts[1]) if len(parts) > 1 else 9100
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((host, port))
            s.sendall(data)
        return True

    @staticmethod
    def _send_serial(data: bytes, destination: str, baud: int = 9600) -> bool:
        try:
            import serial as _serial
        except ImportError:
            logger.warning("pyserial no instalado — canal SERIAL no disponible")
            return False
        with _serial.Serial(destination, baud, timeout=3) as sp:
            sp.write(data)
        return True

    @staticmethod
    def _send_file(data: bytes, destination: str) -> bool:
        with open(destination, "wb") as f:
            f.write(data)
        return True

    @staticmethod
    def _send_win32(data: bytes, destination: str) -> bool:
        import win32print
        printer_name = destination or win32print.GetDefaultPrinter()
        hp = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(hp, 1, ("SPJ Ticket", None, "RAW"))
            win32print.StartPagePrinter(hp)
            win32print.WritePrinter(hp, data)
            win32print.EndPagePrinter(hp)
            win32print.EndDocPrinter(hp)
            return True
        finally:
            win32print.ClosePrinter(hp)

    @staticmethod
    def is_available(transport: TransportType, destination: str) -> bool:
        try:
            if transport == TransportType.AUTO:
                transport = PrintTransport.detect_type(destination)
            if transport == TransportType.NETWORK:
                parts = str(destination).split(":")
                host = parts[0].strip()
                port = int(parts[1]) if len(parts) > 1 else 9100
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1.5)
                    s.connect((host, port))
                return True
            if transport == TransportType.FILE:
                parent = os.path.dirname(destination) or "."
                return os.path.isdir(parent) and os.access(parent, os.W_OK)
            if transport == TransportType.SERIAL:
                import serial as _serial
                with _serial.Serial(destination, 9600, timeout=0.5):
                    pass
                return True
            if transport in (TransportType.USB_WIN32, TransportType.SYSTEM):
                import win32print
                printer_name = destination or win32print.GetDefaultPrinter()
                hp = win32print.OpenPrinter(printer_name)
                win32print.ClosePrinter(hp)
                return True
            return False
        except Exception:
            return False


class PrintQueue:
    def __init__(self, max_size: int = 100):
        self._queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=max_size)
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        self._job_counter = 0
        self._lock = threading.Lock()
        self.total_printed = 0
        self.total_failed = 0
        self._bus = None
        self._db = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker, name="SPJ-PrintWorker", daemon=True)
        self._worker_thread.start()
        logger.info("Cola de impresión iniciada")

    def stop(self) -> None:
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        logger.info("Cola de impresión detenida (impresos=%d, fallos=%d)", self.total_printed, self.total_failed)

    def submit(self, job: PrintJob) -> None:
        with self._lock:
            self._job_counter += 1
            if not job.id:
                job.id = f"PJ-{self._job_counter:05d}"
        try:
            self._queue.put_nowait((job.priority, job.created_at, job))
            logger.debug("Job encolado: %s (%s → %s)", job.id, job.job_type.value, job.destination or "default")
        except queue.Full:
            logger.error("Cola de impresión llena — trabajo descartado: %s", job.id)
            if job.on_error:
                job.on_error(Exception("Cola de impresión llena"))

    def _worker(self) -> None:
        while self._running:
            try:
                _, _, job = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            job.status = PrintJobStatus.PRINTING
            success = False
            last_error: Optional[Exception] = None
            attempt = 0
            for attempt in range(1, job.retries + 1):
                try:
                    ok = PrintTransport.send(job.data, job.transport, job.destination, baud=job.baud)
                    if not ok:
                        raise RuntimeError(f"Transport returned False: {job.transport.value} -> {job.destination}")
                    success = True
                    job.status = PrintJobStatus.SUCCESS
                    self.total_printed += 1
                    logger.info("✅ Impreso: %s (%s, intento %d)", job.id, job.job_type.value, attempt)
                    if job.on_success:
                        try:
                            job.on_success()
                        except Exception:
                            logger.exception("Print on_success callback failed job=%s", job.id)
                    self._publish_success(job)
                    break
                except Exception as exc:
                    last_error = exc
                    logger.warning("Impresión %s intento %d/%d falló: %s", job.id, attempt, job.retries, exc)
                    if attempt < job.retries:
                        time.sleep(1)
            if not success:
                job.status = PrintJobStatus.FAILED
                job.error_msg = str(last_error) if last_error else "Unknown"
                self.total_failed += 1
                logger.error("❌ Impresión falló: %s tras %d intentos", job.id, job.retries)
                if job.on_error:
                    try:
                        job.on_error(Exception(job.error_msg))
                    except Exception:
                        logger.exception("Print on_error callback failed job=%s", job.id)
                self._publish_failure(job)
            self._log_job_to_db(job, attempt if success else job.retries)
            self._queue.task_done()

    def _publish_success(self, job: PrintJob) -> None:
        if not self._bus:
            return
        try:
            from core.events.event_bus import TICKET_IMPRESO
            rd = job.raw_data or {}
            self._bus.publish(TICKET_IMPRESO, {
                "job_id": job.id,
                "job_type": job.job_type.value,
                "destination": job.destination,
                "folio": rd.get("folio", ""),
                "total": rd.get("totales", {}).get("total_final", rd.get("total", 0)),
            }, async_=True)
        except Exception:
            logger.exception("Failed publishing TICKET_IMPRESO for job=%s", job.id)

    def _publish_failure(self, job: PrintJob) -> None:
        if not self._bus:
            return
        try:
            from core.events.event_bus import PRINT_FAILED
            self._bus.publish(PRINT_FAILED, {
                "job_id": job.id,
                "job_type": job.job_type.value,
                "destination": job.destination,
                "error_msg": job.error_msg,
                "retries": job.retries,
            }, async_=True)
        except Exception:
            logger.exception("Failed publishing PRINT_FAILED for job=%s", job.id)

    def _log_job_to_db(self, job: PrintJob, reintentos: int) -> None:
        if not self._db:
            return
        try:
            rd = job.raw_data or {}
            self._db.execute(
                """
                INSERT INTO print_job_log
                    (job_id, job_type, plantilla, impresora, folio, estado,
                     reintentos, total, error_msg, finished_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    job.id,
                    job.job_type.value,
                    rd.get("plantilla", rd.get("ticket_type", "")),
                    job.destination or "",
                    rd.get("folio", ""),
                    job.status.value,
                    max(0, reintentos - 1),
                    float(rd.get("totales", {}).get("total_final", rd.get("total", 0)) or 0),
                    job.error_msg or "",
                    datetime.now(getattr(datetime, "UTC", timezone.utc)).isoformat(),
                ),
            )
            try:
                self._db.commit()
            except Exception as exc:
                logger.warning("print_job_log commit failed: %s", exc)
        except Exception as exc:
            logger.debug("print_job_log insert failed: %s", exc)

    @property
    def pending(self) -> int:
        return self._queue.qsize()


class PrinterService:
    def __init__(self, db_conn=None, module_config=None):
        self.db = db_conn
        self._module_config = module_config
        self.queue = PrintQueue()
        self._ticket_cfg: Dict[str, Any] = {}
        self._label_cfg: Dict[str, Any] = {}
        self._enabled = True
        try:
            from core.events.event_bus import get_bus
            self.queue._bus = get_bus()
        except Exception as exc:
            logger.warning("PrinterService sin EventBus; eventos de impresión no se publicarán: %s", exc)
        self.queue._db = db_conn
        self.queue.start()
        self._load_configs()

    @property
    def enabled(self) -> bool:
        if self._module_config:
            return self._module_config.is_enabled("printing")
        return self._enabled

    def _load_configs(self) -> None:
        self._ticket_cfg = {}
        self._label_cfg = {}
        if not self.db:
            return
        try:
            from core.repositories.hardware_config_repository import HardwareConfigRepository
            repo = HardwareConfigRepository(self.db)
            repo.ensure_schema()
            repo.seed_defaults()
            # Legacy configuraciones_hardware bridge lives in migrations only,
            # never at runtime (FASE 5 — single hardware source: hardware_config).
            self._ticket_cfg = self._normalize_ticket_cfg(repo.get_config("ticket"))
            self._label_cfg = self._normalize_label_cfg(repo.get_config("etiquetas"))
            logger.info(
                "Configuración de impresoras cargada desde hardware_config: ticket=%s etiquetas=%s mode=%s model=%s",
                bool(self._ticket_cfg.get("ubicacion")),
                bool(self._label_cfg.get("ubicacion")),
                self._ticket_cfg.get("escpos_mode"),
                self._ticket_cfg.get("printer_model"),
            )
        except Exception:
            logger.exception("No se pudo cargar configuración canónica de impresoras desde hardware_config")

    def reload_configs(self) -> None:
        self._load_configs()

    @staticmethod
    def _bool_cfg(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "si", "sí", "yes", "on", "raw", "enabled"}

    @staticmethod
    def _normalize_ticket_cfg(raw: Dict[str, Any]) -> Dict[str, Any]:
        raw = dict(raw or {})
        tipo = str(raw.get("tipo") or raw.get("transport") or raw.get("metodo") or "").strip()
        tipo_l = tipo.lower()
        tipo_idx = raw.get("tipo_idx", None)
        transport = raw.get("transport") or raw.get("metodo")
        if not transport:
            try:
                idx = int(tipo_idx)
            except Exception:
                idx = None
            if idx == 0 or "win32" in tipo_l or "windows" in tipo_l or "usb" in tipo_l:
                transport = "usb_win32"
            elif idx in (1, 3) or "serial" in tipo_l or "com" in tipo_l:
                transport = "serial"
            elif idx == 2 or "red" in tipo_l or "tcp" in tipo_l or "ip" in tipo_l:
                transport = "network"
            else:
                transport = "auto"
        ancho = str(raw.get("ancho") or raw.get("paper_width") or ("58" if "58" in str(raw.get("modelo", raw.get("printer_model", ""))).lower() else "80"))
        paper_width = 58 if "58" in ancho else 80
        mode_raw = str(raw.get("escpos_mode") or raw.get("modo_impresion") or "raw").strip().lower()
        escpos_mode = "text_diagnostic" if mode_raw in {"text", "safe_text", "diagnostic", "text_diagnostic"} else "raw"
        return {
            "ubicacion": str(raw.get("ubicacion") or raw.get("puerto") or raw.get("printer_name") or "").strip(),
            "transport": str(transport).strip().lower(),
            "printer_model": str(raw.get("modelo") or raw.get("printer_model") or "").strip(),
            "paper_width": int(raw.get("paper_width") or paper_width),
            "baud_rate": int(raw.get("baud_rate") or raw.get("baud") or 9600),
            "encoding": str(raw.get("encoding") or "cp850"),
            "corte": bool(raw.get("corte", True)),
            "abrir_cajon": bool(raw.get("abrir_cajon", False)),
            "escpos_mode": escpos_mode,
            "print_logo": PrinterService._bool_cfg(raw.get("print_logo"), True),
            "print_qr": PrinterService._bool_cfg(raw.get("print_qr"), True),
        }

    @staticmethod
    def _normalize_label_cfg(raw: Dict[str, Any]) -> Dict[str, Any]:
        raw = dict(raw or {})
        tipo = str(raw.get("tipo") or raw.get("transport") or "").lower()
        if "red" in tipo or "network" in tipo or "tcp" in tipo:
            transport = "network"
        elif "serial" in tipo or "com" in tipo:
            transport = "serial"
        elif raw.get("transport"):
            transport = raw.get("transport")
        else:
            transport = "usb_win32"
        return {
            "ubicacion": str(raw.get("ubicacion") or raw.get("puerto") or "").strip(),
            "transport": str(transport).strip().lower(),
            "baud_rate": int(raw.get("baud_rate") or raw.get("baud") or 9600),
            "lenguaje": str(raw.get("lenguaje") or raw.get("language") or "ZPL"),
        }

    @staticmethod
    def _safe_baud(raw_value: Any, default: int = 9600) -> int:
        try:
            baud = int(raw_value)
            if 1200 <= baud <= 115200:
                return baud
        except Exception as exc:
            logger.warning("Baud rate de impresora inválido (%r); usando default %s: %s", raw_value, default, exc)
        return default

    @staticmethod
    def _resolve_transport(cfg: Dict[str, Any]) -> TransportType:
        raw = str(cfg.get("transport") or cfg.get("tipo") or cfg.get("metodo") or "auto").strip().lower()
        mapping = {
            "auto": TransportType.AUTO,
            "network": TransportType.NETWORK,
            "tcp": TransportType.NETWORK,
            "serial": TransportType.SERIAL,
            "escpos_serial": TransportType.SERIAL,
            "file": TransportType.FILE,
            "usb_win32": TransportType.USB_WIN32,
            "win32": TransportType.USB_WIN32,
            "win32print": TransportType.USB_WIN32,
            "system": TransportType.SYSTEM,
            "escpos_usb": TransportType.USB_WIN32,
            "escpos": TransportType.AUTO,
        }
        return mapping.get(raw, TransportType.AUTO)

    def _get_cfg(self, key: str, default: str = "") -> str:
        if not self.db:
            return default
        try:
            r = self.db.execute("SELECT valor FROM configuraciones WHERE clave=?", (key,)).fetchone()
            return r[0] if r and r[0] else default
        except Exception as exc:
            logger.warning("No se pudo leer configuración %s; usando default: %s", key, exc)
            return default

    def _get_branding(self):
        try:
            from core.tickets.branding_service import BrandingService
            return BrandingService(db_conn=self.db).get_ticket_branding()
        except Exception as exc:
            logger.warning("No se pudo cargar branding de ticket: %s", exc)
            return None

    def _get_layout(self, layout_type: str = "sale_ticket"):
        try:
            from core.tickets.ticket_layout_repository import TicketLayoutRepository
            return TicketLayoutRepository(db_conn=self.db).load(layout_type=layout_type)
        except Exception as exc:
            logger.warning("No se pudo cargar Ticket Design activo; se usará layout default: %s", exc)
            try:
                from core.tickets.ticket_layout_config import TicketLayoutConfig
                return TicketLayoutConfig.for_layout_type(layout_type)
            except Exception:
                return None

    def _row_value(self, row, *keys, default=""):
        if not row:
            return default
        for key in keys:
            try:
                if isinstance(row, dict) and key in row and row[key] not in (None, ""):
                    return row[key]
                value = row[key]
                if value not in (None, ""):
                    return value
            except Exception:
                continue
        return default

    def _table_columns(self, table: str) -> set[str]:
        if not self.db:
            return set()
        try:
            return {str(r[1]) for r in self.db.execute(f"PRAGMA table_info({table})").fetchall()}
        except Exception:
            return set()

    @staticmethod
    def _normalize_ticket_unit(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _is_generic_ticket_unit(value: Any) -> bool:
        normalized = PrinterService._normalize_ticket_unit(value).lower().rstrip(". ")
        generic_units = {"", "pz", "pza", "pzas", "pieza", "piezas", "unidad", "unidades"}
        return normalized in generic_units

    def _ticket_item_product_id(self, item: Dict[str, Any]) -> int:
        for key in ("product_id", "producto_id", "id_producto"):
            raw = item.get(key)
            if raw not in (None, ""):
                try:
                    return int(raw)
                except Exception:
                    return 0
        # En payloads de UI antiguos ``id`` es el producto; en payloads de
        # detalle de venta suele ser el id de línea y viene acompañado de
        # venta_id/sale_id. No debe usarse como producto en ese caso.
        if any(item.get(key) not in (None, "") for key in ("venta_id", "sale_id", "detalle_id", "line_id")):
            return 0
        raw = item.get("id")
        if raw not in (None, ""):
            try:
                return int(raw)
            except Exception:
                return 0
        return 0

    def _ticket_product_select_columns(self, product_columns: set[str]) -> list[str]:
        select_cols = ["id"]
        for col in ("nombre", "descripcion", "producto", "unidad", "codigo_barras", "codigo"):
            if col in product_columns and col not in select_cols:
                select_cols.append(col)
        return select_cols

    def _fetch_ticket_product_row(self, item: Dict[str, Any], product_columns: set[str]):
        if not (self.db and product_columns):
            return None, 0
        select_cols = self._ticket_product_select_columns(product_columns)
        pid = self._ticket_item_product_id(item)
        if pid:
            try:
                row = self.db.execute(
                    f"SELECT {', '.join(select_cols)} FROM productos WHERE id=? LIMIT 1",
                    (pid,),
                ).fetchone()
                if row:
                    return row, pid
            except Exception as exc:
                logger.debug("No se pudo hidratar producto para ticket pid=%s: %s", pid, exc)
        for item_key, product_col in (("codigo_barras", "codigo_barras"), ("barcode", "codigo_barras"), ("codigo", "codigo")):
            code = str(item.get(item_key) or "").strip()
            if not code or product_col not in product_columns:
                continue
            try:
                row = self.db.execute(
                    f"SELECT {', '.join(select_cols)} FROM productos WHERE {product_col}=? LIMIT 1",
                    (code,),
                ).fetchone()
                if row:
                    try:
                        return row, int(self._row_value(row, "id", default=pid) or 0)
                    except Exception:
                        return row, pid
            except Exception as exc:
                logger.debug("No se pudo hidratar producto para ticket %s=%s: %s", product_col, code, exc)
        return None, pid

    def _hydrate_ticket_items(self, items: list) -> list:
        hydrated = []
        product_columns = self._table_columns("productos")
        can_read_unidad = "unidad" in product_columns
        for item in list(items or []):
            it = dict(item or {})
            row, pid = self._fetch_ticket_product_row(it, product_columns)
            nombre = (
                it.get("nombre") or it.get("name") or it.get("product_name") or
                self._row_value(row, "nombre", "descripcion", "producto", default="") or
                (f"Producto {pid}" if pid else "Producto")
            )
            payload_unidad = self._normalize_ticket_unit(
                it.get("unidad") or it.get("unit") or it.get("unidad_medida") or it.get("uom") or ""
            )
            db_unidad = str(self._row_value(row, "unidad", default="") or "").strip() if can_read_unidad else ""
            if db_unidad and self._is_generic_ticket_unit(payload_unidad):
                unidad = db_unidad
            else:
                unidad = payload_unidad or db_unidad or "pz"
            cantidad = it.get("cantidad", it.get("qty", it.get("quantity", 0)))
            precio = it.get("precio_unitario", it.get("unit_price", 0))
            total = it.get("total", it.get("subtotal", None))
            if total in (None, ""):
                try:
                    total = float(cantidad or 0) * float(precio or 0)
                except Exception:
                    total = 0
            try:
                normalized_pid = int(pid or 0)
            except Exception:
                normalized_pid = 0
            it.update({
                "product_id": normalized_pid,
                "producto_id": normalized_pid,
                "nombre": str(nombre),
                "name": str(nombre),
                "unidad": str(unidad),
                "unit": str(unidad),
                "db_unidad": db_unidad,
                "unidad_db": db_unidad,
                "unidad_producto": db_unidad,
                "cantidad": float(cantidad or 0),
                "qty": float(cantidad or 0),
                "precio_unitario": float(precio or 0),
                "unit_price": float(precio or 0),
                "total": round(float(total or 0), 2),
                "subtotal": round(float(total or 0), 2),
            })
            hydrated.append(it)
        return hydrated

    def _hydrate_ticket_customer(self, data: Dict[str, Any]) -> None:
        if data.get("cliente") or data.get("cliente_nombre"):
            return
        client_id = data.get("cliente_id") or (data.get("loyalty") or {}).get("cliente_id")
        if not (self.db and client_id):
            data.setdefault("cliente", "Público General")
            data.setdefault("cliente_nombre", data["cliente"])
            return
        try:
            row = self.db.execute("SELECT * FROM clientes WHERE id=? LIMIT 1", (int(client_id),)).fetchone()
            nombre = self._row_value(row, "nombre", "name", "razon_social", "cliente", default="")
            if not nombre:
                nombre = f"Cliente {client_id}"
            data["cliente"] = str(nombre)
            data["cliente_nombre"] = str(nombre)
        except Exception as exc:
            logger.debug("No se pudo hidratar cliente para ticket cliente_id=%s: %s", client_id, exc)
            data.setdefault("cliente", f"Cliente {client_id}")
            data.setdefault("cliente_nombre", data["cliente"])

    def _prepare_ticket_data(self, ticket_data: Dict[str, Any]) -> tuple[Dict[str, Any], Any, Any]:
        data = dict(ticket_data or {})
        data["items"] = self._hydrate_ticket_items(data.get("items") or [])
        self._hydrate_ticket_customer(data)
        branding = self._get_branding()
        if branding:
            data.setdefault("empresa", branding.brand_name)
            data.setdefault("direccion", branding.address)
            data.setdefault("telefono", branding.phone)
        else:
            data.setdefault("empresa", self._get_cfg("nombre_empresa", "SPJ POS"))
            data.setdefault("direccion", self._get_cfg("direccion", ""))
            data.setdefault("telefono", self._get_cfg("telefono_empresa", ""))
        layout = self._get_layout("sale_ticket")
        if layout is not None:
            data["layout_config"] = layout.to_dict()
            debug_logo = self._get_cfg("ticket_debug_logo", "")
            if str(debug_logo).strip() == "1":
                data["layout_config"]["ticket_debug_logo"] = True
        return data, branding, layout

    def print_ticket(self, ticket_data: Dict[str, Any], on_success: Callable = None, on_error: Callable = None) -> str:
        if not self.enabled:
            logger.debug("Impresión deshabilitada (toggle printing)")
            return ""
        vr = self.validate_ticket_printer_config()
        if not vr.ok:
            msg = "; ".join(vr.errors or ["Configuración inválida de impresora"])
            logger.warning("print_ticket bloqueado por config inválida: %s", msg)
            if on_error:
                try:
                    on_error(Exception(msg))
                except Exception:
                    logger.exception("print_ticket on_error callback failed (config inválida)")
            return ""
        try:
            from core.ticket_escpos_renderer import TicketESCPOSRenderer
            prepared, branding, layout = self._prepare_ticket_data(ticket_data)
            paper_w = int(getattr(layout, "paper_width_mm", 0) or self._ticket_cfg.get("paper_width", 80))
            renderer = TicketESCPOSRenderer(paper_width_mm=paper_w, encoding=str(self._ticket_cfg.get("encoding", "cp850")))
            if self._ticket_cfg.get("escpos_mode") == "text_diagnostic":
                data = renderer.render_safe_text(prepared)
            else:
                logo_b64 = ""
                if branding and self._ticket_cfg.get("print_logo", True) and getattr(layout, "show_logo", True):
                    logo_b64 = branding.logo_b64 or ""
                qr_content = ""
                if self._ticket_cfg.get("print_qr", True) and getattr(layout, "show_qr", True):
                    qr_content = self._get_cfg("ticket_qr_url", "") or prepared.get("qr_content") or prepared.get("folio", "")
                data = renderer.render(prepared, logo_b64=logo_b64, qr_content=qr_content)
        except Exception as exc:
            logger.error("Error formateando ticket: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception:
                    logger.exception("print_ticket on_error callback failed (renderer)")
            return ""
        job = PrintJob(
            job_type=PrintJobType.TICKET,
            data=data,
            raw_data=prepared,
            destination=self._ticket_cfg.get("ubicacion", ""),
            transport=self._resolve_transport(self._ticket_cfg),
            baud=self._safe_baud(self._ticket_cfg.get("baud_rate", 9600)),
            priority=2,
            on_success=on_success,
            on_error=on_error,
        )
        self.queue.submit(job)
        return job.id

    def print_raffle_ticket(self, raffle_ticket_data: Dict[str, Any], on_success: Callable = None, on_error: Callable = None) -> str:
        if not self.enabled:
            logger.debug("Impresión de boleto de sorteo deshabilitada (toggle printing)")
            return ""
        vr = self.validate_ticket_printer_config()
        if not vr.ok:
            msg = "; ".join(vr.errors or ["Configuración inválida de impresora"])
            logger.warning("print_raffle_ticket bloqueado por config inválida: %s", msg)
            if on_error:
                try:
                    on_error(Exception(msg))
                except Exception:
                    logger.exception("print_raffle_ticket on_error callback failed")
            return ""
        try:
            from core.tickets.raffle_ticket_renderer import RaffleTicketESCPOSRenderer
            prepared = dict(raffle_ticket_data or {})
            prepared["ticket_type"] = "raffle_ticket"
            branding = self._get_branding()
            if branding:
                prepared.setdefault("empresa", branding.brand_name)
                prepared.setdefault("direccion", branding.address)
                prepared.setdefault("telefono", branding.phone)
            else:
                prepared.setdefault("empresa", self._get_cfg("nombre_empresa", "SPJ POS"))
                prepared.setdefault("direccion", self._get_cfg("direccion", ""))
                prepared.setdefault("telefono", self._get_cfg("telefono_empresa", ""))
            layout = self._get_layout("raffle_ticket")
            prepared["layout_config"] = layout.to_dict() if layout else prepared.get("layout_config", {})
            debug_logo = self._get_cfg("ticket_debug_logo", "")
            if str(debug_logo).strip() == "1":
                prepared["layout_config"]["ticket_debug_logo"] = True
            paper_w = int(getattr(layout, "paper_width_mm", 0) or self._ticket_cfg.get("paper_width", 80))
            renderer = RaffleTicketESCPOSRenderer(paper_width_mm=paper_w, encoding=str(self._ticket_cfg.get("encoding", "cp850")))
            logo_b64 = ""
            if branding and self._ticket_cfg.get("print_logo", True) and getattr(layout, "show_logo", True):
                logo_b64 = branding.logo_b64 or ""
            qr_content = prepared.get("qr_content") or prepared.get("numero_boleto") or prepared.get("barcode") or ""
            prepared.setdefault("qr_content", str(qr_content or ""))
            prepared.setdefault("barcode", str(prepared.get("numero_boleto") or qr_content or ""))
            data = renderer.render(prepared, logo_b64=logo_b64, qr_content=str(qr_content or ""))
        except Exception as exc:
            logger.error("Error formateando boleto de sorteo: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception:
                    logger.exception("print_raffle_ticket on_error callback failed (renderer)")
            return ""
        job = PrintJob(
            job_type=PrintJobType.RAFFLE_TICKET,
            data=data,
            raw_data=prepared,
            destination=self._ticket_cfg.get("ubicacion", ""),
            transport=self._resolve_transport(self._ticket_cfg),
            baud=self._safe_baud(self._ticket_cfg.get("baud_rate", 9600)),
            priority=3,
            on_success=on_success,
            on_error=on_error,
        )
        self.queue.submit(job)
        return job.id

    def print_label(self, label_data: bytes, printer_cfg: Dict = None, on_success: Callable = None, on_error: Callable = None) -> str:
        if not self.enabled:
            return ""
        cfg = printer_cfg or self._label_cfg
        job = PrintJob(
            job_type=PrintJobType.LABEL,
            data=label_data,
            raw_data={},
            transport=self._resolve_transport(cfg),
            destination=cfg.get("ubicacion", ""),
            baud=self._safe_baud(cfg.get("baud_rate", 9600)),
            priority=5,
            retries=2,
            on_success=on_success,
            on_error=on_error,
        )
        self.queue.submit(job)
        return job.id

    def print_raw(self, data: bytes, destination: str = "", priority: int = 5) -> str:
        if not self.enabled:
            return ""
        dest = destination or self._ticket_cfg.get("ubicacion", "")
        job = PrintJob(
            job_type=PrintJobType.RAW,
            data=data,
            raw_data={},
            transport=self._resolve_transport(self._ticket_cfg),
            destination=dest,
            baud=self._safe_baud(self._ticket_cfg.get("baud_rate", 9600)),
            priority=priority,
        )
        self.queue.submit(job)
        return job.id

    def has_ticket_printer(self) -> bool:
        return self.validate_ticket_printer_config().ok

    def has_label_printer(self) -> bool:
        return bool(self._label_cfg.get("ubicacion", ""))

    def validate_ticket_printer_config(self) -> ValidationResult:
        cfg = self._ticket_cfg or {}
        transport = self._resolve_transport(cfg)
        destination = str(cfg.get("ubicacion", "") or "").strip()
        errors: List[str] = []
        warnings: List[str] = []
        if not destination:
            errors.append("No hay impresora de tickets configurada en hardware_config.")
        if transport == TransportType.SYSTEM:
            errors.append("TransportType.SYSTEM no es válido para ticket térmico ESC/POS.")
        if transport == TransportType.NETWORK and ":" not in destination:
            errors.append("Destino TCP inválido, use formato ip:puerto.")
        if transport == TransportType.SERIAL:
            if not (destination.upper().startswith("COM") or "/dev/tty" in destination):
                errors.append("Destino serial inválido.")
        if transport == TransportType.USB_WIN32 and not destination:
            errors.append("Nombre de impresora Win32 vacío.")
        if not errors and not PrintTransport.is_available(transport, destination):
            errors.append(f"Impresora no disponible ({transport.value} -> {destination or '<default>'}).")
        if cfg.get("escpos_mode") == "text_diagnostic":
            warnings.append("Modo texto diagnóstico activo: no se imprimen logo, QR ni diseño ESC/POS completo.")
        enc = str(cfg.get("encoding", "cp850") or "cp850").lower()
        if enc not in {"cp850", "latin-1", "utf-8"}:
            warnings.append(f"Encoding no estándar para térmica: {enc}")
        return ValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings, transport=transport.value, destination=destination)

    def print_test_ticket(self) -> str:
        payload = {
            "ticket_type": "test_ticket",
            "folio": "TEST-TICKET",
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cajero": "Sistema",
            "cliente": "Prueba",
            "items": [{"nombre": "Prueba impresora", "cantidad": 1, "unidad": "pz", "precio_unitario": 0, "total": 0}],
            "totales": {"subtotal": 0, "descuento": 0, "total_final": 0},
            "pago": {"forma_pago": "N/A"},
            "mensaje_psicologico": "Impresión de prueba",
        }
        return self.print_ticket(payload)

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "queue_pending": self.queue.pending,
            "total_printed": self.queue.total_printed,
            "total_failed": self.queue.total_failed,
            "ticket_printer": self._ticket_cfg.get("ubicacion", "N/A"),
            "ticket_mode": self._ticket_cfg.get("escpos_mode", "raw"),
            "ticket_model": self._ticket_cfg.get("printer_model", ""),
            "label_printer": self._label_cfg.get("ubicacion", "N/A"),
        }

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        logger.info("PrinterService %s", "activado" if enabled else "desactivado")

    def close(self) -> None:
        self.queue.stop()


def save_ticket_pdf(html: str, filepath: str) -> str:
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html or "")
    return filepath
