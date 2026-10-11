"""WorkItemVisibility — quién ve actividades, tareas y notas (auditoría CRM F03).

Antes bastaba ``CRM.tareas.ver`` / ``CRM.actividades.ver`` para leer las de
CUALQUIER usuario o registro: un cajero pedía las tareas de otro por su id y
las obtenía, aunque su bandeja no se las mostrara. Ahora:

* lo de otra persona (``list_assigned_to(otro)``, la agenda de otro) exige el
  permiso de supervisión de ese tipo (``…reasignar``, gerente/dueño);
* lo de un registro (``list_for_related_entity``) exige que el registro esté en
  el alcance del actor — el mismo con que lo ve en su bandeja;
* un elemento suelto (``get``) se ve si es propio (asignado o creado), si el
  actor supervisa, o si su registro está en su alcance.

``record_visible(actor, tipo, id)`` lo inyecta la raíz de composición (usa
``CRMRecordScopeGuard``). Sin él, sólo se aplican las dos reglas por persona.
"""

from __future__ import annotations

from collections.abc import Callable

from backend.domain.crm.exceptions import CRMScopeError

RecordVisible = Callable[[str, str, str], bool]


def _kind(value) -> str:
    return str(getattr(value, "value", value) or "")


class WorkItemVisibility:
    def __init__(self, authorization, supervisor_permission: str,
                 record_visible: RecordVisible | None = None) -> None:
        self._auth = authorization
        self._supervisor = supervisor_permission
        self._record_visible = record_visible

    def supervises(self, actor_user_id: str) -> bool:
        return self._auth.has_permission(actor_user_id, self._supervisor)

    def require_user(self, actor_user_id: str, user_id: str) -> None:
        if user_id and user_id != actor_user_id:
            self._auth.require(actor_user_id, self._supervisor)

    def require_record(self, actor_user_id: str, kind, record_id: str) -> None:
        if self._record_visible is not None and not self._record_visible(
                actor_user_id, _kind(kind), record_id):
            raise CRMScopeError("Ese registro está fuera de tu alcance.")

    def can_see_item(self, actor_user_id: str, item, *, owners: tuple[str | None, ...]) -> bool:
        if actor_user_id in owners or self.supervises(actor_user_id):
            return True
        if self._record_visible is None:
            return False
        return self._record_visible(actor_user_id, _kind(item.related_entity_type),
                                    item.related_entity_id)
