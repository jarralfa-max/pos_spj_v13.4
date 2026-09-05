# domain/whatsapp/value_objects/intent_resolution.py — WA-8 (§27/§30)
"""IntentEntity y IntentResolution — el resultado de resolver la intención
de un mensaje. Value objects inmutables: una resolución ya hecha no
cambia, se vuelve a resolver."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

from domain.whatsapp.enums import Intent


class IntentResolutionSource(str, Enum):
    """§28 — capa que produjo la resolución, en el orden en que se intentan."""

    INTERACTIVE = "INTERACTIVE"
    EXPECTED_STATE = "EXPECTED_STATE"
    RULE = "RULE"
    CLASSIFIER = "CLASSIFIER"
    LLM = "LLM"
    UNRESOLVED = "UNRESOLVED"


class EntityValidationStatus(str, Enum):
    UNVALIDATED = "UNVALIDATED"
    VALID = "VALID"
    INVALID = "INVALID"


@dataclass(frozen=True)
class IntentEntity:
    """§30 — una entidad extraída del mensaje (producto, cantidad,
    sucursal...). Nunca se confía en el valor de una IA sin validación de
    dominio — `validation_status` empieza `UNVALIDATED` y una capa
    posterior (fuera de alcance de WA-8) la valida contra el dominio real."""

    name: str
    value: str
    normalized_value: Optional[str] = None
    confidence: float = 1.0
    source: str = "rule"
    validation_status: EntityValidationStatus = EntityValidationStatus.UNVALIDATED


@dataclass(frozen=True)
class IntentResolution:
    intent: Intent
    confidence: float
    source: IntentResolutionSource
    entities: Tuple[IntentEntity, ...] = field(default_factory=tuple)

    @property
    def is_resolved(self) -> bool:
        return self.source != IntentResolutionSource.UNRESOLVED
