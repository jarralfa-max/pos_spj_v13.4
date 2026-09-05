# core/repositories/whatsapp_history_repository.py
"""Historial unificado de mensajes WhatsApp. Abstrae múltiples tablas legacy."""
from __future__ import annotations
import logging
from typing import List, Dict, Optional

logger = logging.getLogger("spj.repo.wa_history")


class WhatsAppHistoryRepository:
    """
    Fuente canónica (WA-19): bounded context nuevo (`whatsapp_messages`,
    WA-2/WA-3) → wa_message_queue (tabla fantasma, nunca creada por
    ninguna migración — ver `docs/refactor/whatsapp_schema_consolidation.md`,
    esta consulta siempre falla y cae al siguiente fallback, comportamiento
    preexistente, no tocado) → bot_mensajes_log → pedidos_whatsapp.
    Usa LIKE con parámetros (sin interpolación directa) para evitar SQL injection.
    """

    def __init__(self, conn):
        self.conn = conn

    def get_history(self, search: str = "", limit: int = 200) -> List[Dict]:
        pattern = f"%{search}%" if search else None
        for query_fn in (self._query_new_bounded_context, self._query_wa_queue,
                         self._query_bot_log, self._query_pedidos_wa):
            try:
                rows = query_fn(pattern, limit)
                if rows:
                    return rows
            except Exception as e:
                logger.debug("history query failed: %s", e)
        return []

    def _query_new_bounded_context(self, pattern: Optional[str], limit: int) -> List[Dict]:
        """WA-19 — el canal nuevo (WA-1..18) todavía no está wireado al
        webhook en vivo (ver memoria del proyecto), así que hoy esta
        consulta típicamente devuelve vacío y cae al siguiente fallback —
        sin cambio de comportamiento observable hasta el día del cutover,
        momento en el que esta pasa a ser la fuente real automáticamente.

        `whatsapp_messages` (WA-2) no persiste el texto/interactive_id
        crudo del mensaje (gap documentado desde WA-8) — `mensaje` refleja
        eso honestamente en vez de fingir contenido que no existe.
        """
        where = "WHERE i.normalized_phone LIKE ?" if pattern else ""
        params = (pattern, limit) if pattern else (limit,)
        rows = self.conn.execute(
            f"""
            SELECT m.created_at, i.normalized_phone, m.direction, m.message_type,
                   d.status
            FROM whatsapp_messages m
            JOIN whatsapp_conversations c ON c.id = m.conversation_id
            JOIN whatsapp_identities i ON i.id = c.identity_id
            LEFT JOIN whatsapp_message_deliveries d ON d.message_id = m.id
            {where}
            ORDER BY m.created_at DESC LIMIT ?
            """,
            params,
        ).fetchall()
        result = []
        for fecha, numero, direction, message_type, delivery_status in rows:
            direccion = "⬇️ Entrada" if direction == "INBOUND" else "⬆️ Salida"
            estado = delivery_status or ("recibido" if direction == "INBOUND" else "en cola")
            result.append({
                "fecha": fecha, "numero": numero, "direccion": direccion,
                "mensaje": f"[{message_type}] (sin texto persistido)",
                "estado": estado,
            })
        return result

    def _query_wa_queue(self, pattern: Optional[str], limit: int) -> List[Dict]:
        if pattern:
            rows = self.conn.execute(
                "SELECT fecha_creacion, to_number, "
                "CASE WHEN status='sent' THEN '⬆️ Salida' ELSE '⏳ Cola' END, "
                "COALESCE(message,''), COALESCE(status,'pendiente') "
                "FROM wa_message_queue "
                "WHERE to_number LIKE ? OR message LIKE ? "
                "ORDER BY fecha_creacion DESC LIMIT ?",
                (pattern, pattern, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT fecha_creacion, to_number, "
                "CASE WHEN status='sent' THEN '⬆️ Salida' ELSE '⏳ Cola' END, "
                "COALESCE(message,''), COALESCE(status,'pendiente') "
                "FROM wa_message_queue ORDER BY fecha_creacion DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [{"fecha": r[0], "numero": r[1], "direccion": r[2],
                 "mensaje": r[3], "estado": r[4]} for r in rows]

    def _query_bot_log(self, pattern: Optional[str], limit: int) -> List[Dict]:
        if pattern:
            rows = self.conn.execute(
                "SELECT fecha, numero_whatsapp, "
                "CASE WHEN direction='in' THEN '⬇️ Entrada' ELSE '⬆️ Salida' END, "
                "COALESCE(mensaje,texto,''), COALESCE(estado,'enviado') "
                "FROM bot_mensajes_log "
                "WHERE numero_whatsapp LIKE ? OR mensaje LIKE ? OR texto LIKE ? "
                "ORDER BY fecha DESC LIMIT ?",
                (pattern, pattern, pattern, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT fecha, numero_whatsapp, "
                "CASE WHEN direction='in' THEN '⬇️ Entrada' ELSE '⬆️ Salida' END, "
                "COALESCE(mensaje,texto,''), COALESCE(estado,'enviado') "
                "FROM bot_mensajes_log ORDER BY fecha DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [{"fecha": r[0], "numero": r[1], "direccion": r[2],
                 "mensaje": r[3], "estado": r[4]} for r in rows]

    def _query_pedidos_wa(self, pattern: Optional[str], limit: int) -> List[Dict]:
        if pattern:
            rows = self.conn.execute(
                "SELECT fecha, COALESCE(numero_whatsapp,telefono_cliente,'?'), "
                "'⬇️ Entrada', COALESCE(mensaje,''), 'recibido' "
                "FROM pedidos_whatsapp "
                "WHERE numero_whatsapp LIKE ? OR telefono_cliente LIKE ? "
                "ORDER BY fecha DESC LIMIT ?",
                (pattern, pattern, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT fecha, COALESCE(numero_whatsapp,telefono_cliente,'?'), "
                "'⬇️ Entrada', COALESCE(mensaje,''), 'recibido' "
                "FROM pedidos_whatsapp ORDER BY fecha DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [{"fecha": r[0], "numero": r[1], "direccion": r[2],
                 "mensaje": r[3], "estado": r[4]} for r in rows]
