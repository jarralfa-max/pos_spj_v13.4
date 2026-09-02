"""EffectivePeriod — the vigencia window of one `ConfigurationValue`.

Mirrors backend/domain/cash_register/configuration.py's dating rules:
timezone-aware bounds, `effective_to` strictly after `effective_from` when
present, open-ended (`effective_to is None`) means "until superseded".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.domain.settings.exceptions import ConfigurationInvalidValueError


@dataclass(frozen=True, slots=True)
class EffectivePeriod:
    effective_from: datetime
    effective_to: datetime | None = None

    @classmethod
    def create(
        cls, effective_from: datetime, effective_to: datetime | None = None,
    ) -> "EffectivePeriod":
        if effective_from.tzinfo is None:
            raise ConfigurationInvalidValueError("effective_from requiere zona horaria")
        if effective_to is not None:
            if effective_to.tzinfo is None:
                raise ConfigurationInvalidValueError("effective_to requiere zona horaria")
            if effective_to <= effective_from:
                raise ConfigurationInvalidValueError(
                    "effective_to debe ser posterior a effective_from"
                )
        return cls(effective_from, effective_to)

    def contains(self, at: datetime) -> bool:
        if at.tzinfo is None:
            raise ConfigurationInvalidValueError("La fecha de evaluación requiere zona horaria")
        return self.effective_from <= at and (self.effective_to is None or at < self.effective_to)

    def has_expired(self, at: datetime) -> bool:
        return self.effective_to is not None and at >= self.effective_to

    def is_future(self, at: datetime) -> bool:
        return at < self.effective_from
