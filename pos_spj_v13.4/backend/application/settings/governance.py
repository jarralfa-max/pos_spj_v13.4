"""Gobierno de configuración: el ÚNICO camino para cambiar un parámetro.

`GovernedSettingsWriter` lo usan las pantallas de ajustes de cada contexto
(Fidelidad, Cárnico, Precios…). El contexto autoriza con su propio permiso —es
dueño del significado del parámetro— y el escritor versiona y audita dentro de
su transacción. Configuración NO tiene una pantalla para estos parámetros:
cada uno se edita sólo en su módulo (decisión del usuario, 2026-10-04: dos
pantallas para lo mismo se contradicen). Un parámetro que exigiera aprobación
no se puede cambiar por aquí.

Reglas (todas del dominio, aquí sólo se orquestan):
- No se modifica un valor activo: cada cambio es una versión nueva (§10).
- Un solo cambio abierto por (parámetro, ámbito).
- Crítico (`approval_required`): quien propone no aprueba y quien aprueba no
  activa (§59).
- Activar expira la versión anterior del mismo ámbito.
- Cada transición deja auditoría en la misma transacción (§63).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Mapping

from backend.application.settings.catalog import CATALOG_BY_KEY
from backend.application.settings.value_coercion import coerce_value, display_value
from backend.domain.settings.entities.configuration_value import ConfigurationValue
from backend.domain.settings.enums import ConfigurationValueStatus, ScopeType
from backend.domain.settings.events import ConfigurationEvents, build_event_payload
from backend.domain.settings.exceptions import (
    ConfigurationActivationNotAllowedError,
    ConfigurationApprovalRequiredError,
    ConfigurationDefinitionNotFoundError,
    ConfigurationInvalidValueError,
    ConfigurationRollbackNotAllowedError,
    ConfigurationValueNotFoundError,
)
from backend.domain.settings.policies.configuration_activation_policy import assert_can_activate
from backend.domain.settings.policies.configuration_approval_policy import assert_can_approve
from backend.domain.settings.policies.configuration_inheritance_policy import (
    assert_override_allowed,
    assert_scope_allowed,
)
from backend.domain.settings.policies.configuration_rollback_policy import build_rollback_draft
from backend.domain.settings.policies.configuration_validation_policy import (
    validate_against_definition,
)
from backend.domain.settings.value_objects.configuration_scope import ConfigurationScope
from backend.domain.settings.value_objects.effective_period import EffectivePeriod
from backend.infrastructure.db.repositories.settings.configuracion_security_repositories import (
    ConfiguracionAuditLogRepository,
)
from backend.infrastructure.db.repositories.settings.configuration_definition_repository import (
    SqliteConfigurationDefinitionRepository,
)
from backend.infrastructure.db.repositories.settings.configuration_value_repository import (
    SqliteConfigurationValueRepository,
)
logger = logging.getLogger("spj.settings.governance")

_OPEN = (ConfigurationValueStatus.DRAFT, ConfigurationValueStatus.PENDING_APPROVAL,
         ConfigurationValueStatus.APPROVED, ConfigurationValueStatus.SCHEDULED)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _GovernanceCore:
    """Orquestación sin autorización ni commit; la usan las dos entradas."""

    def __init__(self, connection) -> None:
        self._conn = connection
        self.definitions = SqliteConfigurationDefinitionRepository(connection)
        self.values = SqliteConfigurationValueRepository(connection)
        self._audit = ConfiguracionAuditLogRepository(connection)
        self.events: list[tuple[str, dict]] = []

    # ── lookups ─────────────────────────────────────────────────────────
    def definition(self, key: str):
        if key not in CATALOG_BY_KEY:
            raise ConfigurationDefinitionNotFoundError(
                f"{key!r} no está en el catálogo de parámetros gobernados")
        definition = self.definitions.get_by_key(key)
        if definition is None:
            raise ConfigurationDefinitionNotFoundError(
                f"La definición de {key!r} no está sincronizada en esta base")
        return definition

    def definition_by_id(self, definition_id: str):
        definition = self.definitions.get(definition_id)
        if definition is None:
            raise ConfigurationDefinitionNotFoundError(f"Definición {definition_id} inexistente")
        return definition

    def value(self, value_id: str) -> ConfigurationValue:
        value = self.values.get(value_id)
        if value is None:
            raise ConfigurationValueNotFoundError(f"Cambio de configuración {value_id} inexistente")
        return value

    @staticmethod
    def scope(definition, scope_type: ScopeType | str, scope_id: str | None) -> ConfigurationScope:
        scope_type = ScopeType(scope_type)
        assert_scope_allowed(definition, scope_type)
        assert_override_allowed(definition, scope_type)
        return ConfigurationScope.create(scope_type, scope_id or None)

    @staticmethod
    def typed(definition, raw: object) -> object:
        value = coerce_value(definition.value_type, raw)
        validate_against_definition(definition, value)
        return value

    def active_at(self, definition, scope: ConfigurationScope) -> ConfigurationValue | None:
        for candidate in self.values.list_lineage(definition.id, scope):
            if candidate.status is ConfigurationValueStatus.ACTIVE:
                return candidate
        return None

    def open_change(self, definition, scope: ConfigurationScope) -> ConfigurationValue | None:
        latest = self.values.latest_in_lineage(definition.id, scope)
        return latest if latest is not None and latest.status in _OPEN else None

    # ── transiciones ────────────────────────────────────────────────────
    def new_version(self, definition, scope, value, *, actor_user_id: str, reason: str,
                    operation_id: str, row_operation_id: str | None = None) -> ConfigurationValue:
        pending = self.open_change(definition, scope)
        if pending is not None:
            raise ConfigurationActivationNotAllowedError(
                f"{definition.label}: ya hay un cambio abierto ({pending.status.value}, "
                f"v{pending.version.value}) en este ámbito; apruébalo, recházalo o cancélalo.")
        current = self.active_at(definition, scope)
        if current is not None and current.value == value:
            raise ConfigurationInvalidValueError(f"{definition.label}: ese ya es el valor vigente")
        latest = self.values.latest_in_lineage(definition.id, scope)
        period = EffectivePeriod.create(_now())
        if latest is None:
            draft = ConfigurationValue.create(
                definition_id=definition.id, scope=scope, value=value, effective_period=period,
                created_by_user_id=actor_user_id, reason=reason or None)
        else:
            draft = latest.create_next_version(
                value=value, effective_period=period, created_by_user_id=actor_user_id,
                reason=reason or None)
        self.values.save(draft, operation_id=row_operation_id)
        self._record(definition, draft, "CREAR", operation_id, actor_user_id, after=draft,
                     reason=reason)
        self._event(ConfigurationEvents.VALUE_CREATED, definition, draft, operation_id,
                    actor_user_id)
        return draft

    def submit(self, definition, value, *, actor_user_id, operation_id) -> None:
        value.submit_for_approval()
        self.values.save(value, operation_id=None)
        self._record(definition, value, "ENVIAR_A_APROBACION", operation_id, actor_user_id)
        self._event(ConfigurationEvents.CHANGE_SUBMITTED, definition, value, operation_id,
                    actor_user_id)

    def approve(self, definition, value, *, actor_user_id, operation_id) -> None:
        assert_can_approve(value, approver_user_id=actor_user_id)
        value.approve(actor_user_id)
        self.values.save(value, operation_id=None)
        self._record(definition, value, "APROBAR", operation_id, actor_user_id)
        self._event(ConfigurationEvents.APPROVED, definition, value, operation_id, actor_user_id)

    def auto_approve(self, definition, value, *, actor_user_id, operation_id) -> None:
        if definition.approval_required:
            raise ConfigurationApprovalRequiredError(
                f"{definition.label} exige aprobación de otra persona")
        value.auto_approve(actor_user_id)
        self.values.save(value, operation_id=None)

    def reject(self, definition, value, *, actor_user_id, reason, operation_id) -> None:
        value.reject(reason)
        self.values.save(value, operation_id=None)
        self._record(definition, value, "RECHAZAR", operation_id, actor_user_id, reason=reason)
        self._event(ConfigurationEvents.REJECTED, definition, value, operation_id, actor_user_id)

    def cancel(self, definition, value, *, actor_user_id, operation_id) -> None:
        value.cancel()
        self.values.save(value, operation_id=None)
        self._record(definition, value, "CANCELAR", operation_id, actor_user_id)
        self._event(ConfigurationEvents.CANCELLED, definition, value, operation_id, actor_user_id)

    def activate(self, definition, value, *, actor_user_id, operation_id) -> None:
        assert_can_activate(definition, value, activator_user_id=actor_user_id)
        moment = _now()
        previous = self.active_at(definition, value.scope)
        value.activate(actor_user_id, at=moment)
        if previous is not None and previous.id != value.id:
            self._expire(previous, moment)
        self.values.save(value, operation_id=None)
        self._record(definition, value, "ACTIVAR", operation_id, actor_user_id,
                     before=previous, after=value)
        self._event(ConfigurationEvents.ACTIVATED, definition, value, operation_id, actor_user_id)

    def rollback(self, definition, scope, *, actor_user_id, reason, operation_id) -> ConfigurationValue | None:
        current = self.active_at(definition, scope)
        if current is None:
            raise ConfigurationRollbackNotAllowedError(
                f"{definition.label}: no hay un valor activo en este ámbito que revertir")
        if self.open_change(definition, scope) is not None:
            raise ConfigurationRollbackNotAllowedError(
                f"{definition.label}: hay un cambio abierto en este ámbito; resuélvelo antes")
        target = next((v for v in self.values.list_lineage(definition.id, scope)
                       if v.status is ConfigurationValueStatus.EXPIRED
                       and v.version.value < current.version.value), None)
        if target is None:
            # Sin versión anterior: se retira el valor y rige el heredado.
            current.mark_rolled_back()
            self.values.save(current, operation_id=None)
            self._record(definition, current, "REVERTIR", operation_id, actor_user_id,
                         before=current, reason=reason)
            self._event(ConfigurationEvents.ROLLED_BACK, definition, current, operation_id,
                        actor_user_id)
            return None
        if definition.approval_required:
            # El valor actual sigue rigiendo hasta que la reversión se active:
            # un parámetro crítico no puede caer al de omisión mientras espera.
            draft = self.new_version(
                definition, scope, target.value, actor_user_id=actor_user_id,
                reason=f"Reversión a v{target.version.value}: {reason}", operation_id=operation_id)
            self.submit(definition, draft, actor_user_id=actor_user_id, operation_id=operation_id)
            return draft
        draft = build_rollback_draft(
            current, target, effective_period=EffectivePeriod.create(_now()),
            requested_by_user_id=actor_user_id, reason=reason)
        self.values.save(current, operation_id=None)
        self.values.save(draft, operation_id=None)
        draft.auto_approve(actor_user_id)
        draft.activate(actor_user_id, at=_now())
        self.values.save(draft, operation_id=None)
        self._record(definition, draft, "REVERTIR", operation_id, actor_user_id,
                     before=current, after=draft, reason=reason)
        self._event(ConfigurationEvents.ROLLED_BACK, definition, draft, operation_id, actor_user_id)
        return draft

    # ── apoyo ───────────────────────────────────────────────────────────
    def _expire(self, value: ConfigurationValue, moment: datetime) -> None:
        start = value.effective_period.effective_from
        end = moment if moment > start else start + timedelta(microseconds=1)
        value.effective_period = EffectivePeriod.create(start, end)
        value.expire(at=end)
        self.values.save(value, operation_id=None)

    def _record(self, definition, value, action, operation_id, actor_user_id, *,
                before=None, after=None, reason: str = "") -> None:
        self._audit.record(
            entity_type="configuration_value", entity_id=value.id, action=action,
            user_id=actor_user_id or None, operation_id=operation_id,
            before_json=self._snapshot(definition, before),
            after_json=self._snapshot(definition, after if after is not None else value),
            reason=reason or None, source_module="settings")

    @staticmethod
    def _snapshot(definition, value) -> str | None:
        if value is None:
            return None
        return json.dumps({
            "key": definition.key.value, "scope_type": value.scope.scope_type.value,
            "scope_id": value.scope.scope_id, "version": value.version.value,
            "status": value.status.value,
            "value": display_value(definition.value_type, value.value,
                                   sensitive=definition.sensitive),
        }, ensure_ascii=False)

    def _event(self, name, definition, value, operation_id, actor_user_id) -> None:
        self.events.append((name, build_event_payload(
            name, operation_id=operation_id, definition_id=definition.id, value_id=value.id,
            user_id=actor_user_id, key=definition.key.value,
            scope_type=value.scope.scope_type.value, scope_id=value.scope.scope_id,
            version=value.version.value)))

    def publish(self) -> None:
        """Después del commit (§61). Un suscriptor que falla no deshace nada."""
        from backend.shared.events.application_bus import get_bus

        events, self.events = self.events, []
        for name, payload in events:
            get_bus().publish(name, payload)


class GovernedSettingsWriter:
    """Escritura de parámetros desde la pantalla de ajustes de un contexto.

    `stage()` escribe DENTRO de la transacción del llamador (no confirma);
    `publish()` se llama después de que el llamador confirme.
    """

    def __init__(self, connection) -> None:
        self._core = _GovernanceCore(connection)

    def stage(self, changes: Mapping[str, object], *, actor_user_id: str, reason: str,
              operation_id: str, scope_type: ScopeType = ScopeType.GLOBAL,
              scope_id: str | None = None) -> tuple[str, ...]:
        """Activa cada valor que cambió. Devuelve las claves que cambiaron;
        repetir la misma operación no crea versiones nuevas."""
        changed = []
        for key, raw in changes.items():
            definition = self._core.definition(key)
            scope = self._core.scope(definition, scope_type, scope_id)
            value = self._core.typed(definition, raw)
            current = self._core.active_at(definition, scope)
            if current is not None and current.value == value:
                continue
            if current is None and scope.scope_type is ScopeType.GLOBAL \
                    and definition.default_value == value:
                continue
            if definition.approval_required:
                raise ConfigurationApprovalRequiredError(
                    f"{definition.label} exige aprobación: cámbialo en Configuración → Parámetros")
            draft = self._core.new_version(
                definition, scope, value, actor_user_id=actor_user_id, reason=reason,
                operation_id=operation_id)
            self._core.auto_approve(definition, draft, actor_user_id=actor_user_id,
                                    operation_id=operation_id)
            self._core.activate(definition, draft, actor_user_id=actor_user_id,
                                operation_id=operation_id)
            changed.append(key)
        return tuple(changed)

    def publish(self) -> None:
        self._core.publish()



__all__ = ["GovernedSettingsWriter"]
