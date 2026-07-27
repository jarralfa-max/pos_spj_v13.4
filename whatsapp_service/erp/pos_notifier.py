# erp/pos_notifier.py — Puente persistente WA → ERP/POS
"""
Notificador persistente para que el ERP desktop se entere de pedidos creados
por el microservicio WhatsApp.

Por qué existe:
- El microservicio y el ERP desktop corren en procesos distintos.
- Publicar en el EventBus desde el microservicio NO despierta el EventBus en
  memoria del ERP desktop.
- La integración confiable debe dejar huellas persistentes en la BD:
  1) wa_event_log para trazabilidad/eventos.
  2) notification_inbox para campana/inbox del ERP.

Este módulo no envía WhatsApp al staff. Las alertas de nuevo pedido deben verse
en el ERP, tal como se definió en el flujo de negocio.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, Iterable, List

logger = logging.getLogger("wa.pos_notifier")

PEDIDO_WA_TIPO = "pedido_whatsapp_nuevo"
EVENT_WHATSAPP_ORDER_CREATED = "WHATSAPP_ORDER_CREATED"
EVENT_WHATSAPP_SCHEDULED_ORDER_CREATED = "WHATSAPP_SCHEDULED_ORDER_CREATED"
EVENT_BRANCH_NOTIFICATION_CREATED = "BRANCH_NOTIFICATION_CREATED"


class POSNotifier:
    """Crea eventos/notificaciones persistentes para el ERP desktop."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self.db.row_factory = sqlite3.Row

    # ── API pública ──────────────────────────────────────────────────────────

    def notify_new_whatsapp_order(
        self,
        *,
        venta_id: int,
        folio: str,
        cliente_id: int,
        cliente_nombre: str,
        total: float,
        sucursal_id: int,
        tipo_entrega: str,
        direccion: str = "",
        items: List[Dict[str, Any]] | None = None,
    ) -> None:
        """Registra evento + notificación POS de nuevo pedido WhatsApp."""
        delivery_type = "home_delivery" if (tipo_entrega or "").strip().lower() in ("domicilio", "home_delivery") else "pickup"
        workflow_type = "delivery" if delivery_type == "home_delivery" else "counter"
        payload = {
            "event_type": "WA_PEDIDO_CREADO",
            "venta_id": venta_id,
            "folio": folio,
            "cliente_id": cliente_id,
            "cliente": cliente_nombre or "Cliente WhatsApp",
            "total": float(total or 0),
            "sucursal_id": sucursal_id,
            "tipo_entrega": tipo_entrega or "sucursal",
            "direccion": direccion or "",
            "items": items or [],
            "canal": "whatsapp",
            "timestamp": datetime.now().isoformat(),
            # canonical internal aliases
            "sale_id": venta_id,
            "branch_id": sucursal_id,
            "customer_id": cliente_id,
            "customer_name": cliente_nombre or "Cliente WhatsApp",
            "delivery_type": delivery_type,
            "workflow_type": workflow_type,
            "source_channel": "whatsapp",
        }

        self._insert_wa_event(EVENT_WHATSAPP_ORDER_CREATED, payload, sucursal_id=sucursal_id, prioridad=90)
        self._insert_wa_event("WA_PEDIDO_CREADO", payload, sucursal_id=sucursal_id, prioridad=90)
        self._insert_wa_event("SALE_CREATED", payload, sucursal_id=sucursal_id, prioridad=90)
        dedupe_key = f"new_order:{venta_id}"

        self._insert_wa_event(EVENT_BRANCH_NOTIFICATION_CREATED, payload, sucursal_id=sucursal_id, prioridad=80)

        self._insert_inbox_for_roles(
            roles=("admin", "gerente", "cajero"),
            tipo=PEDIDO_WA_TIPO,
            titulo=f"📲 Nuevo pedido WhatsApp {folio}",
            cuerpo=(
                f"Cliente: {payload['cliente']}\n"
                f"Total: ${float(total or 0):.2f}\n"
                f"Entrega: {payload['tipo_entrega']}\n"
                "Atiéndelo desde Ventas/Delivery."
            ),
            datos=payload,
            sucursal_id=sucursal_id,
            severity="info",
            dedupe_key=dedupe_key,
        )

    def notify_scheduled_whatsapp_order(
        self,
        *,
        venta_id: int,
        folio: str,
        cliente_id: int,
        cliente_nombre: str,
        total: float,
        sucursal_id: int,
        tipo_entrega: str,
        scheduled_at: str,
        direccion: str = "",
        items: List[Dict[str, Any]] | None = None,
    ) -> None:
        delivery_type = "home_delivery" if (tipo_entrega or "").strip().lower() in ("domicilio", "home_delivery") else "pickup"
        payload = {
            "event_type": EVENT_WHATSAPP_SCHEDULED_ORDER_CREATED,
            "venta_id": venta_id,
            "folio": folio,
            "cliente_id": cliente_id,
            "cliente": cliente_nombre or "Cliente WhatsApp",
            "total": float(total or 0),
            "sucursal_id": sucursal_id,
            "tipo_entrega": tipo_entrega or "sucursal",
            "scheduled_at": scheduled_at,
            "direccion": direccion or "",
            "items": items or [],
            "canal": "whatsapp",
            "timestamp": datetime.now().isoformat(),
            # canonical internal aliases
            "sale_id": venta_id,
            "branch_id": sucursal_id,
            "customer_id": cliente_id,
            "customer_name": cliente_nombre or "Cliente WhatsApp",
            "delivery_type": delivery_type,
            "workflow_type": "scheduled",
            "source_channel": "whatsapp",
        }
        self._insert_wa_event(EVENT_WHATSAPP_SCHEDULED_ORDER_CREATED, payload, sucursal_id=sucursal_id, prioridad=90)
        self._insert_wa_event(EVENT_BRANCH_NOTIFICATION_CREATED, payload, sucursal_id=sucursal_id, prioridad=80)
        self._insert_inbox_for_roles(
            roles=("admin", "gerente", "cajero"),
            tipo=PEDIDO_WA_TIPO,
            titulo=f"📅 Pedido programado WhatsApp {folio}",
            cuerpo=(
                f"Cliente: {payload['cliente']}\n"
                f"Programado: {scheduled_at}\n"
                f"Total: ${float(total or 0):.2f}\n"
                "Revisa Programados para activación."
            ),
            datos=payload,
            sucursal_id=sucursal_id,
            severity="warning",
            dedupe_key=f"scheduled_order:{venta_id}",
        )

    # ── Inserción de eventos ─────────────────────────────────────────────────

    def _insert_wa_event(self, event_type: str, payload: Dict[str, Any], *, sucursal_id: int, prioridad: int) -> None:
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS wa_event_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    data_json TEXT,
                    sucursal_id INTEGER DEFAULT 1,
                    prioridad INTEGER DEFAULT 5,
                    timestamp TEXT DEFAULT (datetime('now'))
                )
            """)
            self.db.execute("""
                INSERT INTO wa_event_log (event_type, data_json, sucursal_id, prioridad, timestamp)
                VALUES (?, ?, ?, ?, datetime('now'))
            """, (
                event_type,
                json.dumps(payload, ensure_ascii=False, default=str),
                sucursal_id,
                prioridad,
            ))
            self.db.commit()
        except Exception as exc:
            logger.debug("No se pudo insertar wa_event_log %s: %s", event_type, exc)

    # ── Inserción en notification_inbox ───────────────────────────────────────

    def _insert_inbox_for_roles(
        self,
        *,
        roles: Iterable[str],
        tipo: str,
        titulo: str,
        cuerpo: str,
        datos: Dict[str, Any],
        sucursal_id: int,
        severity: str = "info",
        dedupe_key: str | None = None,
    ) -> None:
        empleados = self._get_users_by_roles(list(roles), sucursal_id)
        if not empleados:
            logger.warning("No hay usuarios destino para notificación WA roles=%s sucursal=%s", list(roles), sucursal_id)
            return

        self._ensure_notification_inbox()
        for emp in empleados:
            self._insert_one_inbox(emp, tipo, titulo, cuerpo, datos, sucursal_id, severity=severity, dedupe_key=dedupe_key)

    def _ensure_notification_inbox(self) -> None:
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS notification_inbox (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER,
                    tipo        TEXT    NOT NULL,
                    titulo      TEXT    NOT NULL,
                    cuerpo      TEXT    DEFAULT '',
                    datos       TEXT    DEFAULT '{}',
                    leido       INTEGER DEFAULT 0,
                    sucursal_id INTEGER DEFAULT 1,
                    created_at  TEXT    DEFAULT (datetime('now')),
                    leido_at    TEXT,
                    dedupe_key  TEXT,
                    severity    TEXT DEFAULT 'info'
                )
            """)
            self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_inbox_dedupe_key ON notification_inbox(dedupe_key) WHERE dedupe_key IS NOT NULL")
            self.db.commit()
        except Exception as exc:
            logger.debug("ensure notification_inbox falló: %s", exc)

    def _insert_one_inbox(
        self,
        emp: Dict[str, Any],
        tipo: str,
        titulo: str,
        cuerpo: str,
        datos: Dict[str, Any],
        sucursal_id: int,
        severity: str = "info",
        dedupe_key: str | None = None,
    ) -> None:
        datos_json = json.dumps(datos, ensure_ascii=False, default=str)
        cols = self._table_columns("notification_inbox")
        dedupe_value = f"{dedupe_key}:emp:{emp.get('id') or emp.get('usuario')}" if dedupe_key else None
        if dedupe_value and "dedupe_key" in cols:
            exists = self.db.execute("SELECT 1 FROM notification_inbox WHERE dedupe_key=? LIMIT 1", (dedupe_value,)).fetchone()
            if exists:
                return
        try:
            if "empleado_id" in cols:
                self.db.execute("""
                    INSERT INTO notification_inbox
                        (empleado_id, tipo, titulo, cuerpo, datos, sucursal_id, severity, dedupe_key, leido, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'))
                """, (emp.get("id"), tipo, titulo, cuerpo, datos_json, sucursal_id, severity, dedupe_value))
            elif "usuario" in cols:
                self.db.execute("""
                    INSERT INTO notification_inbox
                        (usuario, tipo, titulo, cuerpo, sucursal_id, severity, dedupe_key, leido, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, datetime('now'))
                """, (emp.get("usuario") or emp.get("nombre") or "admin", tipo, titulo, cuerpo, sucursal_id, severity, dedupe_value))
            else:
                logger.warning("notification_inbox sin empleado_id/usuario; no se insertó notificación")
                return
            self.db.commit()
        except Exception as exc:
            logger.debug("insert inbox WA falló emp=%s: %s", emp, exc)

    # ── Usuarios destino ──────────────────────────────────────────────────────

    def _get_users_by_roles(self, roles: List[str], sucursal_id: int) -> List[Dict[str, Any]]:
        if not roles:
            return []
        roles_l = [r.lower() for r in roles]
        placeholders = ",".join("?" * len(roles_l))

        # RBAC moderno: usuarios_roles + roles.
        try:
            rows = self.db.execute(f"""
                SELECT DISTINCT u.id, u.usuario, u.nombre, LOWER(r.nombre) AS rol
                FROM usuarios u
                JOIN usuarios_roles ur ON ur.usuario_id = u.id
                JOIN roles r ON r.id = ur.rol_id
                WHERE LOWER(r.nombre) IN ({placeholders})
                  AND (ur.sucursal_id = ? OR ur.sucursal_id = 0 OR ur.sucursal_id IS NULL)
                  AND COALESCE(u.activo, 1) = 1
            """, (*roles_l, sucursal_id)).fetchall()
            if rows:
                return [dict(r) for r in rows]
        except Exception:
            pass

        # Legacy: usuarios.rol.
        try:
            rows = self.db.execute(f"""
                SELECT DISTINCT u.id, u.usuario, u.nombre, LOWER(u.rol) AS rol
                FROM usuarios u
                WHERE LOWER(COALESCE(u.rol, '')) IN ({placeholders})
                  AND (u.sucursal_id = ? OR u.sucursal_id IS NULL OR u.sucursal_id = 0)
                  AND COALESCE(u.activo, 1) = 1
            """, (*roles_l, sucursal_id)).fetchall()
            if rows:
                return [dict(r) for r in rows]
        except Exception:
            pass

        # Último recurso: cualquier usuario activo para que el ERP no quede ciego.
        try:
            rows = self.db.execute("""
                SELECT id, usuario, nombre, COALESCE(rol, '') AS rol
                FROM usuarios
                WHERE COALESCE(activo, 1) = 1
                  AND (sucursal_id = ? OR sucursal_id IS NULL OR sucursal_id = 0)
                ORDER BY CASE LOWER(COALESCE(rol,''))
                    WHEN 'admin' THEN 0
                    WHEN 'gerente' THEN 1
                    WHEN 'cajero' THEN 2
                    ELSE 3
                END, id
                LIMIT 5
            """, (sucursal_id,)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _table_columns(self, table: str) -> set[str]:
        try:
            return {r[1] for r in self.db.execute(f"PRAGMA table_info({table})").fetchall()}
        except Exception:
            return set()
