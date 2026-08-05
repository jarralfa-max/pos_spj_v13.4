"""Provider adapters used by LOSS-19 without embedding provider logic."""
class LossInAppNotificationSender:
    def send(self,*,delivery_id,**_):return delivery_id
class LossWhatsAppNotificationSender:
    def __init__(self,message_service):self._service=message_service
    def send(self,*,phone_e164,message,idempotency_key,**_):return self._service.send_message(phone_e164=phone_e164,message=message,idempotency_key=idempotency_key)
class UnavailableWhatsAppNotificationSender:
    def send(self,**_):raise RuntimeError("Proveedor WhatsApp no configurado")
