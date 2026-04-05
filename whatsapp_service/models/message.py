# models/message.py — Modelos de mensaje WhatsApp
"""
Modelos para parsear webhooks entrantes y construir mensajes salientes.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class MessageType(str, Enum):
    TEXT = "text"
    INTERACTIVE = "interactive"       # Botón o lista
    IMAGE = "image"
    DOCUMENT = "document"
    LOCATION = "location"
    REACTION = "reaction"
    ORDER = "order"                   # Pedido desde catálogo
    UNKNOWN = "unknown"


class InteractiveType(str, Enum):
    BUTTON_REPLY = "button_reply"     # Respuesta a botón
    LIST_REPLY = "list_reply"         # Respuesta a lista
    NONE = "none"


@dataclass
class IncomingMessage:
    """Mensaje entrante de WhatsApp ya parseado."""
    message_id: str
    from_number: str                  # Teléfono del cliente (whatsapp_id)
    phone_number_id: str              # Nuestro número que lo recibió
    timestamp: datetime
    type: MessageType

    # Contenido según tipo
    text: str = ""                    # Para TEXT
    interactive_id: str = ""          # ID del botón/lista clickeado
    interactive_title: str = ""       # Texto visible del botón
    interactive_type: InteractiveType = InteractiveType.NONE

    # Metadata
    contact_name: str = ""            # Nombre del perfil WA
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_webhook(cls, data: dict) -> Optional["IncomingMessage"]:
        """Parsea el payload del webhook de WhatsApp."""
        try:
            entry = data.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})

            metadata = value.get("metadata", {})
            phone_number_id = metadata.get("phone_number_id", "")

            messages = value.get("messages", [])
            if not messages:
                return None

            msg = messages[0]
            contacts = value.get("contacts", [{}])
            contact_name = contacts[0].get("profile", {}).get("name", "") if contacts else ""

            msg_type = MessageType(msg.get("type", "unknown"))

            text = ""
            interactive_id = ""
            interactive_title = ""
            interactive_type = InteractiveType.NONE

            if msg_type == MessageType.TEXT:
                text = msg.get("text", {}).get("body", "")

            elif msg_type == MessageType.INTERACTIVE:
                ir = msg.get("interactive", {})
                ir_type = ir.get("type", "")
                if ir_type == "button_reply":
                    interactive_type = InteractiveType.BUTTON_REPLY
                    reply = ir.get("button_reply", {})
                    interactive_id = reply.get("id", "")
                    interactive_title = reply.get("title", "")
                elif ir_type == "list_reply":
                    interactive_type = InteractiveType.LIST_REPLY
                    reply = ir.get("list_reply", {})
                    interactive_id = reply.get("id", "")
                    interactive_title = reply.get("title", "")

            elif msg_type == MessageType.ORDER:
                # Pedido desde catálogo de WhatsApp
                text = "__ORDER__"

            return cls(
                message_id=msg.get("id", ""),
                from_number=msg.get("from", ""),
                phone_number_id=phone_number_id,
                timestamp=datetime.fromtimestamp(int(msg.get("timestamp", 0))),
                type=msg_type,
                text=text,
                interactive_id=interactive_id,
                interactive_title=interactive_title,
                interactive_type=interactive_type,
                contact_name=contact_name,
                raw=data,
            )
        except Exception:
            return None


@dataclass
class OutgoingMessage:
    """Mensaje de respuesta a construir."""
    to: str
    text: str = ""
    buttons: List[Dict[str, str]] = field(default_factory=list)    # [{id, title}]
    list_sections: List[Dict] = field(default_factory=list)        # Para listas
    list_button_text: str = "Ver opciones"
    header: str = ""
    footer: str = ""
