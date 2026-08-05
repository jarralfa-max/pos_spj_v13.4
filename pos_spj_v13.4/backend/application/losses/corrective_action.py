"""LOSS-17 canonical corrective-action application service."""
from dataclasses import dataclass
from datetime import datetime
from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.permissions import LossPermissions
from backend.domain.losses.corrective_action import CorrectiveActionPolicy,EffectivenessDecision
from backend.domain.losses.events import LossEvents,build_loss_event
from backend.domain.losses.exceptions import LossInvariantError
from backend.shared.ids import new_uuid,validate_uuidv7
@dataclass(frozen=True,slots=True)
class CreateCorrectiveActionCommand:
    operation_id:str; investigation_id:str; context:LossExecutionContext
    title:str; description:str; owner_user_id:str; due_at:datetime
@dataclass(frozen=True,slots=True)
class SubmitCorrectiveActionCommand:
    operation_id:str; action_id:str; context:LossExecutionContext
    completion_notes:str; evidence_uri:str; evidence_checksum:str
@dataclass(frozen=True,slots=True)
class VerifyCorrectiveActionCommand:
    operation_id:str; action_id:str; context:LossExecutionContext
    decision:EffectivenessDecision; effectiveness_notes:str
@dataclass(frozen=True,slots=True)
class CorrectiveActionResult:
    entity_id:str; status:str; replayed:bool=False
class LossCorrectiveActionService:
    def __init__(self,repository,authorization,policy=None): self._repository=repository; self._authorization=authorization; self._policy=policy or CorrectiveActionPolicy()
    def create(self,command):
        validate_uuidv7(command.operation_id); validate_uuidv7(command.investigation_id); validate_uuidv7(command.owner_user_id)
        replay=self._replay(command.operation_id)
        if replay:return replay
        actor=command.context.actor_user_id; self._authorization.require(actor,LossPermissions.CREATE_CORRECTIVE_ACTION)
        investigation=self._repository.get_investigation(command.investigation_id)
        if not investigation: raise LossInvariantError("Investigación no encontrada")
        self._scope(investigation,command.context)
        if investigation["status"]!="CONCLUDED": raise LossInvariantError("La acción correctiva requiere una investigación concluida")
        self._policy.validate_create(title=command.title,description=command.description,owner_user_id=command.owner_user_id,due_at=command.due_at)
        action_id=new_uuid(); event=self._event(LossEvents.LOSS_CORRECTIVE_ACTION_CREATED,command.operation_id,action_id,investigation,actor,owner_user_id=command.owner_user_id,due_at=command.due_at.isoformat())
        with self._repository.transaction(): self._repository.save_created(action_id=action_id,operation_id=command.operation_id,investigation=investigation,title=command.title.strip(),description=command.description.strip(),owner_user_id=command.owner_user_id,due_at=command.due_at.isoformat(),actor_user_id=actor,event=event)
        return CorrectiveActionResult(action_id,"OPEN")
    def submit(self,command):
        validate_uuidv7(command.operation_id); validate_uuidv7(command.action_id)
        replay=self._replay(command.operation_id)
        if replay:return replay
        actor=command.context.actor_user_id; self._authorization.require(actor,LossPermissions.CREATE_CORRECTIVE_ACTION)
        action=self._action(command.action_id,command.context,"OPEN","IN_PROGRESS")
        if action["owner_user_id"]!=actor: raise LossInvariantError("Sólo el responsable puede enviar la acción a verificación")
        self._policy.validate_submission(notes=command.completion_notes,evidence_uri=command.evidence_uri,checksum=command.evidence_checksum)
        event=self._event(LossEvents.LOSS_CORRECTIVE_ACTION_SUBMITTED,command.operation_id,command.action_id,action,actor)
        with self._repository.transaction(): self._repository.submit(action_id=command.action_id,operation_id=command.operation_id,completion_notes=command.completion_notes.strip(),evidence_uri=command.evidence_uri.strip(),checksum=command.evidence_checksum.lower(),actor_user_id=actor,event=event,case=action)
        return CorrectiveActionResult(command.action_id,"PENDING_VERIFICATION")
    def verify(self,command):
        validate_uuidv7(command.operation_id); validate_uuidv7(command.action_id)
        replay=self._replay(command.operation_id)
        if replay:return replay
        actor=command.context.actor_user_id; self._authorization.require(actor,LossPermissions.VERIFY_CORRECTIVE_ACTION)
        action=self._action(command.action_id,command.context,"PENDING_VERIFICATION")
        if actor in {action["owner_user_id"],action["created_by_user_id"]}: raise LossInvariantError("El verificador debe ser independiente")
        self._policy.validate_verification(decision=command.decision,notes=command.effectiveness_notes)
        decision=EffectivenessDecision(command.decision); event=self._event(LossEvents.LOSS_CORRECTIVE_ACTION_VERIFIED,command.operation_id,command.action_id,action,actor,effectiveness=decision.value)
        with self._repository.transaction(): self._repository.verify(action_id=command.action_id,operation_id=command.operation_id,decision=decision,notes=command.effectiveness_notes.strip(),actor_user_id=actor,event=event,case=action)
        return CorrectiveActionResult(command.action_id,decision.value)
    def _action(self,value,context,*states):
        item=self._repository.get_action(value)
        if not item: raise LossInvariantError("Acción correctiva no encontrada")
        self._scope(item,context)
        if item["status"] not in states: raise LossInvariantError("Estado de acción correctiva inválido")
        return item
    @staticmethod
    def _scope(item,context): context.enforce_branch(item["branch_id"]); context.enforce_warehouse(item["warehouse_id"])
    def _replay(self,operation_id):
        row=self._repository.find_processed(operation_id); return CorrectiveActionResult(row["entity_id"],row["status"],True) if row else None
    @staticmethod
    def _event(name,operation_id,entity_id,item,actor,**payload): return build_loss_event(name,operation_id=operation_id,entity_id=entity_id,branch_id=item["branch_id"],warehouse_id=item["warehouse_id"],user_id=actor,loss_case_id=item["loss_case_id"],**payload)
