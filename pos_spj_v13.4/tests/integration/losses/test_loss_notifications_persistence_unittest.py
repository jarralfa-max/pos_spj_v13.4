import importlib,sqlite3,unittest
from backend.application.losses.notifications import LossNotificationRouter,RouteLossEventCommand
from backend.infrastructure.persistence.loss_notification_repository import LossNotificationRepository
from backend.shared.ids import new_uuid
class Sender:
    def __init__(self):self.calls=[]
    def send(self,**kw):self.calls.append(kw);return "provider-ok"
class NotificationPersistenceTest(unittest.TestCase):
    def test_in_app_whatsapp_audit_and_replay(self):
        db=sqlite3.connect(":memory:");db.execute("PRAGMA foreign_keys=ON");importlib.import_module("migrations.standalone.174_losses_bounded_context_schema").run(db)
        case,branch,warehouse,actor,manager=(new_uuid() for _ in range(5));classification,reason=db.execute("SELECT classification_id,id FROM loss_reasons LIMIT 1").fetchone();now="2026-08-04T10:00:00+00:00"
        db.execute("INSERT INTO loss_cases (id,operation_id,branch_id,warehouse_id,reported_by_user_id,classification_id,reason_id,origin,status,requires_inventory_posting,occurred_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(case,new_uuid(),branch,warehouse,actor,classification,reason,"INVENTORY","UNDER_REVIEW",0,now,now,now))
        db.execute("INSERT INTO loss_notification_subscriptions (id,user_id,branch_id,role_code,phone_e164,in_app_enabled,whatsapp_enabled,active,created_at) VALUES (?,?,?,?,?,1,1,1,?)",(new_uuid(),manager,branch,"LOSSES_MANAGER","+5215551234567",now));db.commit()
        inapp,wa=Sender(),Sender();router=LossNotificationRouter(LossNotificationRepository(db),inapp,wa);route_op=new_uuid();event={"event_id":new_uuid(),"event_name":"LOSS_HIGH_VALUE_DETECTED","operation_id":new_uuid(),"entity_id":case,"branch_id":branch,"warehouse_id":warehouse,"user_id":actor,"timestamp":now,"source_module":"losses","loss_case_id":case}
        first=router.route(RouteLossEventCommand(route_op,event));replay=router.route(RouteLossEventCommand(route_op,event))
        self.assertEqual(first.delivery_count,2);self.assertTrue(replay.replayed);self.assertEqual(db.execute("SELECT COUNT(*) FROM loss_notification_deliveries WHERE status='SENT'").fetchone()[0],2);self.assertEqual(db.execute("SELECT COUNT(*) FROM loss_notification_audit").fetchone()[0],2);self.assertEqual(len(wa.calls),1);db.close()
if __name__=="__main__":unittest.main()
