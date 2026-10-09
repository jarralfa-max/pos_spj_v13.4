"""Editar los ajustes del programa de puntos (Fidelidad → Ajustes, 2026-10-02).

Acumulación (pesos por punto, si el crédito acumula, meses de vigencia) y canje
(valor del punto, mínimo para canjear, tope del ticket pagadero con puntos). Lo
decidió el usuario: todo configurable desde Fidelidad; antes ni los ajustes de
canje tenían pantalla.

Exige `GROWTH_ENGINE.configuracion.editar`. Valida antes de escribir y guarda
por `GovernedSettingsWriter`: cada valor que cambia es una versión nueva del
parámetro gobernado, auditada, en la misma transacción que el evento del outbox
de Fidelidad.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.application.loyalty.queries.program_settings_query import (
    CREDIT_EARNS_KEY,
    EXPIRATION_MONTHS_KEY,
    MAX_PERCENT_KEY,
    MIN_POINTS_KEY,
    PESOS_PER_POINT_KEY,
    POINT_VALUE_KEY,
    LoyaltyProgramSettingsQuery,
)
from backend.application.loyalty.result import LoyaltyResult, fail_from_domain_error
from backend.application.settings.governance import GovernedSettingsWriter
from backend.application.loyalty.use_cases._base import _LoyaltyBaseUseCase
from backend.domain.loyalty.events import SYSTEM_ACTOR_ID, LoyaltyEvents
from backend.domain.loyalty.exceptions import LoyaltyDomainError
from backend.domain.settings.exceptions import ConfigurationDomainError
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork
from backend.shared.ids import new_uuid


def _dec(value, name: str) -> Decimal:
    if isinstance(value, float):
        raise LoyaltyDomainError(f"{name}: no se captura como float")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise LoyaltyDomainError(f"{name}: valor inválido") from exc


class UpdateLoyaltyProgramSettingsUseCase(_LoyaltyBaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, operation_id: str,
        pesos_per_point, credit_earns: bool, expiration_months: int,
        point_value, min_points: int, max_percent, branch_id: str | None = None,
    ) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.CONFIG_EDIT)
            pesos = _dec(pesos_per_point, "Pesos por punto")
            valor = _dec(point_value, "Valor del punto")
            tope = _dec(max_percent, "Tope del ticket")
            meses, minimo = int(expiration_months), int(min_points)
            if pesos <= 0:
                raise LoyaltyDomainError("Los pesos por punto deben ser mayores a cero")
            if meses < 0 or meses > 120:
                raise LoyaltyDomainError("La vigencia va de 0 (no caducan) a 120 meses")
            if valor <= 0:
                raise LoyaltyDomainError("El valor del punto debe ser mayor a cero")
            if minimo < 0:
                raise LoyaltyDomainError("El mínimo para canjear no puede ser negativo")
            if tope <= 0 or tope > 1:
                raise LoyaltyDomainError("El tope del ticket va de más de 0 % a 100 %")
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        antes = LoyaltyProgramSettingsQuery(connection).current()
        nuevos = {
            PESOS_PER_POINT_KEY: pesos, CREDIT_EARNS_KEY: bool(credit_earns),
            EXPIRATION_MONTHS_KEY: meses, POINT_VALUE_KEY: valor,
            MIN_POINTS_KEY: minimo, MAX_PERCENT_KEY: tope,
        }
        writer = GovernedSettingsWriter(connection)
        try:
            with LoyaltyUnitOfWork(connection) as uow:
                writer.stage(nuevos, actor_user_id=actor_user_id, operation_id=operation_id,
                             reason="Fidelidad → Ajustes")
                self._emit(uow, LoyaltyEvents.PROGRAM_SETTINGS_UPDATED, entity_id=new_uuid(),
                           operation_id=operation_id, branch_id=branch_id or SYSTEM_ACTOR_ID,
                           actor_user_id=actor_user_id,
                           before={
                               "pesos_per_point": str(antes.accrual.pesos_per_point),
                               "credit_earns": antes.accrual.credit_earns,
                               "expiration_months": antes.accrual.expiration_months,
                               "point_value": str(antes.redemption.point_value),
                               "min_points": antes.redemption.min_points,
                               "max_percent": str(antes.redemption.max_percent)},
                           after={clave: str(v) for clave, v in nuevos.items()})
        except ConfigurationDomainError as exc:
            return fail_from_domain_error(LoyaltyDomainError(str(exc)), operation_id=operation_id)
        writer.publish()
        return LoyaltyResult.ok("Ajustes guardados", operation_id=operation_id)
