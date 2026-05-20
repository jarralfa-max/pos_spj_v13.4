# core/services/whatsapp_credential_service.py
"""
Servicio de gestión segura de credenciales Meta/WhatsApp.

Valida tokens antes de guardarlos y enmascara tokens al mostrarlos.
No loggea tokens completos en ningún nivel de logging.
"""
from __future__ import annotations
import logging
import urllib.request
import urllib.error
import json
from typing import Dict, Tuple

from core.repositories.whatsapp_config_repository import WhatsAppConfigRepository

logger = logging.getLogger("spj.service.whatsapp_credential")

_GRAPH_API = "https://graph.facebook.com/v21.0"


def _mask_token(token: str) -> str:
    """Retorna token enmascarado: primeros 8 chars + *** + últimos 4."""
    if not token or len(token) < 12:
        return "***"
    return f"{token[:8]}***{token[-4:]}"


class WhatsAppCredentialService:
    """Gestión segura de credenciales Meta WhatsApp."""

    def __init__(self, db):
        self._repo = WhatsAppConfigRepository(db)

    def save_credentials(self, token: str, phone_number_id: str,
                          verify_token: str = "") -> None:
        """Guarda credenciales en BD. No valida formato aquí (validar antes con validate_meta_credentials)."""
        if not token:
            raise ValueError("El token de acceso no puede estar vacío")
        if not phone_number_id:
            raise ValueError("El Phone Number ID no puede estar vacío")
        self._repo.set_config("meta_token", token)
        self._repo.set_config("meta_phone_id", phone_number_id)
        if verify_token:
            self._repo.set_config("verify_token", verify_token)
        self._repo.commit()
        logger.info("Credenciales Meta guardadas (phone_id=%s)", phone_number_id)

    def get_masked_credentials(self) -> Dict[str, str]:
        """Retorna credenciales enmascaradas para mostrar en UI."""
        token = self._repo.get_config("meta_token", "")
        phone_id = self._repo.get_config("meta_phone_id", "")
        verify = self._repo.get_config("verify_token", "spj_verify")
        return {
            "token_masked": _mask_token(token),
            "phone_number_id": phone_id,
            "verify_token": verify,
            "configured": bool(token and phone_id),
        }

    def validate_meta_credentials(self, token: str, phone_number_id: str) -> Tuple[bool, str]:
        """
        Valida credenciales contra Graph API de Meta.
        Retorna (ok, mensaje_error).
        No loggea el token completo.
        """
        if not token:
            return False, "Token vacío"
        if not phone_number_id:
            return False, "Phone Number ID vacío"
        if len(token) < 10:
            return False, "Token demasiado corto"

        try:
            url = f"{_GRAPH_API}/{phone_number_id}"
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {token}"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                if data.get("id") == phone_number_id:
                    return True, ""
                return True, "Acceso OK (id no coincide exactamente)"
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return False, "Token inválido o expirado (401 Unauthorized)"
            if e.code == 403:
                return False, "Sin permisos para este Phone Number ID (403)"
            return False, f"Error Meta API: HTTP {e.code}"
        except urllib.error.URLError as e:
            return False, f"Sin acceso a Meta API: {e.reason}"
        except Exception as e:
            logger.debug("validate_meta_credentials: %s", type(e).__name__)
            return False, f"Error de validación: {type(e).__name__}"

    def validate_webhook_token(self, verify_token: str) -> Tuple[bool, str]:
        if not verify_token:
            return False, "Verify token vacío"
        if len(verify_token) < 6:
            return False, "Verify token demasiado corto (mínimo 6 caracteres)"
        return True, ""

    def rotate_token(self, new_token: str, phone_number_id: str) -> Tuple[bool, str]:
        """Valida el nuevo token antes de reemplazar."""
        ok, err = self.validate_meta_credentials(new_token, phone_number_id)
        if not ok:
            return False, err
        self._repo.set_config("meta_token", new_token)
        self._repo.commit()
        logger.info("Token rotado exitosamente (phone_id=%s)", phone_number_id)
        return True, ""
