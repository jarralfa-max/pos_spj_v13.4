"""Persistence and query adapters for LOSS-16 root-cause analysis."""

import json
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class LossRootCauseRepository:
    def __init__(self, connection): self._db = connection
    @contextmanager
    def transaction(self):
        self._db.execute("SAVEPOINT loss16_root_cause")
        try:
            yield; self._db.execute("RELEASE SAVEPOINT loss16_root_cause")
        except Exception:
            self._db.execute("ROLLBACK TO SAVEPOINT loss16_root_cause")
            self._db.execute("RELEASE SAVEPOINT loss16_root_cause"); raise
    def find_processed(self, operation_id):
        row=self._db.execute("SELECT result_json FROM loss_processed_operations WHERE operation_id=?",(operation_id,)).fetchone()
        return json.loads(row[0]) if row else None
    def get_investigation(self, investigation_id):
        row=self._db.execute("SELECT i.id,i.loss_case_id,c.branch_id,c.warehouse_id,i.status FROM loss_investigations i JOIN loss_cases c ON c.id=i.loss_case_id WHERE i.id=?",(investigation_id,)).fetchone()
        return dict(zip(("id","loss_case_id","branch_id","warehouse_id","status"),row)) if row else None
    def get_active_catalog_entries(self, identifiers):
        if not identifiers: return set()
        placeholders=",".join("?" for _ in identifiers)
        return {row[0] for row in self._db.execute(f"SELECT id FROM loss_root_cause_catalog WHERE active=1 AND id IN ({placeholders})",tuple(identifiers))}
    def save_analysis(self, *, analysis_id, operation_id, investigation, analysis, actor_user_id, event):
        now=self._now()
        self._db.execute("INSERT INTO loss_root_cause_analyses (id,investigation_id,operation_id,method,summary,recorded_by_user_id,recorded_at) VALUES (?,?,?,?,?,?,?)",(analysis_id,investigation["id"],operation_id,analysis.method.value,analysis.summary,actor_user_id,now))
        causes=((analysis.primary_cause,"PRIMARY"),*((item,"CONTRIBUTING") for item in analysis.contributing_causes))
        for cause,role in causes:
            self._db.execute("INSERT INTO loss_root_causes (id,analysis_id,catalog_entry_id,role,rationale,recorded_by_user_id,recorded_at) VALUES (?,?,?,?,?,?,?)",(new_uuid(),analysis_id,cause.catalog_entry_id,role,cause.rationale,actor_user_id,now))
        result={"entity_id":analysis_id,"status":"RECORDED"}
        self._db.execute("INSERT INTO loss_outbox (id,event_id,event_name,aggregate_id,operation_id,correlation_id,payload_json,created_at) VALUES (?,?,?,?,?,?,?,?)",(new_uuid(),event["event_id"],event["event_name"],investigation["loss_case_id"],operation_id,event["event_id"],json.dumps(event,sort_keys=True),now))
        self._db.execute("INSERT INTO loss_processed_operations (operation_id,operation_type,result_entity_id,result_json,processed_at) VALUES (?,?,?,?,?)",(operation_id,"RECORD_ROOT_CAUSE_ANALYSIS",analysis_id,json.dumps(result,sort_keys=True),now))
    @staticmethod
    def _now(): return datetime.now(timezone.utc).isoformat()


class LossRootCauseQueryRepository:
    def __init__(self, connection): self._db=connection
    def search_catalog(self, query, limit=25):
        term=f"%{str(query or '').strip()}%"
        return self._db.execute("SELECT id,display_name,category FROM loss_root_cause_catalog WHERE active=1 AND (display_name LIKE ? OR code LIKE ?) ORDER BY display_name LIMIT ?",(term,term,limit)).fetchall()
    def search_open_investigations(self, branch_id, query, limit=25):
        term=f"%{str(query or '').strip()}%"
        return self._db.execute("SELECT i.id,'Investigación '||substr(i.id,1,8),i.status FROM loss_investigations i JOIN loss_cases c ON c.id=i.loss_case_id WHERE c.branch_id=? AND i.status IN ('OPEN','IN_PROGRESS') AND (i.id LIKE ? OR i.opening_reason LIKE ?) AND NOT EXISTS (SELECT 1 FROM loss_root_cause_analyses a WHERE a.investigation_id=i.id) ORDER BY i.due_at,i.opened_at LIMIT ?",(branch_id,term,term,limit)).fetchall()
