"""VersionNumber — a positive, monotonically increasing version tag on a
`ConfigurationValue` lineage (one per (definition, scope) history)."""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.settings.exceptions import ConfigurationInvalidValueError


@dataclass(frozen=True, slots=True, order=True)
class VersionNumber:
    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int) or self.value < 1:
            raise ConfigurationInvalidValueError("El número de versión debe ser un entero >= 1")

    @classmethod
    def first(cls) -> "VersionNumber":
        return cls(1)

    def next(self) -> "VersionNumber":
        return VersionNumber(self.value + 1)
