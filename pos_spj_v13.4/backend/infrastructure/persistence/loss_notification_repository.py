"""LOSS-19 recipient resolution, inbox delivery and immutable attempt audit."""
import json
from datetime import datetime,timezone
from backend.shared.ids import new_uuid
class LossNotificationRepository:
    def __init__(self,connection):self._db=connection
    def find_processed(self,operation_id):
        row=self._db.execute("SELECT result_json FROM loss_processed_operations WHERE operation_id=?",(operation_id,)).fetchone();return json.loads(row[0]) if row else None
    def resolve_recipients(self,branch_id,roles):
        if not roles:return ()
        marks=",".join("?" for _ in roles);rows=self._db.execute(f"SELECT user_id,phone_e164,in_app_enabled,whatsapp_enabled FROM loss_notification_subscriptions WHERE branch_id=? AND active=1 AND role_code IN ({marks})",(branch_id,*tuple(roles))).fetchall();merged={}
        for user,phone,in_app,wa in rows:
            item=merged.setdefault(user,{"user_id":user,"phone_e164":phone,"channels":set()})
            if in_app:item["channels"].add("IN_APP")
            if wa:item["channels"].add("WHATSAPP")
        return tuple(merged.values())
    def prepare(self,*,operation_id,event,recipient,channels,severity,message):
        result=[];now=self._now()
        for channel in channels:
            row=self._db.execute("SELECT id,recipient_user_id,phone_e164,channel,status FROM loss_notification_deliveries WHERE source_event_id=? AND recipient_user_id=? AND channel=?",(event["event_id"],recipient["user_id"],channel.value)).fetchone()
            if row is None:
                delivery_id=new_uuid();self._db.execute("INSERT INTO loss_notification_deliveries (id,source_event_id,routing_operation_id,loss_case_id,recipient_user_id,channel,severity,message,phone_e164,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,'PENDING',?)",(delivery_id,event["event_id"],operation_id,event.get("loss_case_id",event["entity_id"]),recipient["user_id"],channel.value,severity,message,recipient.get("phone_e164"),now));row=(delivery_id,recipient["user_id"],recipient.get("phone_e164"),channel.value,"PENDING")
            if row[4]!="SENT":result.append(dict(zip(("id","recipient_user_id","phone_e164","channel","status"),row)))
        self._db.commit();return result
    def audit(self,*,delivery_id,status,provider_message_id,error):
        now=self._now();attempt=self._db.execute("SELECT attempt_count FROM loss_notification_deliveries WHERE id=?",(delivery_id,)).fetchone()[0]+1
        self._db.execute("UPDATE loss_notification_deliveries SET status=?,provider_message_id=?,last_error=?,attempt_count=?,sent_at=? WHERE id=?",(status,provider_message_id,error,attempt,now if status=="SENT" else None,delivery_id));self._db.execute("INSERT INTO loss_notification_audit (id,delivery_id,attempt_number,status,provider_message_id,error,occurred_at) VALUES (?,?,?,?,?,?,?)",(new_uuid(),delivery_id,attempt,status,provider_message_id,error,now));self._db.commit()
    def mark_processed(self,operation_id,event_id,count,failures=0):
        result={"event_id":event_id,"delivery_count":count,"failed_count":failures};self._db.execute("INSERT INTO loss_processed_operations (operation_id,operation_type,result_entity_id,result_json,processed_at) VALUES (?,?,?,?,?)",(operation_id,"ROUTE_LOSS_NOTIFICATIONS",event_id,json.dumps(result,sort_keys=True),self._now()));self._db.commit()
    @staticmethod
    def _now():return datetime.now(timezone.utc).isoformat()
