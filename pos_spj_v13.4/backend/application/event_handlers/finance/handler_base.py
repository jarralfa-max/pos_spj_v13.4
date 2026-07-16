"""Base for finance event handlers.

Contract for every operational event consumed by Finance:
- payload is a dict with UUIDv7 string ids;
- every monetary value travels as a decimal string ("125.40");
- ``event_id`` + ``operation_id`` are mandatory; a repeated event returns
  idempotently without duplicating effects.
"""

from __future__ import annotations

import logging
from datetime import date

from backend.domain.finance.exceptions import FinanceDomainError, PostingProfileNotFoundError
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork

logger = logging.getLogger("spj.finance.handlers")


class FinanceEventHandler:
    """Template: idempotency guard + UoW boundary around ``_handle``."""

    event_name: str = ""

    def __init__(self, connection) -> None:
        self._connection = connection

    def handle(self, payload: dict) -> None:
        event_id = str(payload.get("event_id") or "").strip()
        operation_id = str(payload.get("operation_id") or "").strip()
        if not event_id or not operation_id:
            raise FinanceDomainError(
                f"{self.event_name}: event_id y operation_id son obligatorios"
            )
        with FinanceUnitOfWork(self._connection) as uow:
            if uow.processed_events.was_processed(event_id):
                logger.info("%s: evento %s ya procesado (idempotente)", self.event_name, event_id)
                return
            self._handle(uow, payload)
            uow.processed_events.mark_processed(event_id, self.event_name, operation_id)

    def _handle(self, uow: FinanceUnitOfWork, payload: dict) -> None:
        raise NotImplementedError

    # ── payload helpers ───────────────────────────────────────────────────
    @staticmethod
    def money(payload: dict, key: str, currency: str, *, required: bool = True) -> Money:
        raw = payload.get(key)
        if raw is None or str(raw).strip() == "":
            if required:
                raise FinanceDomainError(f"Falta el importe requerido {key!r} en el evento")
            return Money.zero(currency)
        if isinstance(raw, float):
            raise FinanceDomainError(
                f"El importe {key!r} llegó como float; los eventos deben transportar cadenas decimales"
            )
        return Money.from_string(str(raw), currency)

    @staticmethod
    def currency(payload: dict) -> str:
        return str(payload.get("currency_code") or "MXN")

    @staticmethod
    def event_date(payload: dict) -> date:
        occurred = str(payload.get("occurred_at") or "")
        if occurred:
            return date.fromisoformat(occurred[:10])
        raise FinanceDomainError("El evento no incluye occurred_at")

    @staticmethod
    def resolve_profile(uow: FinanceUnitOfWork, profile_key: str, on_date: date, **criteria):
        profile = uow.posting_profiles.find_effective(profile_key, on_date, **criteria)
        if profile is None:
            raise PostingProfileNotFoundError(
                f"No hay perfil contable vigente para {profile_key!r} en {on_date.isoformat()}; "
                "configure el perfil antes de procesar el evento"
            )
        return profile
