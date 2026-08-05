"""Portable read-only SQL adapter for LOSS-20 analytics."""
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
class LossAnalyticsRepository:
    def __init__(self,connection):self._db=connection
    @staticmethod
    def _where():return "c.branch_id=? AND c.occurred_at>=? AND c.occurred_at<?"
    @staticmethod
    def _args(branch_id,start_at,end_at):return (branch_id,start_at,end_at)
    def summary(self,*,branch_id,start_at,end_at):
        args=self._args(branch_id,start_at,end_at);row=self._db.execute(f"SELECT COUNT(*),COALESCE(SUM(CAST(c.gross_value AS NUMERIC)),0),COALESCE(SUM(CAST(c.recoverable_value AS NUMERIC)),0),COALESCE(SUM(CAST(c.net_loss_value AS NUMERIC)),0) FROM loss_cases c WHERE {self._where()}",args).fetchone();investigations=self._db.execute(f"SELECT COUNT(*) FROM loss_investigations i JOIN loss_cases c ON c.id=i.loss_case_id WHERE {self._where()} AND i.status IN ('OPEN','IN_PROGRESS')",args).fetchone()[0];overdue=self._db.execute(f"SELECT COUNT(*) FROM loss_corrective_actions a JOIN loss_investigations i ON i.id=a.investigation_id JOIN loss_cases c ON c.id=i.loss_case_id WHERE {self._where()} AND a.status IN ('OPEN','IN_PROGRESS','PENDING_VERIFICATION') AND a.due_at<?",(*args,end_at)).fetchone()[0];return {"case_count":row[0],"gross_value":row[1],"recovered_value":row[2],"net_loss_value":row[3],"open_investigations":investigations,"overdue_actions":overdue}
    def status_distribution(self,*,branch_id,start_at,end_at):return self._db.execute(f"SELECT c.status,COUNT(*) FROM loss_cases c WHERE {self._where()} GROUP BY c.status ORDER BY COUNT(*) DESC,c.status",self._args(branch_id,start_at,end_at)).fetchall()
    def pareto(self,*,branch_id,start_at,end_at):return self._db.execute(f"SELECT cl.code,cl.display_name,COALESCE(SUM(CAST(c.net_loss_value AS NUMERIC)),0) FROM loss_cases c JOIN loss_classifications cl ON cl.id=c.classification_id WHERE {self._where()} GROUP BY cl.code,cl.display_name ORDER BY SUM(CAST(c.net_loss_value AS NUMERIC)) DESC,cl.code",self._args(branch_id,start_at,end_at)).fetchall()
    def trend(self,*,branch_id,start_at,end_at):
        totals=defaultdict(lambda:Decimal("0"))
        for occurred,value in self._db.execute(f"SELECT c.occurred_at,c.net_loss_value FROM loss_cases c WHERE {self._where()} ORDER BY c.occurred_at",self._args(branch_id,start_at,end_at)):totals[datetime.fromisoformat(occurred).date().isoformat()]+=Decimal(str(value))
        return tuple(sorted(totals.items()))
    def export_rows(self,*,branch_id,start_at,end_at):return self._db.execute(f"SELECT c.id,c.occurred_at,cl.display_name,c.status,c.gross_value,c.recoverable_value,c.net_loss_value,c.currency_code FROM loss_cases c JOIN loss_classifications cl ON cl.id=c.classification_id WHERE {self._where()} ORDER BY c.occurred_at,c.id",self._args(branch_id,start_at,end_at)).fetchall()
