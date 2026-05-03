
# integrations/whatsapp_service.py — SHIM v12
# El servicio canónico (con cola offline) está en core/services/whatsapp_service.py
from core.services.whatsapp_service import (
    WhatsAppService, WhatsAppConfig, MessageQueue
)
__all__ = ['WhatsAppService', 'WhatsAppConfig', 'MessageQueue']
