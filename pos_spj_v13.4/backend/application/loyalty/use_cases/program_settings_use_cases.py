"""Editar los ajustes del programa de puntos (Fidelidad → Ajustes, 2026-10-02).

Acumulación (pesos por punto, si el crédito acumula, meses de vigencia) y canje
(valor del punto, mínimo para canjear, tope del ticket pagadero con puntos). Lo
decidió el usuario: todo configurable desde Fidelidad; antes ni los ajustes de
canje tenían pantalla.

Exige `GROWTH_ENGINE.configuracion.editar`. Valida antes de escribir (un valor
inválido dejaría el cobro con los de fábrica sin avisar) y deja el antes/después
en el outbox de Fidelidad.
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
from backend.application.loyalty.use_cases._base import _LoyaltyBaseUseCase
from backend.domain.loyalty.events import SYSTEM_ACTOR_ID, LoyaltyEvents
from backend.domain.loyalty.exceptions import LoyaltyDomainError
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
            PESOS_PER_POINT_KEY: str(pesos), CREDIT_EARNS_KEY: "1" if credit_earns else "0",
            EXPIRATION_MONTHS_KEY: str(meses), POINT_VALUE_KEY: str(valor),
            MIN_POINTS_KEY: str(minimo), MAX_PERCENT_KEY: str(tope),
        }
        with LoyaltyUnitOfWork(connection) as uow:
            for clave, valor_texto in nuevos.items():
                connection.execute(
                    "INSERT INTO configuraciones (clave, valor, grupo) VALUES (?,?,'fidelidad')"
                    " ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor", (clave, valor_texto))
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
                       after=nuevos)
        return LoyaltyResult.ok("Ajustes guardados", operation_id=operation_id)
