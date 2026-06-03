"""Base repository contracts for infrastructure persistence adapters."""

from __future__ import annotations

from typing import Any, Generic, Protocol, TypeVar


EntityId = TypeVar("EntityId")
Entity = TypeVar("Entity")


class Repository(Protocol[EntityId, Entity]):
    def get(self, entity_id: EntityId) -> Entity | None:
        """Return an entity by id or None when it does not exist."""

    def add(self, entity: Entity) -> None:
        """Persist a new entity."""


class DbApiRepository(Generic[EntityId, Entity]):
    """Base class for DB-API repositories.

    Concrete repositories own SQL details. Application services should depend on
    explicit repository interfaces instead of raw UI cursors.
    """

    def __init__(self, connection: Any) -> None:
        self.connection = connection
