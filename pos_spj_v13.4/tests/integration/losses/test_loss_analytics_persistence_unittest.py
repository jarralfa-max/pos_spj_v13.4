import importlib,sqlite3,unittest
from datetime import datetime,timezone
from decimal import Decimal
from backend.application.losses.analytics import LossAnalyticsQuery,LossAnalyticsQueryService
from backend.application.losses.execution_context import LossExecutionContext
from backend.infrastructure.persistence.loss_analytics_repository import LossAnalyticsRepository
from backend.shared.ids import new_uuid
class Auth:
    def require(self,*_):pass
class AnalyticsPersistenceTest(unittest.TestCase):
    def test_kpis_pareto_trend_charts_and_csv_use_scoped_values(self):
        db=sqlite3.connect(":memory:");importlib.import_module("migrations.standalone.174_losses_bounded_context_schema").run(db);branch,other,warehouse,actor=(new_uuid() for _ in range(4));catalog=db.execute("SELECT c.id,r.id FROM loss_classifications c JOIN loss_reasons r ON r.classification_id=c.id ORDER BY c.code LIMIT 2").fetchall()
        for index,(classification,reason) in enumerate((catalog[0],catalog[0],catalog[1])):
            target=other if index==2 else branch;gross=(Decimal("100"),Decimal("50"),Decimal("999"))[index];recovered=(Decimal("25"),Decimal("0"),Decimal("0"))[index];occurred=("2026-08-01T10:00:00+00:00","2026-08-02T10:00:00+00:00","2026-08-02T10:00:00+00:00")[index]
            db.execute("INSERT INTO loss_cases (id,operation_id,branch_id,warehouse_id,reported_by_user_id,classification_id,reason_id,origin,status,requires_inventory_posting,gross_value,recoverable_value,net_loss_value,occurred_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,'INVENTORY','CLOSED',0,?,?,?,?,?,?)",(new_uuid(),new_uuid(),target,warehouse,actor,classification,reason,str(gross),str(recovered),str(gross-recovered),occurred,occurred,occurred))
        db.commit();context=LossExecutionContext(actor,branch,frozenset(),frozenset({warehouse}));query=LossAnalyticsQuery(context,branch,datetime(2026,8,1,tzinfo=timezone.utc),datetime(2026,8,3,tzinfo=timezone.utc));service=LossAnalyticsQueryService(LossAnalyticsRepository(db),Auth());dashboard=service.dashboard(query)
        self.assertEqual(dashboard.kpis.case_count,2);self.assertEqual(dashboard.kpis.net_loss_value,Decimal("125"));self.assertEqual(len(dashboard.trend),2);self.assertEqual(dashboard.pareto[-1].cumulative_percent,Decimal("100"));self.assertEqual(service.export_csv(query).count("\n"),3);db.close()
if __name__=="__main__":unittest.main()
