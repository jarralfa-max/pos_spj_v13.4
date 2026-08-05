import unittest
from backend.application.losses.notifications import LossNotificationRouter,RouteLossEventCommand
from backend.domain.losses.notifications import NotificationChannel
from backend.shared.ids import new_uuid
class Repo:
    def __init__(self,ids):self.ids=ids;self.processed={};self.audits=[]
    def find_processed(self,op):return self.processed.get(op)
    def resolve_recipients(self,branch,roles):return ({"user_id":self.ids["manager"],"phone_e164":"+5215551234567","channels":{"IN_APP","WHATSAPP"}},)
    def prepare(self,**kw):
        deliveries=[]
        for channel in kw["channels"]:deliveries.append({"id":new_uuid(),"recipient_user_id":kw["recipient"]["user_id"],"phone_e164":kw["recipient"]["phone_e164"],"channel":channel.value,"status":"PENDING"})
        return deliveries
    def audit(self,**kw):self.audits.append(kw)
    def mark_processed(self,operation_id,event_id,count,failures=0):self.processed[operation_id]={"event_id":event_id,"delivery_count":count,"failed_count":failures}
class Sender:
    def __init__(self):self.calls=[]
    def send(self,**kw):self.calls.append(kw);return "provider-1"
def event(ids,name="LOSS_HIGH_VALUE_DETECTED"):
    return {"event_id":ids["event"],"event_name":name,"operation_id":ids["source_op"],"entity_id":ids["case"],"branch_id":ids["branch"],"warehouse_id":ids["warehouse"],"user_id":ids["actor"],"timestamp":"2026-08-04T10:00:00+00:00","source_module":"losses","loss_case_id":ids["case"]}
class LossNotificationsTest(unittest.TestCase):
    def setUp(self):
        self.ids={n:new_uuid() for n in ("event","source_op","route_op","case","branch","warehouse","actor","manager")};self.repo=Repo(self.ids);self.inapp=Sender();self.wa=Sender();self.router=LossNotificationRouter(self.repo,self.inapp,self.wa)
    def test_critical_event_routes_in_app_and_whatsapp_with_delivery_id_as_key(self):
        result=self.router.route(RouteLossEventCommand(self.ids["route_op"],event(self.ids)));self.assertEqual(result.delivery_count,2);self.assertEqual(len(self.inapp.calls),1);self.assertEqual(len(self.wa.calls),1);self.assertEqual(self.wa.calls[0]["idempotency_key"],self.wa.calls[0]["delivery_id"]);self.assertEqual(len(self.repo.audits),2)
    def test_operational_event_is_in_app_only_and_replay_is_safe(self):
        first=self.router.route(RouteLossEventCommand(self.ids["route_op"],event(self.ids,"LOSS_CASE_SUBMITTED")));replay=self.router.route(RouteLossEventCommand(self.ids["route_op"],event(self.ids,"LOSS_CASE_SUBMITTED")));self.assertEqual(first.delivery_count,1);self.assertTrue(replay.replayed);self.assertEqual(len(self.inapp.calls),1);self.assertEqual(len(self.wa.calls),0)
    def test_non_loss_event_is_rejected(self):
        bad=event(self.ids);bad["source_module"]="sales"
        with self.assertRaises(ValueError):self.router.route(RouteLossEventCommand(self.ids["route_op"],bad))
if __name__=="__main__":unittest.main()
