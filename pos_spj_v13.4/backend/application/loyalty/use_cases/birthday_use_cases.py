"""LOY-14/LOY-24 — Birthday benefit use cases (master prompt §18, phase list
"LOY-14 — Cumpleaños y retención": Reglas, Consentimientos, Campañas,
Win-back).

`GrantBirthdayBenefitUseCase` is system-triggered (mirrors LOY-6/7/9's own
sweeps: `ExpireLoyaltyPointsUseCase`/`EvaluateLoyaltyMembershipTierUseCase`)
— a birthday benefit fires because a date matched, not because an
authenticated human requested it. It therefore does NOT delegate to
`AccrueLoyaltyPointsUseCase`/`IssueCouponInstanceUseCase`/
`IssueVoucherInstanceUseCase` (a first draft tried this and was wrong):
those use cases call `self._auth.require(actor_user_id, ...)` against a
REAL session-backed `PermissionChecker` in production, which would always
deny a system actor with no live session — exactly the same reasoning the
sweep use cases already apply by never gating themselves on a permission
check at all. This use case instead performs the ledger/instrument
creation directly against the appropriate repositories, using
`SYSTEM_ACTOR_ID` for audit/event attribution, same as the sweeps.

**LOY-24**: COUPON and VOUCHER benefit types are now implemented, crossing
into Commercial Instruments' own tables via its RAW repositories
(`CouponInstanceRepository`/`VoucherInstanceRepository`/etc.) constructed
directly on the SAME connection — never via a whole
`CommercialInstrumentsUnitOfWork`, whose own `__exit__` would call
`connection.commit()` a second time before this use case's own
`LoyaltyUnitOfWork` finishes, breaking atomicity if anything failed
afterward (same "shared connection, don't nest a second UoW" lesson
LOY-22 already applied to `LoyaltyCardPrintJob`). REWARD remains
unimplemented — this codebase has no "grant a reward for free" mechanism
anywhere (`RequestRewardRedemptionUseCase` always spends real points); building
one is a larger, separate feature, not something to force into this phase.
"""

from __future__ import annotations

import json
import secrets
from decimal import Decimal

from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.application.loyalty.result import LoyaltyResult, fail_from_domain_error
from backend.application.loyalty.use_cases._base import _LoyaltyBaseUseCase
from backend.domain.commercial_instruments.entities.coupon_instance import CouponInstance
from backend.domain.commercial_instruments.entities.voucher_instance import VoucherInstance
from backend.domain.commercial_instruments.entities.voucher_transaction import VoucherTransaction
from backend.domain.commercial_instruments.events import (
    CommercialInstrumentEvents,
    commercial_instrument_event_payload,
)
from backend.domain.commercial_instruments.exceptions import (
    CouponDefinitionNotFoundError,
    CouponInactiveError,
    VoucherDefinitionNotFoundError,
)
from backend.domain.loyalty.entities.birthday_benefit_config import BirthdayBenefitConfig
from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
from backend.domain.loyalty.enums import BirthdayBenefitType
from backend.domain.loyalty.events import SYSTEM_ACTOR_ID, LoyaltyEvents
from backend.domain.loyalty.exceptions import (
    BirthdayBenefitConfigNotFoundError,
    ConsentRequiredError,
    LoyaltyAccountNotFoundError,
    LoyaltyDomainError,
    LoyaltyProgramNotFoundError,
)
from backend.infrastructure.db.repositories.commercial_instruments.coupon_repository import (
    CouponDefinitionRepository,
    CouponInstanceRepository,
)
from backend.infrastructure.db.repositories.commercial_instruments.outbox_repository import (
    CommercialInstrumentsOutboxRepository,
)
from backend.infrastructure.db.repositories.commercial_instruments.voucher_repository import (
    VoucherDefinitionRepository,
    VoucherInstanceRepository,
    VoucherTransactionRepository,
)
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork
from backend.shared.ids import new_uuid


def _generate_instrument_code(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(4).upper()}"


class ConfigureBirthdayBenefitUseCase(_LoyaltyBaseUseCase):
    def execute(
        self, connection, *, program_id: str, actor_user_id: str, operation_id: str,
        enabled: bool = True, benefit_type: BirthdayBenefitType = BirthdayBenefitType.NONE,
        points_amount: Decimal = Decimal("0"), coupon_definition_id: str | None = None,
        voucher_definition_id: str | None = None, reward_id: str | None = None,
        days_before: int = 0, days_after: int = 0, notification_channel: str = "",
    ) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.BIRTHDAY_MANAGE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            if uow.programs.get(program_id) is None:
                return fail_from_domain_error(
                    LoyaltyProgramNotFoundError(f"Programa {program_id} no existe"),
                    operation_id=operation_id)
            existing = uow.birthday_configs.get_by_program(program_id)
            try:
                config = BirthdayBenefitConfig(
                    id=existing.id if existing else new_uuid(), program_id=program_id,
                    enabled=enabled, benefit_type=benefit_type, points_amount=points_amount,
                    coupon_definition_id=coupon_definition_id,
                    voucher_definition_id=voucher_definition_id, reward_id=reward_id,
                    days_before=days_before, days_after=days_after,
                    notification_channel=notification_channel,
                )
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.birthday_configs.save(config)
        return LoyaltyResult.ok(
            "Configuración de cumpleaños guardada", entity_id=config.id,
            operation_id=operation_id)


class GrantBirthdayBenefitUseCase(_LoyaltyBaseUseCase):
    """System-triggered — see module docstring for why this never delegates
    to a permission-gated use case. ``has_marketing_consent`` is a
    required, explicit boolean the caller must supply (this bounded
    context does not own consent data — master prompt §53, Customer
    Privacy's own domain — so it never queries for it itself, only
    respects what it's told).

    POINTS/COUPON/VOUCHER are implemented (LOY-24). REWARD remains
    unimplemented — this codebase has no "grant for free" mechanism for a
    `Reward` anywhere (§15's `RequestRewardRedemptionUseCase` always spends
    real points); flagged, not fabricated.
    """

    def execute(
        self, connection, *, program_id: str, loyalty_account_id: str,
        has_marketing_consent: bool, actor_branch_id: str, operation_id: str,
    ) -> LoyaltyResult:
        with LoyaltyUnitOfWork(connection) as uow:
            config = uow.birthday_configs.get_by_program(program_id)
            if config is None:
                return fail_from_domain_error(
                    BirthdayBenefitConfigNotFoundError(
                        f"El programa {program_id} no tiene configuración de cumpleaños"),
                    operation_id=operation_id)
            if not config.enabled or config.benefit_type is BirthdayBenefitType.NONE:
                return LoyaltyResult.ok("Sin beneficio de cumpleaños configurado",
                                       operation_id=operation_id, granted=False)
            if not has_marketing_consent:
                return fail_from_domain_error(
                    ConsentRequiredError(
                        "El cliente no tiene consentimiento de mercadotecnia"),
                    operation_id=operation_id)

            if config.benefit_type is BirthdayBenefitType.POINTS:
                return self._grant_points(uow, config, loyalty_account_id, actor_branch_id,
                                          operation_id)
            if config.benefit_type is BirthdayBenefitType.COUPON:
                account = uow.accounts.get(loyalty_account_id)
                if account is None:
                    return fail_from_domain_error(
                        LoyaltyAccountNotFoundError(f"Cuenta {loyalty_account_id} no existe"),
                        operation_id=operation_id)
                return _grant_birthday_coupon(connection, config, account.customer_id,
                                              actor_branch_id, operation_id)
            if config.benefit_type is BirthdayBenefitType.VOUCHER:
                account = uow.accounts.get(loyalty_account_id)
                if account is None:
                    return fail_from_domain_error(
                        LoyaltyAccountNotFoundError(f"Cuenta {loyalty_account_id} no existe"),
                        operation_id=operation_id)
                return _grant_birthday_voucher(connection, config, account.customer_id,
                                               actor_branch_id, operation_id)
            return LoyaltyResult.fail(
                f"El tipo de beneficio {config.benefit_type.value} para cumpleaños"
                " aún no está implementado", "NOT_IMPLEMENTED", operation_id=operation_id)

    @staticmethod
    def _grant_points(uow, config: BirthdayBenefitConfig, loyalty_account_id: str,
                       actor_branch_id: str, operation_id: str) -> LoyaltyResult:
        bonus = LoyaltyTransaction.bonus(
            loyalty_account_id=loyalty_account_id, points_amount=config.points_amount,
            operation_id=operation_id, source_module="loyalty_birthday",
            reason_code="BIRTHDAY_BENEFIT", branch_id=actor_branch_id,
            created_by_user_id=SYSTEM_ACTOR_ID)
        uow.transactions.save(bonus)
        _LoyaltyBaseUseCase._emit(
            uow, LoyaltyEvents.POINTS_ISSUED, entity_id=bonus.id, operation_id=operation_id,
            branch_id=actor_branch_id, actor_user_id=SYSTEM_ACTOR_ID,
            loyalty_transaction_id=bonus.id, points_amount=str(config.points_amount))
        return LoyaltyResult.ok(
            "Beneficio de cumpleaños otorgado (puntos)", entity_id=bonus.id,
            operation_id=operation_id, granted=True)


def _grant_birthday_coupon(connection, config: BirthdayBenefitConfig, customer_id: str,
                           actor_branch_id: str, operation_id: str) -> LoyaltyResult:
    definitions = CouponDefinitionRepository(connection)
    instances = CouponInstanceRepository(connection)
    outbox = CommercialInstrumentsOutboxRepository(connection)

    definition = definitions.get(config.coupon_definition_id)
    if definition is None:
        return fail_from_domain_error(
            CouponDefinitionNotFoundError(f"Definición {config.coupon_definition_id} no existe"),
            operation_id=operation_id)
    if not definition.active:
        return fail_from_domain_error(
            CouponInactiveError(f"La definición {definition.code} no está activa"),
            operation_id=operation_id)

    code = _generate_instrument_code("BDAY")
    instance = CouponInstance.issue(definition.id, code, customer_id=customer_id)
    instances.save(instance)
    payload = commercial_instrument_event_payload(
        CommercialInstrumentEvents.COUPON_ISSUED, operation_id=operation_id,
        entity_id=instance.id, branch_id=actor_branch_id, user_id=SYSTEM_ACTOR_ID,
        instrument_id=instance.id, face_value=str(definition.benefit_value),
        customer_id=customer_id, source_module="loyalty_birthday")
    outbox.enqueue(event_id=payload["event_id"], event_name=payload["event_name"],
                    payload_json=_json_dumps(payload), operation_id=operation_id)
    return LoyaltyResult.ok(
        "Beneficio de cumpleaños otorgado (cupón)", entity_id=instance.id,
        operation_id=operation_id, granted=True, coupon_code=code)


def _grant_birthday_voucher(connection, config: BirthdayBenefitConfig, customer_id: str,
                            actor_branch_id: str, operation_id: str) -> LoyaltyResult:
    definitions = VoucherDefinitionRepository(connection)
    instances = VoucherInstanceRepository(connection)
    transactions = VoucherTransactionRepository(connection)
    outbox = CommercialInstrumentsOutboxRepository(connection)

    definition = definitions.get(config.voucher_definition_id)
    if definition is None:
        return fail_from_domain_error(
            VoucherDefinitionNotFoundError(f"Definición {config.voucher_definition_id} no existe"),
            operation_id=operation_id)

    code = _generate_instrument_code("BDAY")
    instance = VoucherInstance.issue(definition.id, code, customer_id=customer_id)
    instances.save(instance)
    issue_txn = VoucherTransaction.issue(
        voucher_instance_id=instance.id, amount=config.points_amount, operation_id=operation_id,
        created_by_user_id=SYSTEM_ACTOR_ID)
    transactions.save(issue_txn)
    payload = commercial_instrument_event_payload(
        CommercialInstrumentEvents.VOUCHER_ISSUED, operation_id=operation_id,
        entity_id=instance.id, branch_id=actor_branch_id, user_id=SYSTEM_ACTOR_ID,
        instrument_id=instance.id, face_value=str(config.points_amount),
        customer_id=customer_id, source_module="loyalty_birthday")
    outbox.enqueue(event_id=payload["event_id"], event_name=payload["event_name"],
                    payload_json=_json_dumps(payload), operation_id=operation_id)
    return LoyaltyResult.ok(
        "Beneficio de cumpleaños otorgado (vale)", entity_id=instance.id,
        operation_id=operation_id, granted=True, voucher_code=code)


def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)
