"""SQLite adapter for LOSS-18 valuation snapshots and cost provenance."""
import json
from contextlib import contextmanager
from datetime import datetime,timezone
from decimal import Decimal
from backend.domain.losses.exceptions import LossStateTransitionError
from backend.shared.ids import new_uuid
class LossValuationRepository:
    def __init__(self,connection):self._db=connection
    @contextmanager
    def transaction(self):
        self._db.execute("SAVEPOINT loss18_valuation")
        try:yield;self._db.execute("RELEASE SAVEPOINT loss18_valuation")
        except Exception:self._db.execute("ROLLBACK TO SAVEPOINT loss18_valuation");self._db.execute("RELEASE SAVEPOINT loss18_valuation");raise
    def find_processed(self,operation_id):
        row=self._db.execute("SELECT result_json FROM loss_processed_operations WHERE operation_id=?",(operation_id,)).fetchone();return json.loads(row[0]) if row else None
    def get_case(self,value):
        row=self._db.execute("SELECT id,branch_id,warehouse_id,status,currency_code,version,(SELECT COALESCE(SUM(CAST(recovered_value AS NUMERIC)),0) FROM loss_recoveries WHERE loss_case_id=loss_cases.id AND status='APPROVED') FROM loss_cases WHERE id=?",(value,)).fetchone()
        if not row:return None
        result=dict(zip(("id","branch_id","warehouse_id","status","currency_code","version","approved_recovery"),row));result["approved_recovery"]=Decimal(str(result["approved_recovery"] or "0"));result["line_ids"]={item[0] for item in self._db.execute("SELECT id FROM loss_lines WHERE loss_case_id=?",(value,))};return result
    def save_valuation(self,*,valuation_id,operation_id,case,valuation,actor_user_id,events):
        now=self._now();valuation_version=case["version"]+1
        self._db.execute("INSERT INTO loss_valuations (id,loss_case_id,operation_id,valuation_version,currency_code,gross_value,recovered_value,net_loss_value,valued_by_user_id,valued_at) VALUES (?,?,?,?,?,?,?,?,?,?)",(valuation_id,case["id"],operation_id,valuation_version,valuation.currency_code,str(valuation.gross_value),str(valuation.recovered_value),str(valuation.net_loss_value),actor_user_id,now))
        for line in valuation.lines:
            self._db.execute("INSERT INTO loss_cost_references (id,valuation_id,loss_line_id,reference_type,reference_id,cost_basis,basis_amount,unit_cost,gross_value) VALUES (?,?,?,?,?,?,?,?,?)",(new_uuid(),valuation_id,line.line_id,line.reference_type.value,line.reference_id,line.basis.value,str(line.basis_amount),str(line.unit_cost),str(line.gross_value)))
            self._db.execute("UPDATE loss_lines SET unit_cost=?,gross_value=?,recoverable_value=?,net_loss_value=? WHERE id=? AND loss_case_id=?",(str(line.unit_cost),str(line.gross_value),str(line.recovered_value),str(line.net_loss_value),line.line_id,case["id"]))
        changed=self._db.execute("UPDATE loss_cases SET gross_value=?,recoverable_value=?,net_loss_value=?,updated_at=?,version=? WHERE id=? AND version=?",(str(valuation.gross_value),str(valuation.recovered_value),str(valuation.net_loss_value),now,valuation_version,case["id"],case["version"])).rowcount
        if changed!=1:raise LossStateTransitionError("El expediente cambió durante la valuación")
        for event in events:self._db.execute("INSERT INTO loss_outbox (id,event_id,event_name,aggregate_id,operation_id,correlation_id,payload_json,created_at) VALUES (?,?,?,?,?,?,?,?)",(new_uuid(),event["event_id"],event["event_name"],case["id"],operation_id,event["event_id"],json.dumps(event,sort_keys=True),now))
        result={"entity_id":valuation_id,"status":"VALUED","gross_value":str(valuation.gross_value),"recovered_value":str(valuation.recovered_value),"net_loss_value":str(valuation.net_loss_value)};self._db.execute("INSERT INTO loss_processed_operations (operation_id,operation_type,result_entity_id,result_json,processed_at) VALUES (?,?,?,?,?)",(operation_id,"VALUE_LOSS_CASE",valuation_id,json.dumps(result,sort_keys=True),now))
    @staticmethod
    def _now():return datetime.now(timezone.utc).isoformat()
