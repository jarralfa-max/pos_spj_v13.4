import unittest
from datetime import datetime,timezone
from decimal import Decimal
from backend.application.losses.analytics import LossAnalyticsQueryService,LossAnalyticsQuery
from backend.application.losses.execution_context import LossExecutionContext
from backend.domain.losses.exceptions import LossInvariantError
from backend.shared.ids import new_uuid
class Auth:
    def __init__(self):self.calls=[]
    def require(self,*args):self.calls.append(args)
class Repo:
    def summary(self,**_):return {"case_count":4,"gross_value":"200","recovered_value":"50","net_loss_value":"150","open_investigations":2,"overdue_actions":1}
    def status_distribution(self,**_):return [("CLOSED",3),("UNDER_REVIEW",1)]
    def pareto(self,**_):return [("EXPIRY","Caducidad","90"),("DAMAGE","Daño","45"),("OTHER","Otra","15")]
    def trend(self,**_):return [("2026-08-01","40"),("2026-08-02","60"),("2026-08-03","50")]
    def export_rows(self,**_):return [("case-1","2026-08-01","Caducidad","CLOSED","100","25","75","MXN")]
class AnalyticsTest(unittest.TestCase):
    def setUp(self):
        self.branch=new_uuid();self.ctx=LossExecutionContext(new_uuid(),self.branch,frozenset(),frozenset());self.auth=Auth();self.svc=LossAnalyticsQueryService(Repo(),self.auth);self.query=LossAnalyticsQuery(self.ctx,self.branch,datetime(2026,8,1,tzinfo=timezone.utc),datetime(2026,8,4,tzinfo=timezone.utc))
    def test_kpis_charts_pareto_and_trend(self):
        dashboard=self.svc.dashboard(self.query);self.assertEqual(dashboard.kpis.net_loss_value,Decimal("150"));self.assertEqual(dashboard.kpis.recovery_rate,Decimal("25"));self.assertEqual(dashboard.pareto[-1].cumulative_percent,Decimal("100"));self.assertEqual(len(dashboard.charts),3)
    def test_export_is_stable_csv_and_permission_guarded(self):
        content=self.svc.export_csv(self.query);self.assertIn("case_id,occurred_on,classification,status,gross_value,recovered_value,net_loss_value,currency_code",content);self.assertIn("Caducidad",content)
    def test_invalid_range_and_out_of_scope_branch_are_rejected(self):
        with self.assertRaises(LossInvariantError):self.svc.dashboard(LossAnalyticsQuery(self.ctx,self.branch,datetime(2026,8,4,tzinfo=timezone.utc),datetime(2026,8,1,tzinfo=timezone.utc)))
        with self.assertRaises(Exception):self.svc.dashboard(LossAnalyticsQuery(self.ctx,new_uuid(),self.query.start_at,self.query.end_at))
if __name__=="__main__":unittest.main()
