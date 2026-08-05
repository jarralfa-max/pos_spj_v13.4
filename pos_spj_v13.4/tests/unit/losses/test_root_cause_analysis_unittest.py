import unittest
from contextlib import nullcontext

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.root_cause import (
    LossRootCauseService, RecordRootCauseAnalysisCommand, RootCauseInput,
)
from backend.domain.losses.exceptions import LossInvariantError
from backend.domain.losses.root_cause import RootCauseMethod
from backend.shared.ids import new_uuid


class Authorization:
    def require(self, _actor, _permission): pass


class Repository:
    def __init__(self, ids): self.ids, self.processed, self.saved = ids, {}, None
    def transaction(self): return nullcontext()
    def find_processed(self, op): return self.processed.get(op)
    def get_investigation(self, value):
        return {"id": value,"loss_case_id":self.ids["case"],"branch_id":self.ids["branch"],
                "warehouse_id":self.ids["warehouse"],"status":"IN_PROGRESS"}
    def get_active_catalog_entries(self, values): return set(values)
    def save_analysis(self, **kw):
        self.saved = kw
        self.processed[kw["operation_id"]] = {"entity_id":kw["analysis_id"],"status":"RECORDED"}


class RootCauseAnalysisTest(unittest.TestCase):
    def setUp(self):
        names = ("case","branch","warehouse","actor","investigation","primary","contributor","operation")
        self.ids = {name:new_uuid() for name in names}; self.repo = Repository(self.ids)
        self.service = LossRootCauseService(self.repo, Authorization())
        self.context = LossExecutionContext(self.ids["actor"],self.ids["branch"],
            frozenset(),frozenset({self.ids["warehouse"]}))

    def command(self, contributors=None):
        return RecordRootCauseAnalysisCommand(self.ids["operation"],self.ids["investigation"],
            self.context,RootCauseMethod.FIVE_WHYS,"Análisis completo",
            RootCauseInput(self.ids["primary"],"Incumplimiento del proceso"),
            tuple(contributors if contributors is not None else
                  (RootCauseInput(self.ids["contributor"],"Capacitación insuficiente"),)))

    def test_records_one_primary_and_contributing_causes_idempotently(self):
        first = self.service.record(self.command()); replay = self.service.record(self.command())
        self.assertEqual(first.status,"RECORDED"); self.assertTrue(replay.replayed)
        self.assertEqual(self.repo.saved["analysis"].method,RootCauseMethod.FIVE_WHYS)
        self.assertEqual(len(self.repo.saved["analysis"].contributing_causes),1)

    def test_primary_cannot_repeat_as_contributor(self):
        with self.assertRaises(LossInvariantError):
            self.service.record(self.command((RootCauseInput(self.ids["primary"],"Duplicada"),)))

    def test_catalog_entries_must_be_active_and_investigation_open(self):
        self.repo.get_active_catalog_entries = lambda _values: {self.ids["primary"]}
        with self.assertRaises(LossInvariantError): self.service.record(self.command())


if __name__ == "__main__": unittest.main()
