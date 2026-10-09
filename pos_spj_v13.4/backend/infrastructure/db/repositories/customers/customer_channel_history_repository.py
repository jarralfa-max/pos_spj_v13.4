"""Historial de avisos de WhatsApp de un cliente (§52, CRM-43) — SÓLO
metadatos: fecha, dirección, tipo, plantilla y estado de entrega. El
contenido de los mensajes es de WhatsApp y no se duplica aquí.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.customers.base import CustomerRepositoryBase


class CustomerChannelHistoryRepository(CustomerRepositoryBase):
    def whatsapp_messages(self, customer_id: str, *, limit: int = 200) -> list[dict]:
        if not self._query("SELECT 1 FROM sqlite_master WHERE type='table'"
                           " AND name='whatsapp_identities'"):
            return []
        return self._query(
            "SELECT m.id, m.created_at, m.direction, m.message_type,"
            " COALESCE(d.status, '') AS status, d.error_code"
            " FROM whatsapp_identities i"
            " JOIN whatsapp_conversations c ON c.identity_id = i.id"
            " JOIN whatsapp_messages m ON m.conversation_id = c.id"
            " LEFT JOIN whatsapp_message_deliveries d ON d.message_id = m.id"
            " WHERE i.customer_id=? ORDER BY m.created_at DESC LIMIT ?",
            (customer_id, limit))
