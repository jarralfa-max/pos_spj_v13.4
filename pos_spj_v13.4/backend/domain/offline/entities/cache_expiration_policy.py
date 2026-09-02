"""CacheExpirationPolicy — SET-23 "Expiration": the TTL a given
`entity_type` should be considered fresh for. Generalizes the legacy
`core/cache/address_cache.py::AddressCache`'s hardcoded `ttl=3600` into a
typed, admin-editable, per-entity-type record — the domain never guesses
its own threshold (same "quien llama define el umbral" discipline
`backend.domain.settings.entities.workstation.Workstation.is_online`
already established for staleness: *"el dominio nunca decide un umbral
de 'cuánto es demasiado' por su cuenta — eso lo define quien llama"*).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.offline.exceptions import OfflineInvalidValueError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CacheExpirationPolicy:
    id: str
    entity_type: str
    ttl_seconds: int
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, entity_type: str, ttl_seconds: int) -> "CacheExpirationPolicy":
        if not entity_type.strip():
            raise OfflineInvalidValueError("entity_type es obligatorio")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise OfflineInvalidValueError(
                f"ttl_seconds debe ser un entero positivo, recibido {ttl_seconds!r}"
            )
        return cls(id=new_uuid(), entity_type=entity_type.strip(), ttl_seconds=ttl_seconds)

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()

    def change_ttl(self, ttl_seconds: int) -> None:
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise OfflineInvalidValueError(
                f"ttl_seconds debe ser un entero positivo, recibido {ttl_seconds!r}"
            )
        self.ttl_seconds = ttl_seconds
        self._touch()
