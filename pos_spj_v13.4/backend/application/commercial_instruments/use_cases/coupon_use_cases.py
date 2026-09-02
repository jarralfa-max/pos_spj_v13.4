"""LOY-12 — Coupon use cases: Define, Issue, Validate+Reserve, Confirm,
Release, Cancel, Expire (master prompt §21, phase list "LOY-12 — Cupones":
Definición, Emisión, Validación, Reserva, Redención, Expiración, Reverso).

§21: "No marcar redención antes de completar la venta" — enforced by
construction: `ConfirmCouponRedemptionUseCase` is the ONLY place that calls
`CouponInstance.confirm_redemption()`, and it always requires an existing
RESERVED instance tied to a real `sale_id` — there is no path that marks a
coupon REDEEMED without first going through `reserve()`.

Reuses `LoyaltyPermissions.COUPON_*` (see `use_cases/_base.py`'s own
docstring for why) and shapes `COUPON_ISSUED`/`COUPON_REDEEMED`/
`COUPON_EXPIRED`/`COUPON_CANCELLED` payloads to match the fields Finance's
already-built `InstrumentIssuedAdapter`/`InstrumentRedeemedAdapter`/
`InstrumentExpiredAdapter`/`InstrumentReversedAdapter` expect
(`instrument_id`, `face_value`/`redeemed_value`, `operation_id`,
`customer_id`, `branch_id`, `currency_code`) — same LOY-0 "highest value"
finding already applied throughout Loyalty's own event catalog.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.commercial_instruments.dto import (
    CouponDefinitionDTO,
    CouponInstanceDTO,
)
from backend.application.commercial_instruments.result import (
    CommercialInstrumentResult,
    fail_from_domain_error,
)
from backend.application.commercial_instruments.use_cases._base import (
    _CommercialInstrumentBaseUseCase,
)
from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.domain.commercial_instruments.entities.coupon_definition import CouponDefinition
from backend.domain.commercial_instruments.entities.coupon_instance import CouponInstance
from backend.domain.commercial_instruments.entities.coupon_redemption import CouponRedemption
from backend.domain.commercial_instruments.enums import CommercialBenefitType, CouponType
from backend.domain.commercial_instruments.events import CommercialInstrumentEvents
from backend.domain.commercial_instruments.exceptions import (
    CommercialInstrumentDomainError,
    CouponAlreadyRedeemedError,
    CouponDefinitionNotFoundError,
    CouponExpiredError,
    CouponInactiveError,
    CouponNotEligibleError,
    CouponNotFoundError,
)
from backend.domain.loyalty.exceptions import LoyaltyDomainError
from backend.infrastructure.db.repositories.commercial_instruments.unit_of_work import (
    CommercialInstrumentsUnitOfWork,
)


class CreateCouponDefinitionUseCase(_CommercialInstrumentBaseUseCase):
    def execute(
        self, connection, *, code: str, name: str, coupon_type: CouponType,
        benefit_type: CommercialBenefitType, benefit_value: Decimal, actor_user_id: str,
        operation_id: str, valid_from: str | None = None, valid_to: str | None = None,
        source_program_id: str | None = None,
    ) -> CommercialInstrumentResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.COUPON_ISSUE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            if uow.coupon_definitions.get_by_code(code) is not None:
                return fail_from_domain_error(
                    CommercialInstrumentDomainError(
                        f"Ya existe una definición de cupón con el código {code}"),
                    operation_id=operation_id)
            try:
                definition = CouponDefinition.create(
                    code, name, coupon_type, benefit_type, benefit_value,
                    valid_from=valid_from, valid_to=valid_to,
                    source_program_id=source_program_id)
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.coupon_definitions.save(definition)
        return CommercialInstrumentResult.ok(
            "Definición de cupón creada", entity_id=definition.id, operation_id=operation_id,
            definition=CouponDefinitionDTO.from_entity(definition))


class IssueCouponInstanceUseCase(_CommercialInstrumentBaseUseCase):
    def execute(
        self, connection, *, definition_id: str, code: str, actor_user_id: str,
        actor_branch_id: str, operation_id: str, customer_id: str | None = None,
        currency_code: str = "MXN",
    ) -> CommercialInstrumentResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.COUPON_ISSUE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            definition = uow.coupon_definitions.get(definition_id)
            if definition is None:
                return fail_from_domain_error(
                    CouponDefinitionNotFoundError(f"Definición {definition_id} no existe"),
                    operation_id=operation_id)
            if not definition.active:
                return fail_from_domain_error(
                    CouponInactiveError(f"La definición {definition.code} no está activa"),
                    operation_id=operation_id)
            if uow.coupon_instances.get_by_code(code) is not None:
                return fail_from_domain_error(
                    CommercialInstrumentDomainError(f"El código {code} ya está en uso"),
                    operation_id=operation_id)
            instance = CouponInstance.issue(definition_id, code, customer_id=customer_id)
            uow.coupon_instances.save(instance)
            self._emit(
                uow, CommercialInstrumentEvents.COUPON_ISSUED, entity_id=instance.id,
                operation_id=operation_id, branch_id=actor_branch_id,
                actor_user_id=actor_user_id, instrument_id=instance.id,
                face_value=str(definition.benefit_value), currency_code=currency_code,
                customer_id=customer_id, source_module="commercial_instruments",
            )
        return CommercialInstrumentResult.ok(
            "Cupón emitido", entity_id=instance.id, operation_id=operation_id,
            instance=CouponInstanceDTO.from_entity(instance))


class ValidateAndReserveCouponUseCase(_CommercialInstrumentBaseUseCase):
    """§21's flow step 1-2: Validar elegibilidad → Reservar. No permission
    gate — validating/applying a coupon at checkout is a normal cashier
    action already covered by `POS.venta.linea_agregar`-equivalent flows,
    not a Fidelidad-specific privilege (mirrors how redeeming loyalty points
    at checkout doesn't require a separate Loyalty permission either, per
    the master prompt's own §6 boundary: Sales applies benefits, it doesn't
    need Fidelidad's administrative permissions to do so)."""

    def execute(
        self, connection, *, code: str, sale_id: str, actor_user_id: str,
        actor_branch_id: str, operation_id: str, customer_id: str | None = None,
        now_iso: str | None = None,
    ) -> CommercialInstrumentResult:
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            instance = uow.coupon_instances.get_by_code(code)
            if instance is None:
                return fail_from_domain_error(
                    CouponNotFoundError(f"No existe un cupón con el código {code}"),
                    operation_id=operation_id)
            definition = uow.coupon_definitions.get(instance.definition_id)
            if not instance.is_usable():
                if instance.status.value == "REDEEMED":
                    return fail_from_domain_error(
                        CouponAlreadyRedeemedError(f"El cupón {code} ya fue canjeado"),
                        operation_id=operation_id)
                return fail_from_domain_error(
                    CouponInactiveError(f"El cupón {code} no está activo"),
                    operation_id=operation_id)
            if instance.customer_id is not None and instance.customer_id != customer_id:
                return fail_from_domain_error(
                    CouponNotEligibleError(
                        f"El cupón {code} está asignado a otro cliente"),
                    operation_id=operation_id)
            if now_iso is not None and definition is not None and definition.valid_to is not None:
                if now_iso > definition.valid_to:
                    return fail_from_domain_error(
                        CouponExpiredError(f"El cupón {code} ya venció"),
                        operation_id=operation_id)
            try:
                instance.reserve(sale_id)
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.coupon_instances.save(instance)
            self._emit(uow, CommercialInstrumentEvents.COUPON_RESERVED, entity_id=instance.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id, sale_id=sale_id)
        return CommercialInstrumentResult.ok(
            "Cupón reservado", entity_id=instance.id, operation_id=operation_id,
            instance=CouponInstanceDTO.from_entity(instance),
            benefit_type=definition.benefit_type.value if definition else None,
            benefit_value=definition.benefit_value if definition else None)


class ConfirmCouponRedemptionUseCase(_CommercialInstrumentBaseUseCase):
    """§21: 'No marcar redención antes de completar la venta' — this is the
    ONLY caller that transitions a coupon to REDEEMED, and it always
    requires a real amount actually applied to a real sale."""

    def execute(
        self, connection, *, coupon_instance_id: str, amount_applied: Decimal,
        redeemed_by_user_id: str, actor_branch_id: str, operation_id: str,
        currency_code: str = "MXN",
    ) -> CommercialInstrumentResult:
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            instance = uow.coupon_instances.get(coupon_instance_id)
            if instance is None:
                return fail_from_domain_error(
                    CouponNotFoundError(f"Cupón {coupon_instance_id} no existe"),
                    operation_id=operation_id)
            sale_id = instance.sale_id
            try:
                instance.confirm_redemption()
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.coupon_instances.save(instance)
            redemption = CouponRedemption.record(
                instance.id, sale_id, amount_applied, redeemed_by_user_id)
            uow.coupon_redemptions.add(redemption)
            self._emit(
                uow, CommercialInstrumentEvents.COUPON_REDEEMED, entity_id=instance.id,
                operation_id=operation_id, branch_id=actor_branch_id,
                actor_user_id=redeemed_by_user_id, instrument_id=instance.id,
                redeemed_value=str(amount_applied), currency_code=currency_code,
                redemption_id=redemption.id,
            )
        return CommercialInstrumentResult.ok(
            "Canje confirmado", entity_id=instance.id, operation_id=operation_id,
            instance=CouponInstanceDTO.from_entity(instance))


class ReleaseCouponReservationUseCase(_CommercialInstrumentBaseUseCase):
    def execute(self, connection, *, coupon_instance_id: str, actor_branch_id: str,
                operation_id: str, actor_user_id: str) -> CommercialInstrumentResult:
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            instance = uow.coupon_instances.get(coupon_instance_id)
            if instance is None:
                return fail_from_domain_error(
                    CouponNotFoundError(f"Cupón {coupon_instance_id} no existe"),
                    operation_id=operation_id)
            try:
                instance.release()
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.coupon_instances.save(instance)
            self._emit(uow, CommercialInstrumentEvents.COUPON_RELEASED, entity_id=instance.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id)
        return CommercialInstrumentResult.ok(
            "Reserva de cupón liberada", entity_id=instance.id, operation_id=operation_id,
            instance=CouponInstanceDTO.from_entity(instance))


class CancelCouponInstanceUseCase(_CommercialInstrumentBaseUseCase):
    def execute(self, connection, *, coupon_instance_id: str, reason: str,
                actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> CommercialInstrumentResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.COUPON_CANCEL)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            instance = uow.coupon_instances.get(coupon_instance_id)
            if instance is None:
                return fail_from_domain_error(
                    CouponNotFoundError(f"Cupón {coupon_instance_id} no existe"),
                    operation_id=operation_id)
            try:
                instance.cancel(reason)
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.coupon_instances.save(instance)
            self._emit(uow, CommercialInstrumentEvents.COUPON_CANCELLED, entity_id=instance.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id, instrument_id=instance.id, reason=reason)
        return CommercialInstrumentResult.ok(
            "Cupón cancelado", entity_id=instance.id, operation_id=operation_id,
            instance=CouponInstanceDTO.from_entity(instance))


class ExpireCouponsUseCase(_CommercialInstrumentBaseUseCase):
    """System sweep — mirrors `ExpireLoyaltyPointsUseCase`'s own shape
    (LOY-6): no actor/permission gate, uses `SYSTEM_ACTOR_ID` for the
    emitted events."""

    def execute(self, connection, *, now_iso: str, operation_id_prefix: str,
                limit: int = 500) -> CommercialInstrumentResult:
        from backend.domain.loyalty.events import SYSTEM_ACTOR_ID
        from backend.shared.ids import new_uuid

        with CommercialInstrumentsUnitOfWork(connection) as uow:
            expired_ids: list[str] = []
            rows = uow.connection.execute(
                "SELECT id FROM coupon_definitions WHERE valid_to IS NOT NULL"
                " AND valid_to < ?", (now_iso,)).fetchall()
            expired_definition_ids = [row[0] for row in rows]
            for instance in uow.coupon_instances.list_expirable(
                    definition_ids=expired_definition_ids, limit=limit):
                instance.expire()
                uow.coupon_instances.save(instance)
                op_id = new_uuid()
                self._emit(uow, CommercialInstrumentEvents.COUPON_EXPIRED,
                           entity_id=instance.id, operation_id=op_id,
                           branch_id=SYSTEM_ACTOR_ID, actor_user_id=SYSTEM_ACTOR_ID,
                           instrument_id=instance.id)
                expired_ids.append(instance.id)
        return CommercialInstrumentResult.ok(
            f"{len(expired_ids)} cupones expirados", operation_id=operation_id_prefix,
            expired_instance_ids=expired_ids)
