import importlib,sqlite3,unittest
from decimal import Decimal
from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.valuation import LossValuationService,ValueLossCaseCommand,ValuationLineInput
from backend.domain.losses.valuation import CostBasis,CostReferenceType
from backend.infrastructure.persistence.loss_valuation_repository import LossValuationRepository
from backend.shared.ids import new_uuid
class Auth:
    def require(self,*_):pass
class ValuationPersistenceTest(unittest.TestCase):
    def test_cost_references_values_recovery_and_events_are_atomic(self):
        db=sqlite3.connect(":memory:");db.execute("PRAGMA foreign_keys=ON");importlib.import_module("migrations.standalone.174_losses_bounded_context_schema").run(db)
        case,branch,warehouse,actor,line1,line2=(new_uuid() for _ in range(6));classification,reason=db.execute("SELECT classification_id,id FROM loss_reasons LIMIT 1").fetchone();now="2026-08-04T10:00:00+00:00"
        db.execute("INSERT INTO loss_cases (id,operation_id,branch_id,warehouse_id,reported_by_user_id,classification_id,reason_id,origin,status,requires_inventory_posting,occurred_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(case,new_uuid(),branch,warehouse,actor,classification,reason,"INVENTORY","INVENTORY_POSTED",0,now,now,now))
        for line,qty,weight in ((line1,"3","0"),(line2,"0","2.5")):db.execute("INSERT INTO loss_lines (id,loss_case_id,product_id,quantity,weight,unit,unit_cost,gross_value,recoverable_value,net_loss_value,created_at) VALUES (?,?,?,?,?,'unit','0','0','0','0',?)",(line,case,new_uuid(),qty,weight,now))
        db.execute("INSERT INTO loss_recoveries (id,loss_case_id,operation_id,recovery_type,quantity,weight,recovered_value,status,notes,recorded_by_user_id,recorded_at) VALUES (?,?,?,'OTHER','0','0','25','APPROVED','Recuperación',?,?)",(new_uuid(),case,new_uuid(),actor,now))
        svc=LossValuationService(LossValuationRepository(db),Auth());context=LossExecutionContext(actor,branch,frozenset(),frozenset({warehouse}))
        result=svc.value(ValueLossCaseCommand(new_uuid(),case,context,"MXN",(ValuationLineInput(line1,CostReferenceType.INVENTORY_AVERAGE,new_uuid(),CostBasis.QUANTITY,Decimal("3"),Decimal("10")),ValuationLineInput(line2,CostReferenceType.LOT_RECEIPT,new_uuid(),CostBasis.WEIGHT,Decimal("2.5"),Decimal("20")))))
        self.assertEqual((result.gross_value,result.recovered_value,result.net_loss_value),(Decimal("80.0"),Decimal("25"),Decimal("55.0")));self.assertEqual(db.execute("SELECT COUNT(*) FROM loss_cost_references").fetchone()[0],2);self.assertEqual(db.execute("SELECT COUNT(*) FROM loss_outbox").fetchone()[0],2);self.assertEqual(db.execute("SELECT gross_value,recoverable_value,net_loss_value FROM loss_cases").fetchone(),("80.0","25","55.0"));db.close()
if __name__=="__main__":unittest.main()
