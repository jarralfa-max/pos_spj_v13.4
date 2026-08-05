"""LOSS-19 idempotent notification router for Losses domain events."""
from dataclasses import dataclass
from backend.domain.losses.notifications import LossNotificationPolicy,NotificationChannel,valid_e164
from backend.shared.ids import validate_uuidv7
@dataclass(frozen=True,slots=True)
class RouteLossEventCommand:operation_id:str;event:dict
@dataclass(frozen=True,slots=True)
class NotificationRoutingResult:event_id:str;delivery_count:int;failed_count:int=0;replayed:bool=False
class LossNotificationRouter:
    def __init__(self,repository,in_app_sender,whatsapp_sender,policy=None):self._repository=repository;self._in_app=in_app_sender;self._whatsapp=whatsapp_sender;self._policy=policy or LossNotificationPolicy()
    def route(self,command):
        validate_uuidv7(command.operation_id);event=command.event
        if event.get("source_module")!="losses":raise ValueError("LOSS-19 sólo acepta eventos del bounded context Losses")
        for field in ("event_id","operation_id","entity_id","branch_id","user_id"):validate_uuidv7(event[field])
        replay=self._repository.find_processed(command.operation_id)
        if replay:return NotificationRoutingResult(replay["event_id"],replay["delivery_count"],replay.get("failed_count",0),True)
        rule=self._policy.rule_for(event["event_name"])
        if rule is None:self._repository.mark_processed(command.operation_id,event["event_id"],0);return NotificationRoutingResult(event["event_id"],0)
        recipients=self._repository.resolve_recipients(event["branch_id"],rule.roles);deliveries=[]
        for recipient in recipients:
            channels=rule.channels & {NotificationChannel(value) for value in recipient["channels"]}
            if NotificationChannel.WHATSAPP in channels and not valid_e164(recipient.get("phone_e164")):channels=channels-{NotificationChannel.WHATSAPP}
            deliveries.extend(self._repository.prepare(operation_id=command.operation_id,event=event,recipient=recipient,channels=channels,severity=rule.severity,message=self._message(event,rule.severity)))
        failures=0
        for delivery in deliveries:
            sender=self._in_app if delivery["channel"]==NotificationChannel.IN_APP.value else self._whatsapp
            try:
                provider_id=sender.send(delivery_id=delivery["id"],recipient_user_id=delivery["recipient_user_id"],phone_e164=delivery.get("phone_e164"),message=self._message(event,rule.severity),idempotency_key=delivery["id"])
                self._repository.audit(delivery_id=delivery["id"],status="SENT",provider_message_id=provider_id,error=None)
            except Exception as exc:
                failures+=1;self._repository.audit(delivery_id=delivery["id"],status="FAILED",provider_message_id=None,error=str(exc))
        self._repository.mark_processed(command.operation_id,event["event_id"],len(deliveries),failures)
        return NotificationRoutingResult(event["event_id"],len(deliveries),failures)
    @staticmethod
    def _message(event,severity):return f"[{severity}] Mermas: {event['event_name']} · expediente {event.get('loss_case_id',event['entity_id'])}"
