# messaging/sender.py — Envío de mensajes via WhatsApp Cloud API
"""
Cliente HTTP para enviar mensajes, botones, listas y templates.
Configuración dinámica desde ERP (multi-sucursal) con fallback a .env.
"""
from __future__ import annotations

import httpx
import logging
import re
from typing import List, Dict, Optional, Tuple

from config.settings import WA_API_URL, WA_ACCESS_TOKEN, WA_PHONE_NUMBER_ID, ERP_DB_PATH
from models.message import OutgoingMessage

logger = logging.getLogger("wa.sender")

# -----------------------------------------------------------------------------
#  Utilidades
# -----------------------------------------------------------------------------

def _normalize_phone(phone: str) -> str:
    """
    Normaliza un número de teléfono a formato E.164 (con + y código de país).
    Ejemplo: '5215659274265' -> '+5215659274265'
    """
    phone = phone.strip()
    if not phone:
        raise ValueError("Número de teléfono vacío")
    if phone.startswith('+'):
        return phone
    # Si ya tiene código de país pero sin + (ej. 521...), agregamos +
    if re.match(r'^\d{10,15}$', phone):
        return f"+{phone}"
    # Si tiene formato raro, intentamos limpiar solo dígitos
    digits = re.sub(r'\D', '', phone)
    if digits:
        return f"+{digits}"
    raise ValueError(f"Número inválido: {phone}")

# -----------------------------------------------------------------------------
#  Configuración dinámica (ERP + .env)
# -----------------------------------------------------------------------------

def _get_whatsapp_config(sucursal_id: Optional[int] = None) -> Tuple[str, str]:
    """
    Obtiene token y phone_id desde la base de datos (ERP) con fallback a .env.
    Retorna: (token, phone_id)
    Lanza ValueError si no se puede obtener ninguna configuración válida.
    """
    token = None
    phone_id = None

    # 1) Intentar desde ERP consultando directamente la tabla whatsapp_numeros
    try:
        from erp.bridge import ERPBridge
        erp = ERPBridge(ERP_DB_PATH)
        
        query = """
            SELECT meta_token, meta_phone_id 
            FROM whatsapp_numeros 
            WHERE activo = 1 
        """
        params = []
        if sucursal_id:
            query += " AND sucursal_id = ?"
            params.append(sucursal_id)
        else:
            query += " ORDER BY sucursal_id LIMIT 1"
        
        row = erp.db.execute(query, params).fetchone()
        if row:
            token = row["meta_token"]
            phone_id = row["meta_phone_id"]
            if token and phone_id:
                logger.debug("Configuración obtenida desde BD (sucursal=%s)", sucursal_id or "primera activa")
                return token, phone_id
    except Exception as e:
        logger.warning("Error al acceder a BD para obtener configuración WhatsApp: %s", e)

    # 2) Fallback a variables de entorno
    token = WA_ACCESS_TOKEN
    phone_id = WA_PHONE_NUMBER_ID
    if token and phone_id:
        logger.debug("Configuración obtenida desde .env")
        return token, phone_id

    # 3) Sin configuración válida
    raise ValueError("No se pudo obtener token y phone_id para WhatsApp (ni BD ni .env)")


def _build_headers(token: str) -> dict:
    """Construye headers de autorización para la API de WhatsApp."""
    if not token:
        raise ValueError("Token de WhatsApp vacío")
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }


# -----------------------------------------------------------------------------
#  Funciones públicas de envío
# -----------------------------------------------------------------------------

async def send_message(msg: OutgoingMessage, sucursal_id: Optional[int] = None) -> bool:
    """
    Envía un mensaje de WhatsApp (texto, botones o lista).
    - msg: modelo OutgoingMessage
    - sucursal_id: opcional, si no se especifica se usa la primera sucursal activa
    """
    try:
        # Obtener configuración dinámica
        token, phone_id = _get_whatsapp_config(sucursal_id)

        # Construir payload según tipo de mensaje (los builders normalizan el número)
        if msg.buttons:
            payload = _build_buttons(msg)
        elif msg.list_sections:
            payload = _build_list(msg)
        else:
            payload = _build_text(msg)

        # Construir URL y headers
        url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
        headers = _build_headers(token)

        # Enviar petición
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code == 200:
            logger.info("Mensaje enviado a %s (sucursal=%s)", _normalize_phone(msg.to), sucursal_id)
            return True
        else:
            logger.error("Error enviando a %s: %s %s",
                         _normalize_phone(msg.to), resp.status_code, resp.text[:200])
            return False

    except ValueError as ve:
        logger.error("Error de configuración o formato: %s", ve)
        return False
    except httpx.TimeoutException:
        logger.error("Timeout al enviar mensaje a %s", _normalize_phone(msg.to))
        return False
    except Exception as e:
        logger.error("send_message exception: %s", e, exc_info=True)
        return False


async def send_text(to: str, text: str, sucursal_id: Optional[int] = None) -> bool:
    """Shortcut para enviar texto simple."""
    return await send_message(OutgoingMessage(to=to, text=text), sucursal_id=sucursal_id)


async def send_buttons(to: str, body: str,
                       buttons: List[Dict[str, str]],
                       header: str = "", footer: str = "",
                       sucursal_id: Optional[int] = None) -> bool:
    """Shortcut para enviar botones (máx 3)."""
    return await send_message(OutgoingMessage(
        to=to, text=body, buttons=buttons[:3],
        header=header, footer=footer), sucursal_id=sucursal_id)


async def send_list(to: str, body: str,
                    sections: List[Dict],
                    button_text: str = "Ver opciones",
                    header: str = "", footer: str = "",
                    sucursal_id: Optional[int] = None) -> bool:
    """Shortcut para enviar lista interactiva (máx 10 items por sección)."""
    return await send_message(OutgoingMessage(
        to=to, text=body, list_sections=sections,
        list_button_text=button_text, header=header, footer=footer), sucursal_id=sucursal_id)


async def send_template(to: str, template_name: str,
                        language: str = "es_MX",
                        components: List[Dict] = None,
                        sucursal_id: Optional[int] = None) -> bool:
    """
    Envía un template pre-aprobado (para mensajes fuera de ventana 24h).
    """
    try:
        to = _normalize_phone(to)
        token, phone_id = _get_whatsapp_config(sucursal_id)

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
            }
        }
        if components:
            payload["template"]["components"] = components

        url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
        headers = _build_headers(token)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code == 200:
            logger.info("Template '%s' enviado a %s (sucursal=%s)", template_name, to, sucursal_id)
            return True
        else:
            logger.error("Error enviando template a %s: %s %s",
                         to, resp.status_code, resp.text[:200])
            return False

    except ValueError as ve:
        logger.error("Error de configuración en send_template: %s", ve)
        return False
    except httpx.TimeoutException:
        logger.error("Timeout enviando template a %s", to)
        return False
    except Exception as e:
        logger.error("send_template exception: %s", e, exc_info=True)
        return False


# -----------------------------------------------------------------------------
#  Payload builders (normalizan el número dentro de cada uno)
# -----------------------------------------------------------------------------

def _build_text(msg: OutgoingMessage) -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": _normalize_phone(msg.to),
        "type": "text",
        "text": {"body": msg.text},
    }


def _build_buttons(msg: OutgoingMessage) -> dict:
    """Construye payload de botones interactivos (máx 3)."""
    to_norm = _normalize_phone(msg.to)
    action_buttons = []
    for btn in msg.buttons[:3]:
        action_buttons.append({
            "type": "reply",
            "reply": {
                "id": btn["id"],
                "title": btn["title"][:20],  # Límite WA: 20 chars
            }
        })

    body = {
        "messaging_product": "whatsapp",
        "to": to_norm,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": msg.text},
            "action": {"buttons": action_buttons},
        }
    }
    if msg.header:
        body["interactive"]["header"] = {"type": "text", "text": msg.header}
    if msg.footer:
        body["interactive"]["footer"] = {"text": msg.footer}
    return body


def _build_list(msg: OutgoingMessage) -> dict:
    """Construye payload de lista interactiva."""
    to_norm = _normalize_phone(msg.to)
    sections = []
    for sec in msg.list_sections:
        rows = []
        for item in sec.get("rows", [])[:10]:
            row = {"id": item["id"], "title": item["title"][:24]}
            if item.get("description"):
                row["description"] = item["description"][:72]
            rows.append(row)
        sections.append({
            "title": sec.get("title", "Opciones")[:24],
            "rows": rows,
        })

    body = {
        "messaging_product": "whatsapp",
        "to": to_norm,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": msg.text},
            "action": {
                "button": msg.list_button_text[:20],
                "sections": sections,
            },
        }
    }
    if msg.header:
        body["interactive"]["header"] = {"type": "text", "text": msg.header}
    if msg.footer:
        body["interactive"]["footer"] = {"text": msg.footer}
    return body