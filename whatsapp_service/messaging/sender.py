# messaging/sender.py — Envío de mensajes via WhatsApp Cloud API
"""
Cliente HTTP para enviar mensajes, botones, listas y templates.
Configuración dinámica desde ERP (multi-sucursal) con fallback a .env.

Orden correcto de credenciales:
1. Configuración global capturada desde el módulo WhatsApp:
   configuraciones.wa_meta_token / configuraciones.wa_meta_phone_id
2. Configuración por número/sucursal en whatsapp_numeros, cuando aplique.
3. Variables .env como respaldo técnico.
"""
from __future__ import annotations

import httpx
import logging
import re
from typing import List, Dict, Optional, Tuple

try:
    from config.settings import (
        WA_ACCESS_TOKEN,
        WA_PHONE_NUMBER_ID,
        ERP_DB_PATH,
        get_wa_api_url,
        get_meta_access_token,
        get_meta_phone_number_id,
    )
except (ImportError, AttributeError):
    WA_ACCESS_TOKEN = None
    WA_PHONE_NUMBER_ID = None
    ERP_DB_PATH = None
    def get_wa_api_url(phone_number_id=None):  # type: ignore[misc]
        raise ValueError("config.settings not available")
    def get_meta_access_token():  # type: ignore[misc]
        return ""
    def get_meta_phone_number_id():  # type: ignore[misc]
        return ""
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
    if re.match(r'^\d{10,15}$', phone):
        return f"+{phone}"
    digits = re.sub(r'\D', '', phone)
    if digits:
        return f"+{digits}"
    raise ValueError(f"Número inválido: {phone}")

# -----------------------------------------------------------------------------
#  Configuración dinámica (ERP + .env)
# -----------------------------------------------------------------------------

def _get_whatsapp_config(sucursal_id: Optional[int] = None) -> Tuple[str, str]:
    """
    Obtiene token y phone_id.

    Retorna: (token, phone_id)
    Lanza ValueError si no se puede obtener ninguna configuración válida.
    """
    # 1) Configuración global guardada desde el panel Meta/Credenciales.
    # Esta debe ganar porque es lo que el usuario actualiza desde la UI.
    try:
        token = get_meta_access_token()
        phone_id = get_meta_phone_number_id()
        if token and phone_id:
            logger.debug("Configuración obtenida desde configuraciones globales del ERP")
            return token, phone_id
    except Exception as e:
        logger.warning("Error leyendo configuración global WhatsApp: %s", e)

    # 2) Configuración por número/sucursal en whatsapp_numeros.
    # Se conserva como fallback para escenarios multi-número, pero no debe pisar
    # el token global recién capturado desde el módulo.
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
                logger.debug("Configuración obtenida desde whatsapp_numeros (sucursal=%s)", sucursal_id or "primera activa")
                return token, phone_id
    except Exception as e:
        logger.warning("Error al acceder a BD para obtener configuración WhatsApp: %s", e)

    # 3) Fallback a variables de entorno.
    token = WA_ACCESS_TOKEN
    phone_id = WA_PHONE_NUMBER_ID
    if token and phone_id:
        logger.debug("Configuración obtenida desde .env")
        return token, phone_id

    raise ValueError("No se pudo obtener token y phone_id para WhatsApp (configuración global, BD o .env)")


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
        token, phone_id = _get_whatsapp_config(sucursal_id)

        if msg.buttons:
            payload = _build_buttons(msg)
        elif msg.list_sections:
            payload = _build_list(msg)
        else:
            payload = _build_text(msg)

        url = get_wa_api_url(phone_id)
        headers = _build_headers(token)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code == 200:
            logger.info("Mensaje enviado a %s (sucursal=%s)", _normalize_phone(msg.to), sucursal_id)
            return True
        else:
            logger.error("Error enviando a %s: %s %s",
                         _normalize_phone(msg.to), resp.status_code, resp.text[:500])
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

        url = get_wa_api_url(phone_id)
        headers = _build_headers(token)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code == 200:
            logger.info("Template '%s' enviado a %s (sucursal=%s)", template_name, to, sucursal_id)
            return True
        else:
            logger.error("Error enviando template a %s: %s %s",
                         to, resp.status_code, resp.text[:500])
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
                "title": btn["title"][:20],
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
    return {
        "messaging_product": "whatsapp",
        "to": _normalize_phone(msg.to),
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": msg.text},
            "action": {
                "button": msg.list_button_text or "Ver opciones",
                "sections": msg.list_sections or [],
            },
        },
    }
