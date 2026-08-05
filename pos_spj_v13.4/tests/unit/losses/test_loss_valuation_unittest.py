import unittest
from contextlib import nullcontext
from decimal import Decimal
from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.valuation import LossValuationService,ValueLossCaseCommand,ValuationLineInput
from backend.domain.losses.exceptions import LossInvariantError
from backend.domain.losses.valuation import CostBasis,CostReferenceType
from backend.shared.ids import new_uuid
class Auth:
    def require(self,*_):pass
class Repo:
    def __init__(self,ids): self.ids=ids; self.processed={}; self.saved=None
    def transaction(self):return nullcontext()
    def find_processed(self,op):return self.processed.get(op)
    def get_case(self,value):return {"id":value,"branch_id":self.ids["branch"],"warehouse_id":self.ids["warehouse"],"status":"INVENTORY_POSTED","currency_code":"MXN","approved_recovery":Decimal("25"),"line_ids":{self.ids["line1"],self.ids["line2"]}}
    def save_valuation(self,**kw): self.saved=kw; self.processed[kw["operation_id"]]={"entity_id":kw["valuation_id"],"status":"VALUED","gross_value":str(kw["valuation"].gross_value),"recovered_value":str(kw["valuation"].recovered_value),"net_loss_value":str(kw["valuation"].net_loss_value)}
def setup_ids():return {n:new_uuid() for n in ("case","branch","warehouse","actor","line1","line2","ref1","ref2","operation")}
class LossValuationTest(unittest.TestCase):
    def setUp(self):
        self.ids=setup_ids();self.repo=Repo(self.ids);self.svc=LossValuationService(self.repo,Auth());self.ctx=LossExecutionContext(self.ids["actor"],self.ids["branch"],frozenset(),frozenset({self.ids["warehouse"]}))
    def command(self):return ValueLossCaseCommand(self.ids["operation"],self.ids["case"],self.ctx,"MXN",(
        ValuationLineInput(self.ids["line1"],CostReferenceType.INVENTORY_AVERAGE,self.ids["ref1"],CostBasis.QUANTITY,Decimal("3"),Decimal("10")),
        ValuationLineInput(self.ids["line2"],CostReferenceType.LOT_RECEIPT,self.ids["ref2"],CostBasis.WEIGHT,Decimal("2.5"),Decimal("20"))))
    def test_gross_recovery_and_net_are_decimal_and_auditable(self):
        result=self.svc.value(self.command());self.assertEqual(result.gross_value,Decimal("80"));self.assertEqual(result.recovered_value,Decimal("25"));self.assertEqual(result.net_loss_value,Decimal("55"));self.assertEqual(len(self.repo.saved["valuation"].lines),2);self.assertEqual(sum((line.net_loss_value for line in self.repo.saved["valuation"].lines),Decimal("0")),Decimal("55"))
    def test_float_and_unknown_lines_are_rejected(self):
        command=self.command(); bad=ValueLossCaseCommand(new_uuid(),self.ids["case"],self.ctx,"MXN",(ValuationLineInput(self.ids["line1"],CostReferenceType.INVENTORY_AVERAGE,self.ids["ref1"],CostBasis.QUANTITY,3.0,Decimal("10")),))
        with self.assertRaises(LossInvariantError):self.svc.value(bad)
        bad_line=ValuationLineInput(new_uuid(),CostReferenceType.INVENTORY_AVERAGE,self.ids["ref1"],CostBasis.QUANTITY,Decimal("1"),Decimal("1"))
        with self.assertRaises(LossInvariantError):self.svc.value(ValueLossCaseCommand(new_uuid(),self.ids["case"],self.ctx,"MXN",(bad_line,)))
    def test_operation_is_idempotent(self):
        first=self.svc.value(self.command());replay=self.svc.value(self.command());self.assertEqual(first.entity_id,replay.entity_id);self.assertTrue(replay.replayed)
if __name__=="__main__":unittest.main()
