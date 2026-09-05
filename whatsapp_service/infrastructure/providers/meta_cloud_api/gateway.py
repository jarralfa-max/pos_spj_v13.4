# infrastructure/providers/meta_cloud_api/gateway.py — WA-5 (§22 del prompt maestro)
"""
MetaCloudApiWhatsAppGateway — implementación concreta de
`domain.whatsapp.provider_ports.WhatsAppProviderGateway`.

**No reimplementa el envío.** Reutiliza el único punto real que ya llama a
la Graph API para enviar (`messaging.sender._post_message`, extraído en
esta misma fase de `send_message`/`send_template` — funciones ya en
producción, sin cambiar su contrato público) y las mismas piezas de
config/consentimiento/normalización/redacción que esas funciones ya usan
(`_get_whatsapp_config`, `_build_headers`, `_normalize_phone`,
`_is_whatsapp_opted_out`, `redact_phone`). Este gateway es una fachada con
la forma del `Protocol` — no un segundo sender (§2/§81 del prompt maestro:
"un solo sender").

Lo que SÍ es genuinamente nuevo en esta fase (nada de esto existía antes
en el árbol): `send_media`, `mark_read`, `download_media`,
`get_message_status`, `health_check`.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

import httpx

logger = logging.getLogger("wa.provider.meta")

_SUPPORTED_MEDIA_TYPES = {"image", "audio", "video", "document", "sticker"}


class MetaCloudApiWhatsAppGateway:
    """Implementa `WhatsAppProviderGateway` contra la API de Meta Cloud."""

    def __init__(self, *, sucursal_id: Optional[int] = None) -> None:
        self._sucursal_id = sucursal_id

    # ── Envío — construyen el payload y delegan en _send_payload ───────────

    async def send_text(self, *, to: str, body: str) -> Dict[str, Any]:
        return await self._send_payload(
            to, lambda norm_to: {
                "messaging_product": "whatsapp", "to": norm_to,
                "type": "text", "text": {"body": body},
            }
        )

    async def send_template(
        self, *, to: str, template_name: str, language: str, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        def _build(norm_to: str) -> dict:
            payload: Dict[str, Any] = {
                "messaging_product": "whatsapp", "to": norm_to, "type": "template",
                "template": {"name": template_name, "language": {"code": language}},
            }
            if parameters:
                # Meta exige parámetros de body POSICIONALES, no nombrados —
                # se usa el orden de inserción del dict (Python 3.7+
                # garantiza ese orden). El llamador es responsable de pasar
                # `parameters` ya en el orden correcto del template.
                body_params = [{"type": "text", "text": str(v)} for v in parameters.values()]
                payload["template"]["components"] = [{"type": "body", "parameters": body_params}]
            return payload

        return await self._send_payload(to, _build)

    async def send_interactive(self, *, to: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """`payload` es el objeto `interactive` completo tal como lo
        construyen los flows (`type`/`body`/`action`/...) — este gateway
        solo envuelve el sobre `messaging_product`/`to`/`type`; construir
        botones/listas sigue siendo responsabilidad de la capa
        conversacional (hoy `messaging/interactive.py`, WA-7 a futuro)."""
        return await self._send_payload(
            to, lambda norm_to: {
                "messaging_product": "whatsapp", "to": norm_to,
                "type": "interactive", "interactive": payload,
            }
        )

    async def send_media(self, *, to: str, media_type: str, media_reference: str) -> Dict[str, Any]:
        if media_type not in _SUPPORTED_MEDIA_TYPES:
            return {
                "ok": False, "provider_message_id": None,
                "error": f"tipo de media no soportado: {media_type!r}", "raw": None,
            }
        key = "link" if media_reference.startswith("http") else "id"
        return await self._send_payload(
            to, lambda norm_to: {
                "messaging_product": "whatsapp", "to": norm_to,
                "type": media_type, media_type: {key: media_reference},
            }
        )

    async def mark_read(self, *, provider_message_id: str) -> None:
        from messaging.sender import _build_headers, _get_whatsapp_config, _post_message
        from config.settings import get_wa_api_url

        try:
            token, phone_id = _get_whatsapp_config(self._sucursal_id)
        except ValueError as exc:
            logger.warning("mark_read: no se pudo resolver configuración: %s", exc)
            return

        payload = {
            "messaging_product": "whatsapp", "status": "read", "message_id": provider_message_id,
        }
        result = await _post_message(get_wa_api_url(phone_id), payload, _build_headers(token))
        if not result["ok"]:
            logger.warning("mark_read falló para %s: %s", provider_message_id, result["error"])

    # ── Media (§62) ──────────────────────────────────────────────────────────

    async def download_media(self, *, media_id: str) -> bytes:
        """Descarga en 2 pasos, como exige la Graph API: (1) `GET
        /{media_id}` devuelve metadata + una URL firmada temporal, (2) `GET`
        esa URL con el mismo Bearer token descarga el binario."""
        from messaging.sender import _build_headers, _get_whatsapp_config
        from config.settings import WA_API_VERSION

        token, _phone_id = _get_whatsapp_config(self._sucursal_id)
        headers = _build_headers(token)
        meta_url = f"https://graph.facebook.com/{WA_API_VERSION}/{media_id}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            meta_resp = await client.get(meta_url, headers=headers)
            meta_resp.raise_for_status()
            media_url = meta_resp.json()["url"]
            file_resp = await client.get(media_url, headers=headers)
            file_resp.raise_for_status()
            return file_resp.content

    # ── Status (§22) — limitación real de la API, no una omisión ────────────

    async def get_message_status(self, *, provider_message_id: str) -> Optional[str]:
        """Meta Cloud API **no expone ningún endpoint para consultar el
        estado de un mensaje por su ID**. Los estados (sent/delivered/read/
        failed) solo llegan como eventos de webhook (`statuses` dentro del
        payload de `POST /webhook`, §15/§55). Este método existe para
        cumplir el `Protocol` (§22 del prompt maestro lo pide
        explícitamente), pero siempre retorna `None` — el estado real se
        procesa donde realmente llega: el webhook (WA-6), actualizando
        `WhatsAppMessageDelivery` directamente. No finge un polling que la
        API no soporta."""
        return None

    # ── Health (§58) ──────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Ping ligero y real — no existe un endpoint de "ping" dedicado en
        la Graph API, así que se usa la consulta más barata que igual
        valida conectividad + autenticación reales: `GET
        /{phone_number_id}`. Síncrono a propósito (ver nota en
        `provider_ports.py`) — `bootstrap/health_checks.py` es un
        agregador síncrono."""
        from messaging.sender import _get_whatsapp_config
        from config.settings import WA_API_VERSION

        try:
            token, phone_id = _get_whatsapp_config(self._sucursal_id)
        except ValueError:
            return False

        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(
                    f"https://graph.facebook.com/{WA_API_VERSION}/{phone_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
            return resp.status_code == 200
        except Exception:
            return False

    # ── Interno ──────────────────────────────────────────────────────────────

    async def _send_payload(
        self, to: str, build_payload: Callable[[str], dict]
    ) -> Dict[str, Any]:
        """Resuelve config + valida consentimiento + arma payload + envía
        vía `messaging.sender._post_message` — el único camino real de
        salida, compartido con `send_message`/`send_template`."""
        from messaging.sender import (
            _build_headers,
            _get_whatsapp_config,
            _is_whatsapp_opted_out,
            _normalize_phone,
            _post_message,
            redact_phone,
        )
        from config.settings import get_wa_api_url

        try:
            normalized_to = _normalize_phone(to)
        except ValueError as exc:
            return {"ok": False, "provider_message_id": None, "error": str(exc), "raw": None}

        if _is_whatsapp_opted_out(normalized_to):
            logger.warning(
                "Envío bloqueado por consentimiento retirado: %s", redact_phone(normalized_to)
            )
            return {"ok": False, "provider_message_id": None, "error": "opted_out", "raw": None}

        try:
            token, phone_id = _get_whatsapp_config(self._sucursal_id)
        except ValueError as exc:
            return {"ok": False, "provider_message_id": None, "error": str(exc), "raw": None}

        payload = build_payload(normalized_to)
        result = await _post_message(
            get_wa_api_url(phone_id), payload, _build_headers(token)
        )
        if result["ok"]:
            logger.info("Mensaje enviado a %s", redact_phone(normalized_to))
        else:
            logger.error("Error enviando a %s: %s", redact_phone(normalized_to), result["error"])
        return {
            "ok": result["ok"],
            "provider_message_id": result["provider_message_id"],
            "error": result["error"],
            "raw": result["raw"],
        }
