"""LOSS-16 canonical root-cause analysis service."""

from dataclasses import dataclass

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.permissions import LossPermissions
from backend.domain.losses.events import LossEvents, build_loss_event
from backend.domain.losses.exceptions import LossInvariantError
from backend.domain.losses.root_cause import RootCauseMethod, RootCausePolicy
from backend.shared.ids import new_uuid, validate_uuidv7


@dataclass(frozen=True, slots=True)
class RootCauseInput:
    catalog_entry_id: str
    rationale: str


@dataclass(frozen=True, slots=True)
class RecordRootCauseAnalysisCommand:
    operation_id: str
    investigation_id: str
    context: LossExecutionContext
    method: RootCauseMethod
    summary: str
    primary_cause: RootCauseInput
    contributing_causes: tuple[RootCauseInput, ...] = ()


@dataclass(frozen=True, slots=True)
class RootCauseResult:
    entity_id: str
    status: str
    replayed: bool = False


class LossRootCauseService:
    def __init__(self, repository, authorization, policy=None):
        self._repository, self._authorization = repository, authorization
        self._policy = policy or RootCausePolicy()

    def record(self, command: RecordRootCauseAnalysisCommand) -> RootCauseResult:
        validate_uuidv7(command.operation_id); validate_uuidv7(command.investigation_id)
        replay = self._repository.find_processed(command.operation_id)
        if replay: return RootCauseResult(replay["entity_id"],replay["status"],True)
        actor = command.context.actor_user_id
        self._authorization.require(actor,LossPermissions.MANAGE_ROOT_CAUSE)
        investigation = self._repository.get_investigation(command.investigation_id)
        if not investigation: raise LossInvariantError("Investigación no encontrada")
        command.context.enforce_branch(investigation["branch_id"])
        command.context.enforce_warehouse(investigation["warehouse_id"])
        if investigation["status"] not in ("OPEN","IN_PROGRESS"):
            raise LossInvariantError("La investigación no admite análisis de causa raíz")
        analysis = self._policy.build(method=command.method,summary=command.summary,
            primary_cause=command.primary_cause,
            contributing_causes=command.contributing_causes)
        catalog_ids = {analysis.primary_cause.catalog_entry_id,
                       *(item.catalog_entry_id for item in analysis.contributing_causes)}
        for catalog_id in catalog_ids: validate_uuidv7(catalog_id)
        if self._repository.get_active_catalog_entries(catalog_ids) != catalog_ids:
            raise LossInvariantError("Una o más causas de catálogo no están activas")
        analysis_id = new_uuid()
        event = build_loss_event(LossEvents.LOSS_ROOT_CAUSE_RECORDED,
            operation_id=command.operation_id,entity_id=analysis_id,
            branch_id=investigation["branch_id"],warehouse_id=investigation["warehouse_id"],
            user_id=actor,loss_case_id=investigation["loss_case_id"],
            investigation_id=command.investigation_id,method=analysis.method.value,
            contributing_count=len(analysis.contributing_causes))
        with self._repository.transaction():
            self._repository.save_analysis(analysis_id=analysis_id,
                operation_id=command.operation_id,investigation=investigation,
                analysis=analysis,actor_user_id=actor,event=event)
        return RootCauseResult(analysis_id,"RECORDED")
