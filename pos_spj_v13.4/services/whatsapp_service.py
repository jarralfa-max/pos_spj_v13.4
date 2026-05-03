
# services/whatsapp_service.py — SHIM v12
# El servicio canónico está en core/services/whatsapp_service.py
from core.services.whatsapp_service import (
    WhatsAppService, WhatsAppWebhookServer, WhatsAppConfig, MessageQueue
)
__all__ = ['WhatsAppService', 'WhatsAppWebhookServer', 'WhatsAppConfig', 'MessageQueue']
