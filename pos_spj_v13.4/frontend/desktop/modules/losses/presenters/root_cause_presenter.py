"""Presentation adapter for the LOSS-16 root-cause page."""

from backend.application.losses.root_cause import RecordRootCauseAnalysisCommand, RootCauseInput
from backend.domain.losses.root_cause import RootCauseMethod
from backend.shared.ids import new_uuid
from frontend.desktop.components.search_selector import SearchOption


class RootCausePresenter:
    def __init__(self, query_service, application_service, context_provider):
        self._query=query_service; self._service=application_service
        self._context_provider=context_provider
    def search_investigations(self, query):
        context=self._context_provider()
        return [SearchOption(str(row[0]),str(row[1]),str(row[2]))
                for row in self._query.search_open_investigations(context.active_branch_id,query)]
    def search_catalog(self, query):
        return [SearchOption(str(row[0]),str(row[1]),str(row[2]))
                for row in self._query.search_catalog(query)]
    @staticmethod
    def methods():
        labels={RootCauseMethod.FIVE_WHYS:"5 porqués",RootCauseMethod.FISHBONE:"Ishikawa",
                RootCauseMethod.PARETO:"Pareto",RootCauseMethod.FAULT_TREE:"Árbol de fallas",
                RootCauseMethod.DIRECT_OBSERVATION:"Observación directa"}
        return tuple((item,labels[item]) for item in RootCauseMethod)
    def record(self, *, investigation_id, method, summary, primary, contributors):
        return self._service.record(RecordRootCauseAnalysisCommand(new_uuid(),investigation_id,
            self._context_provider(),RootCauseMethod(method),summary,
            RootCauseInput(primary[0],primary[1]),
            tuple(RootCauseInput(item[0],item[1]) for item in contributors)))
