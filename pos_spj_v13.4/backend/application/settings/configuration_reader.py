"""ConfigurationReader — el valor efectivo de un parámetro gobernado.

La ÚNICA forma en que un contexto lee un parámetro del catálogo. Resuelve la
herencia (§7: valor específico → ámbito padre → empresa → global → omisión)
con `ConfigurationResolutionService` y devuelve el valor TIPADO junto con su
origen, para que la pantalla pueda decir de dónde sale (§68: "valor efectivo,
valor heredado, ámbito de origen, versión").

Sin caché: cada lectura es una consulta indexada a SQLite. Así no hay caché
eterna que invalidar (§55) y un valor recién activado se ve en la siguiente
lectura, en cualquier pantalla.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from backend.application.settings.catalog import CATALOG_BY_KEY
from backend.domain.settings.enums import ScopeType
from backend.domain.settings.exceptions import (
    ConfigurationDefinitionNotFoundError,
    ConfigurationDomainError,
)
from backend.domain.settings.services.configuration_resolution_service import (
    ConfigurationResolutionService,
    ScopeContext,
)
from backend.domain.settings.value_objects.configuration_scope import ConfigurationScope
from backend.infrastructure.db.repositories.settings.configuration_definition_repository import (
    SqliteConfigurationDefinitionRepository,
)
from backend.infrastructure.db.repositories.settings.configuration_value_repository import (
    SqliteConfigurationValueRepository,
)

logger = logging.getLogger("spj.settings.reader")


@dataclass(frozen=True)
class EffectiveSetting:
    key: str
    value: object
    source_scope_type: str | None = None
    source_scope_id: str | None = None
    version: int | None = None
    value_id: str | None = None

    @property
    def is_default(self) -> bool:
        """True si no hay ningún valor activo aplicable: rige el de omisión."""
        return self.value_id is None


class ConfigurationReader:
    def __init__(self, connection) -> None:
        self._definitions = SqliteConfigurationDefinitionRepository(connection)
        self._values = SqliteConfigurationValueRepository(connection)
        self._resolver = ConfigurationResolutionService()

    def get(self, key: str, *, context: Mapping[ScopeType, str] | None = None,
            at: datetime | None = None) -> object:
        return self.resolve(key, context=context, at=at).value

    def resolve(self, key: str, *, context: Mapping[ScopeType, str] | None = None,
                at: datetime | None = None) -> EffectiveSetting:
        spec = CATALOG_BY_KEY.get(key)
        if spec is None:
            raise ConfigurationDefinitionNotFoundError(
                f"{key!r} no está en el catálogo de parámetros gobernados")
        try:
            definition = self._definitions.get_by_key(key)
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc):
                raise
            definition = None
        if definition is None:
            # La migración que sincroniza el catálogo no ha corrido en esta base
            # (o es una base reducida sin las tablas de gobierno).
            # Rige el valor de omisión del catálogo, y se dice: no es un fallo
            # silencioso, la pantalla de Parámetros lo muestra como "omisión".
            logger.warning("Definición %s sin sincronizar; rige el valor de omisión", key)
            return EffectiveSetting(key, spec.default_value)
        applicable: dict[ScopeType, str] = {}
        scopes = [ConfigurationScope.global_scope()]
        for scope_type, scope_id in (context or {}).items():
            scope_type = ScopeType(scope_type)
            if (not scope_id or scope_type is ScopeType.GLOBAL
                    or not definition.allows_scope(scope_type)):
                continue
            try:
                scopes.append(ConfigurationScope.create(scope_type, scope_id))
            except ConfigurationDomainError:
                # Un id que no es UUIDv7 no puede tener un valor gobernado.
                continue
            applicable[scope_type] = scope_id
        scope_context = ScopeContext(applicable)
        candidates = self._values.list_candidates(definition.id, tuple(scopes))
        resolved = self._resolver.resolve(definition, candidates, context=scope_context, at=at)
        chosen = resolved.configuration_value
        if chosen is None:
            return EffectiveSetting(key, resolved.value)
        return EffectiveSetting(
            key, resolved.value, source_scope_type=chosen.scope.scope_type.value,
            source_scope_id=chosen.scope.scope_id, version=chosen.version.value,
            value_id=chosen.id)
