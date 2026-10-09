"""CRMReferenceQueryService (CRM-43) — lo que toda pantalla de CRM necesita
para no mostrar identificadores: usuarios asignables, nombres de clientes y
usuarios, sucursales y el catálogo de etapas del pipeline.

Sin permiso propio: sólo lo consulta quien ya pasó la puerta del módulo
(``CLIENTES.acceso``), y no expone datos sensibles (ni teléfonos, ni correos,
ni importes).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.customers.permissions import CustomerPermissions
from backend.domain.crm.entities.stage_definition import CRMStageDefinition
from backend.infrastructure.db.repositories.crm.crm_reference_repository import (
    CRMReferenceRepository,
)
from backend.infrastructure.db.repositories.crm.stage_definition_repository import (
    CRMStageDefinitionRepository,
)


@dataclass(frozen=True)
class UserOption:
    user_id: str
    name: str
    branch_id: str | None


class CRMReferenceQueryService:
    def __init__(self, connection, authorization=None) -> None:
        self._repo = CRMReferenceRepository(connection)
        self._stages = CRMStageDefinitionRepository(connection)
        self._auth = authorization

    def _require_access(self, actor_user_id: str) -> None:
        if self._auth is not None:
            self._auth.require(actor_user_id, CustomerPermissions.ACCESS)

    def assignable_users(self, *, actor_user_id: str) -> list[UserOption]:
        self._require_access(actor_user_id)
        return [UserOption(r["id"], r["name"], r["sucursal_id"])
                for r in self._repo.active_users()]

    def user_names(self, user_ids, *, actor_user_id: str) -> dict[str, str]:
        self._require_access(actor_user_id)
        return self._repo.user_names(tuple(user_ids))

    def customer_names(self, customer_ids, *, actor_user_id: str) -> dict[str, str]:
        self._require_access(actor_user_id)
        return self._repo.customer_names(tuple(customer_ids))

    def related_names(self, pairs, *, actor_user_id: str) -> dict[tuple[str, str], str]:
        """``{(tipo, id): nombre}`` para registros relacionados de actividades,
        tareas y notas (cliente, prospecto, oportunidad o caso)."""
        self._require_access(actor_user_id)
        by_type: dict[str, list[str]] = {}
        for entity_type, entity_id in pairs:
            by_type.setdefault(str(entity_type), []).append(entity_id)
        names: dict[tuple[str, str], str] = {}
        for entity_type, ids in by_type.items():
            for entity_id, name in self._repo.related_names(entity_type, tuple(ids)).items():
                names[(entity_type, entity_id)] = name
        return names

    def branch_names(self, *, actor_user_id: str) -> dict[str, str]:
        self._require_access(actor_user_id)
        return self._repo.branch_names()

    def stages(self, *, actor_user_id: str, include_inactive: bool = False
               ) -> list[CRMStageDefinition]:
        self._require_access(actor_user_id)
        if include_inactive:
            return self._stages.list_all_ordered()
        return self._stages.list_active_ordered()
