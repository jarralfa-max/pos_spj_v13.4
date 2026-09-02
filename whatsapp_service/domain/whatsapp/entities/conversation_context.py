# domain/whatsapp/entities/conversation_context.py — WA-2 (prompt maestro §31)
"""ConversationContext — contexto conversacional versionado y tipado.

§14 y §31 del prompt maestro son explícitos: el contexto debe ser
versionado y validado, y NO debe almacenar objetos Python serializados
arbitrariamente, ni copias maestras de productos/precios/stock/crédito/
puntos (eso se consulta en el momento, no se cachea aquí). Por eso este
módulo es una dataclass con campos explícitos — no un dict libre.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ConversationContext:
    """Referencias vivas de una conversación — nunca copias de datos ERP."""

    version: int = 1
    customer_id: Optional[str] = None
    branch_id: Optional[str] = None
    active_order_draft_id: Optional[str] = None
    active_quote_id: Optional[str] = None
    delivery_address_id: Optional[str] = None
    expected_intent: Optional[str] = None
    expected_entity: Optional[str] = None
    last_confirmed_action: Optional[str] = None

    def with_update(self, **changes) -> "ConversationContext":
        """Devuelve un nuevo contexto con `changes` aplicados y versión +1.

        Inmutable por diseño (igual criterio que los value objects) — el
        llamador siempre reemplaza el contexto de la conversación por el
        valor devuelto, nunca muta el existente in-place.
        """
        allowed = set(self.__dataclass_fields__.keys()) - {"version"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Campos de contexto desconocidos: {sorted(unknown)}")
        data = {f: getattr(self, f) for f in allowed}
        data.update(changes)
        return ConversationContext(version=self.version + 1, **data)

    def clear_active_flow(self) -> "ConversationContext":
        """Limpia referencias de flujo activo (orden/cotización/expectativa)
        sin perder `customer_id`/`branch_id`/`delivery_address_id` — usado al
        cancelar o completar un flujo conversacional."""
        return self.with_update(
            active_order_draft_id=None,
            active_quote_id=None,
            expected_intent=None,
            expected_entity=None,
        )
