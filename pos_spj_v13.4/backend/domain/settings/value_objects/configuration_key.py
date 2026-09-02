"""ConfigurationKey — the dotted identifier of a `ConfigurationDefinition`.

Format: two or more lowercase snake_case segments joined by dots, e.g.
``orders.weight_adjustment_tolerance_pct`` (§9's own example). The leading
segment is conventionally the owning module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.domain.settings.exceptions import ConfigurationInvalidValueError

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


@dataclass(frozen=True, slots=True)
class ConfigurationKey:
    value: str

    @classmethod
    def create(cls, raw: str) -> "ConfigurationKey":
        candidate = str(raw or "").strip()
        if not _KEY_PATTERN.match(candidate):
            raise ConfigurationInvalidValueError(
                f"Clave de configuración inválida: {raw!r}. "
                "Formato esperado: modulo.nombre_parametro (minúsculas, snake_case, "
                "al menos un punto)."
            )
        return cls(candidate)

    @property
    def module(self) -> str:
        return self.value.split(".", 1)[0]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value
