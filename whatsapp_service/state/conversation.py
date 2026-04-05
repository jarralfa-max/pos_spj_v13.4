# state/conversation.py — Persistencia de contexto por teléfono
"""
Guarda y recupera el estado de conversación en SQLite.
Cada teléfono tiene un registro con su contexto serializado.
"""
from __future__ import annotations
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional
from models.context import ConversationContext, FlowState, PedidoItem
from config.settings import CONTEXT_DB_PATH, CONVERSATION_TIMEOUT_MINUTES

logger = logging.getLogger("wa.state")


class ConversationStore:

    def __init__(self, db_path: str = CONTEXT_DB_PATH):
        from pathlib import Path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                phone TEXT PRIMARY KEY,
                state TEXT DEFAULT 'idle',
                sucursal_id INTEGER,
                sucursal_nombre TEXT DEFAULT '',
                cliente_id INTEGER,
                cliente_nombre TEXT DEFAULT '',
                data_json TEXT DEFAULT '{}',
                last_activity TEXT DEFAULT (datetime('now')),
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS message_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE,
                phone TEXT,
                direction TEXT DEFAULT 'in',
                content TEXT,
                timestamp TEXT DEFAULT (datetime('now'))
            );
        """)
        self.db.commit()

    def get(self, phone: str) -> ConversationContext:
        """Recupera o crea el contexto de una conversación."""
        row = self.db.execute(
            "SELECT * FROM conversations WHERE phone=?", (phone,)
        ).fetchone()

        if not row:
            ctx = ConversationContext(phone=phone)
            self._insert(ctx)
            return ctx

        # Verificar timeout
        last = datetime.fromisoformat(row["last_activity"])
        if datetime.now() - last > timedelta(minutes=CONVERSATION_TIMEOUT_MINUTES):
            ctx = ConversationContext(
                phone=phone,
                sucursal_id=row["sucursal_id"],
                sucursal_nombre=row["sucursal_nombre"] or "",
                cliente_id=row["cliente_id"],
                cliente_nombre=row["cliente_nombre"] or "",
            )
            self.save(ctx)
            return ctx

        # Restaurar contexto completo
        ctx = ConversationContext(phone=phone)
        ctx.state = FlowState(row["state"])
        ctx.sucursal_id = row["sucursal_id"]
        ctx.sucursal_nombre = row["sucursal_nombre"] or ""
        ctx.cliente_id = row["cliente_id"]
        ctx.cliente_nombre = row["cliente_nombre"] or ""

        try:
            data = json.loads(row["data_json"] or "{}")
            ctx.pedido_items = [PedidoItem.from_dict(d) for d in data.get("pedido_items", [])]
            ctx.pedido_tipo_entrega = data.get("pedido_tipo_entrega", "")
            ctx.pedido_direccion = data.get("pedido_direccion", "")
            ctx.pedido_fecha_entrega = data.get("pedido_fecha_entrega", "")
            ctx.pedido_programado = data.get("pedido_programado", False)
            ctx.cotizacion_items = [PedidoItem.from_dict(d) for d in data.get("cotizacion_items", [])]
            ctx._producto_temp = data.get("_producto_temp")
            ctx.failed_intents = data.get("failed_intents", 0)
            ctx.numero_tipo = data.get("numero_tipo", "")
        except Exception as e:
            logger.warning("Error parsing context data: %s", e)

        ctx.last_activity = datetime.fromisoformat(row["last_activity"])
        return ctx

    def save(self, ctx: ConversationContext):
        """Guarda el contexto actualizado."""
        data = {
            "pedido_items": [i.to_dict() for i in ctx.pedido_items],
            "pedido_tipo_entrega": ctx.pedido_tipo_entrega,
            "pedido_direccion": ctx.pedido_direccion,
            "pedido_fecha_entrega": ctx.pedido_fecha_entrega,
            "pedido_programado": ctx.pedido_programado,
            "cotizacion_items": [i.to_dict() for i in ctx.cotizacion_items],
            "_producto_temp": ctx._producto_temp,
            "failed_intents": ctx.failed_intents,
            "numero_tipo": ctx.numero_tipo,
        }
        self.db.execute("""
            INSERT INTO conversations (phone, state, sucursal_id, sucursal_nombre,
                         cliente_id, cliente_nombre, data_json, last_activity)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(phone) DO UPDATE SET
                state=excluded.state, sucursal_id=excluded.sucursal_id,
                sucursal_nombre=excluded.sucursal_nombre,
                cliente_id=excluded.cliente_id, cliente_nombre=excluded.cliente_nombre,
                data_json=excluded.data_json, last_activity=excluded.last_activity
        """, (ctx.phone, ctx.state.value, ctx.sucursal_id, ctx.sucursal_nombre,
              ctx.cliente_id, ctx.cliente_nombre, json.dumps(data, default=str)))
        self.db.commit()

    def _insert(self, ctx: ConversationContext):
        self.db.execute(
            "INSERT OR IGNORE INTO conversations (phone) VALUES (?)",
            (ctx.phone,))
        self.db.commit()

    def log_message(self, message_id: str, phone: str,
                    direction: str, content: str) -> bool:
        """Registra un mensaje. Retorna False si ya existe (duplicado)."""
        try:
            self.db.execute(
                "INSERT INTO message_log (message_id, phone, direction, content) "
                "VALUES (?, ?, ?, ?)",
                (message_id, phone, direction, content[:500]))
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Duplicado

    def is_duplicate(self, message_id: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM message_log WHERE message_id=?", (message_id,)
        ).fetchone()
        return row is not None
