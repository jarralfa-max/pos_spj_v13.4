# state/reminder_engine.py — SPJ POS v13.4 — FASE WA
"""
ReminderEngine — Motor de recordatorios programados.

Usa PedidoPriorityQueue para gestionar y ejecutar recordatorios diferidos:
  - Clientes:   anticipo pendiente, confirmación de pedido, entrega
  - Compras:    seguimiento de OC
  - Staff:      tareas operativas, alertas
  - RRHH:       nómina, descansos, vacaciones

FEATURE FLAG: reminder_engine_enabled (module_toggles en BD)

ARQUITECTURA:
  - Worker thread revisa la cola cada `check_interval` segundos
  - No bloquea el bot (daemon thread)
  - Persistente: estados en wa_reminder_queue (SQLite)
  - Thread-safe: usa threading.Lock en operaciones de BD
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Any

from erp.events import (
    WAEventEmitter,
    PAYMENT_REMINDER, CLIENT_CONFIRMATION_REQUIRED, DELIVERY_REMINDER,
    PURCHASE_FOLLOWUP_REMINDER, STAFF_NOTIFICATION,
    VACATION_REMINDER,
    # RRHH aliases (re-emitted from ERP events)
    ERP_PAYROLL_DUE, ERP_EMPLOYEE_REST_DAY,
)
from state.priority_queue import PedidoPriorityQueue

logger = logging.getLogger("wa.reminders")


@dataclass
class Reminder:
    """Un recordatorio programado."""
    tipo: str                           # payment | delivery | oc_followup | rrhh | staff
    event_type: str                     # Evento a emitir
    data: Dict[str, Any]                # Payload del evento
    phone: str                          # Destinatario principal
    execute_at: datetime                # Cuándo ejecutar
    prioridad: int = 5
    sucursal_id: int = 1
    db_id: Optional[int] = None         # ID en wa_reminder_queue


class ReminderEngine:
    """
    Motor de recordatorios thread-safe.
    Persiste en SQLite y ejecuta handlers asíncronos en un worker thread.
    """

    CHECK_INTERVAL_SEC = 30             # Revisa la cola cada 30 seg

    def __init__(self, db_conn, events: WAEventEmitter,
                 check_interval: int = CHECK_INTERVAL_SEC):
        self.db = db_conn
        self.events = events
        self.check_interval = check_interval
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._queue = PedidoPriorityQueue()

        self._ensure_tables()
        self._load_pending()

    def _ensure_tables(self):
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS wa_reminder_queue (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo        TEXT    NOT NULL,
                    event_type  TEXT    NOT NULL,
                    data_json   TEXT    DEFAULT '{}',
                    phone       TEXT    NOT NULL DEFAULT '',
                    execute_at  TEXT    NOT NULL,
                    prioridad   INTEGER DEFAULT 5,
                    sucursal_id INTEGER DEFAULT 1,
                    estado      TEXT    DEFAULT 'pendiente',  -- pendiente|ejecutado|cancelado
                    created_at  TEXT    DEFAULT (datetime('now'))
                )
            """)
            self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_wa_reminder_execute
                ON wa_reminder_queue(estado, execute_at)
            """)
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("_ensure_tables: %s", e)

    def _load_pending(self):
        """Carga recordatorios pendientes de la BD al arrancar."""
        try:
            import json
            rows = self.db.execute("""
                SELECT id, tipo, event_type, data_json, phone,
                       execute_at, prioridad, sucursal_id
                FROM wa_reminder_queue
                WHERE estado='pendiente' AND execute_at > datetime('now','-1 hour')
            """).fetchall()
            for row in rows:
                try:
                    data = json.loads(row[3]) if row[3] else {}
                    at = datetime.fromisoformat(row[5])
                    reminder = Reminder(
                        tipo=row[1], event_type=row[2], data=data,
                        phone=row[4], execute_at=at,
                        prioridad=row[6], sucursal_id=row[7], db_id=row[0])
                    self._queue.push(
                        pedido_data={"reminder": reminder},
                        phone=row[4],
                        sucursal_id=row[7],
                        prioridad=row[6],
                    )
                except Exception as e:
                    logger.debug("load_pending item: %s", e)
            logger.info("ReminderEngine: %d recordatorios cargados", len(rows))
        except Exception as e:
            logger.debug("_load_pending: %s", e)

    # ── API pública ───────────────────────────────────────────────────────────

    def start(self) -> None:
        """Inicia el worker thread (daemon — no bloquea el bot)."""
        if self._worker and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._run, daemon=True, name="wa_reminders"
        )
        self._worker.start()
        logger.info("ReminderEngine iniciado (worker daemon)")

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker:
            self._worker.join(timeout=5)

    def programar(self, tipo: str, event_type: str, data: Dict,
                   phone: str, delay_segundos: int,
                   prioridad: int = 5,
                   sucursal_id: int = 1) -> Optional[int]:
        """
        Programa un recordatorio.
        Retorna el ID de BD o None si falló.
        """
        import json
        execute_at = datetime.now() + timedelta(seconds=delay_segundos)

        with self._lock:
            try:
                cursor = self.db.execute("""
                    INSERT INTO wa_reminder_queue
                        (tipo, event_type, data_json, phone, execute_at,
                         prioridad, sucursal_id, estado)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pendiente')
                """, (tipo, event_type, json.dumps(data, default=str),
                      phone, execute_at.isoformat(),
                      prioridad, sucursal_id))
                try:
                    self.db.commit()
                except Exception:
                    pass
                db_id = cursor.lastrowid
            except Exception as e:
                logger.warning("programar reminder: %s", e)
                return None

        reminder = Reminder(
            tipo=tipo, event_type=event_type, data=data,
            phone=phone, execute_at=execute_at,
            prioridad=prioridad, sucursal_id=sucursal_id, db_id=db_id)

        self._queue.push(
            pedido_data={"reminder": reminder},
            phone=phone, sucursal_id=sucursal_id, prioridad=prioridad)

        logger.info("Recordatorio programado: %s/%s en %ds (id=%s)",
                    tipo, event_type, delay_segundos, db_id)
        return db_id

    def cancelar(self, db_id: int) -> bool:
        """Cancela un recordatorio por ID."""
        try:
            with self._lock:
                self.db.execute(
                    "UPDATE wa_reminder_queue SET estado='cancelado' WHERE id=?",
                    (db_id,))
                try:
                    self.db.commit()
                except Exception:
                    pass
            return True
        except Exception:
            return False

    # ── Helpers de dominio ────────────────────────────────────────────────────

    def programar_anticipo_pendiente(self, venta_id: int, folio: str,
                                      monto: float, phone: str,
                                      sucursal_id: int = 1,
                                      delay_horas: int = 2) -> Optional[int]:
        """Recuerda al cliente que tiene un anticipo pendiente."""
        return self.programar(
            tipo="payment",
            event_type=PAYMENT_REMINDER,
            data={"venta_id": venta_id, "folio": folio,
                  "monto": monto, "phone": phone},
            phone=phone,
            delay_segundos=delay_horas * 3600,
            prioridad=3, sucursal_id=sucursal_id)

    def programar_confirmacion_pedido(self, venta_id: int, folio: str,
                                       phone: str, sucursal_id: int = 1,
                                       delay_horas: int = 1) -> Optional[int]:
        """Solicita confirmación al cliente."""
        return self.programar(
            tipo="confirmacion",
            event_type=CLIENT_CONFIRMATION_REQUIRED,
            data={"venta_id": venta_id, "folio": folio, "phone": phone},
            phone=phone,
            delay_segundos=delay_horas * 3600,
            prioridad=4, sucursal_id=sucursal_id)

    def programar_recordatorio_entrega(self, venta_id: int, folio: str,
                                        fecha_entrega: str, phone: str,
                                        sucursal_id: int = 1,
                                        horas_antes: int = 24) -> Optional[int]:
        """Recuerda la entrega con N horas de anticipación."""
        try:
            from datetime import datetime as _dt
            entrega = _dt.fromisoformat(fecha_entrega)
            delay = max(60, int((entrega - _dt.now()).total_seconds())
                        - horas_antes * 3600)
        except Exception:
            delay = max(60, horas_antes * 3600)

        return self.programar(
            tipo="delivery",
            event_type=DELIVERY_REMINDER,
            data={"venta_id": venta_id, "folio": folio,
                  "fecha": fecha_entrega, "phone": phone},
            phone=phone, delay_segundos=delay,
            prioridad=4, sucursal_id=sucursal_id)

    def programar_seguimiento_oc(self, oc_id: int, producto: str,
                                   phone_compras: str,
                                   sucursal_id: int = 1,
                                   delay_horas: int = 24) -> Optional[int]:
        """Recuerda al personal de compras hacer seguimiento de OC."""
        return self.programar(
            tipo="oc_followup",
            event_type=PURCHASE_FOLLOWUP_REMINDER,
            data={"oc_id": oc_id, "producto": producto, "phone": phone_compras},
            phone=phone_compras,
            delay_segundos=delay_horas * 3600,
            prioridad=5, sucursal_id=sucursal_id)

    def programar_notificacion_rrhh(self, event_type: str, data: Dict,
                                     phone: str, sucursal_id: int = 1,
                                     delay_horas: int = 0) -> Optional[int]:
        """Programa notificación RRHH (descanso, nómina, vacaciones)."""
        return self.programar(
            tipo="rrhh",
            event_type=event_type,
            data=data, phone=phone,
            delay_segundos=max(1, delay_horas * 3600),
            prioridad=5, sucursal_id=sucursal_id)

    # ── Worker ────────────────────────────────────────────────────────────────

    def _run(self) -> None:
        """Loop principal del worker."""
        logger.info("ReminderEngine worker iniciado")
        while not self._stop_event.is_set():
            try:
                self._process_due()
            except Exception as e:
                logger.error("ReminderEngine._run error: %s", e)
            self._stop_event.wait(self.check_interval)
        logger.info("ReminderEngine worker detenido")

    def _process_due(self) -> None:
        """Procesa todos los recordatorios cuyo execute_at ya pasó."""
        now = datetime.now()
        try:
            with self._lock:
                rows = self.db.execute("""
                    SELECT id, tipo, event_type, data_json, phone,
                           execute_at, prioridad, sucursal_id
                    FROM wa_reminder_queue
                    WHERE estado='pendiente' AND execute_at <= datetime('now')
                    ORDER BY prioridad ASC, execute_at ASC
                    LIMIT 20
                """).fetchall()
        except Exception as e:
            logger.debug("_process_due query: %s", e)
            return

        import json
        for row in rows:
            db_id, tipo, event_type, data_json, phone, _, prioridad, suc_id = row
            try:
                data = json.loads(data_json) if data_json else {}
                data["phone"] = phone

                # Emitir el evento al EventBus del ERP
                self.events.emit(event_type, data,
                                 sucursal_id=suc_id, prioridad=prioridad)

                with self._lock:
                    self.db.execute(
                        "UPDATE wa_reminder_queue SET estado='ejecutado' WHERE id=?",
                        (db_id,))
                    try:
                        self.db.commit()
                    except Exception:
                        pass

                logger.info("Recordatorio ejecutado: %s/%s id=%d",
                            tipo, event_type, db_id)
            except Exception as e:
                logger.error("Ejecutar reminder id=%d: %s", db_id, e)
