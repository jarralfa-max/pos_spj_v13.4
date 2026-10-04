"""Puntos por compra: acreditarlos al completar una venta y quitarlos al
devolverla (decisiones del usuario, 2026-10-02).

* Se acumula 1 punto por cada N pesos del total pagado (Ajustes de Fidelidad;
  inicial $10), con caducidad configurable (inicial 12 meses).
* Un cliente identificado SIN cuenta de puntos la abre con su primera venta
  cobrada (crear el cliente no la crea, §22: la abre su primera compra).
* Devolver quita los puntos en proporción a lo devuelto, acumulado entre
  devoluciones, y nunca más de los que la compra dio ni más de los que el
  cliente aún tiene (lo ya canjeado no se le puede recuperar).
* Antes de acreditar corre el barrido de caducidad: sin planificador en el
  shell, cobrar es lo que lo mantiene al día.
* Canjear descuenta los puntos EN EL MOMENTO (antes de cobrar). Si la venta se
  cancela o se reversa, el canje se devuelve al cliente
  (`RestoreSaleRedemptionUseCase`); sin esto se perdían sin dejar rastro.

Llegan por el bus desde Ventas (`SALE_COMPLETED`, `SALE_RETURNED`,
`SALE_REVERSED`), con una política DELEGADA: el cajero no tiene permisos de
Fidelidad; Fidelidad concede a Ventas sólo acreditar y reversar
(`DelegatedIntegrationPermissionChecker`). Idempotente por documento: reintentar
el despacho no acredita ni quita dos veces.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.application.loyalty.queries.program_settings_query import LoyaltyProgramSettingsQuery
from backend.application.loyalty.result import LoyaltyResult, fail_from_domain_error
from backend.application.loyalty.use_cases._base import _LoyaltyBaseUseCase
from backend.application.loyalty.use_cases.ledger_use_cases import (
    AccrueLoyaltyPointsUseCase,
    ExpireLoyaltyPointsUseCase,
    ReverseLoyaltyTransactionUseCase,
)
from backend.application.security.system_integration_authorization import (
    DelegatedIntegrationPermissionChecker,
    IntegrationGrant,
)
from backend.domain.loyalty.entities.loyalty_account import LoyaltyAccount
from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
from backend.domain.loyalty.enums import TransactionStatus, TransactionType
from backend.domain.loyalty.events import LoyaltyEvents
from backend.domain.loyalty.exceptions import LoyaltyDomainError
from backend.domain.loyalty.policies.accrual_policy import LoyaltyAccrualPolicy
from backend.domain.loyalty.policies.balance_policy import LoyaltyBalancePolicy
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork
from backend.shared.ids import new_uuid

#: Lo que Fidelidad permite pedir a Ventas en nombre del cajero.
SALES_GRANT = IntegrationGrant(
    owner_context="loyalty", source_module="sales",
    permissions=frozenset({LoyaltyPermissions.POINTS_CREDIT, LoyaltyPermissions.POINTS_REVERSE}))

RETURN_REASON = "SALE_RETURN"
RESTORE_REASON = "SALE_CANCELLED_REDEMPTION"


def delegated_policy(actor_user_id: str) -> LoyaltyAuthorizationPolicy:
    return LoyaltyAuthorizationPolicy(DelegatedIntegrationPermissionChecker(
        grant=SALES_GRANT, actor_user_id=actor_user_id))


class AccrueSalePointsUseCase(_LoyaltyBaseUseCase):
    """Acredita los puntos de una compra con las REGLAS de Fidelidad (§13,
    2026-10-03): base de la Configuración o reglas base, multiplicadores y
    bonos (`LoyaltyAccrualEvaluator`, el mismo cálculo que el POS muestra como
    "puntos a ganar"). La evaluación se guarda ANTES de acreditar
    (`loyalty_sale_evaluations` + aplicaciones por regla): un reintento acredita
    exactamente lo evaluado, aunque entre tanto cambien reglas o usos."""

    def execute(self, connection, *, sale_id: str, customer_id: str | None, total,
                credit_amount, branch_id: str, actor_user_id: str, operation_id: str,
                occurred_at: str | None = None, lines=None, payments=None,
                channel: str = "POS") -> LoyaltyResult:
        if not customer_id:
            return LoyaltyResult.ok("Venta de mostrador: no acumula", operation_id=operation_id,
                                    points=0)
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.POINTS_CREDIT)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        momento = _moment(occurred_at)
        ExpireLoyaltyPointsUseCase(self._auth).execute(
            connection, before_iso=momento.isoformat(timespec="seconds"),
            operation_id_prefix=new_uuid())
        from backend.application.loyalty.use_cases.birthday_use_cases import (
            GrantDueBirthdayBenefitsUseCase,
        )
        GrantDueBirthdayBenefitsUseCase().execute(connection, today=momento.date())

        settings = LoyaltyProgramSettingsQuery(connection).accrual()
        puntos, desglose = _evaluate_once(
            connection, sale_id=sale_id, customer_id=customer_id, branch_id=branch_id,
            total=total, credit_amount=credit_amount, lines=lines, payments=payments,
            channel=channel, momento=momento)
        if puntos <= 0:
            return LoyaltyResult.ok("La compra no alcanza un punto", operation_id=operation_id,
                                    points=0, breakdown=desglose)

        with LoyaltyUnitOfWork(connection) as uow:
            account = uow.accounts.get_by_customer_id(customer_id)
            if account is None:
                account = LoyaltyAccount.create(customer_id)
                uow.accounts.save(account)
            elif not account.is_operational():
                return LoyaltyResult.ok("La cuenta de puntos del cliente no está activa",
                                        operation_id=operation_id, points=0)
        result = AccrueLoyaltyPointsUseCase(self._auth).execute(
            connection, loyalty_account_id=account.id, points_amount=Decimal(puntos),
            operation_id=operation_id, actor_user_id=actor_user_id, actor_branch_id=branch_id,
            source_module="sales", reason_code="SALE", source_document_id=sale_id,
            sale_id=sale_id, expires_at=LoyaltyAccrualPolicy.expires_at(momento, settings))
        if not result.success and "Ya existe una acreditación" in (result.message or ""):
            return LoyaltyResult.ok("Puntos ya acreditados (idempotente)",
                                    operation_id=operation_id, points=puntos,
                                    already_processed=True)
        if result.success:
            result.data["points"] = puntos
            result.data["breakdown"] = desglose
        return result


def _evaluate_once(connection, *, sale_id, customer_id, branch_id, total, credit_amount,
                   lines, payments, channel, momento) -> tuple[int, list[dict]]:
    """Evalúa la compra UNA vez y la guarda con sus reglas aplicadas; si ya se
    evaluó (reintento del despacho), devuelve lo guardado."""
    import json

    from backend.application.loyalty.queries.customer_benefits_query import (
        LoyaltyAccrualEvaluator,
    )
    from backend.infrastructure.db.repositories.loyalty.rule_repository import (
        LoyaltyRuleRepository,
    )

    reglas = LoyaltyRuleRepository(connection)
    previa = reglas.evaluation_for(sale_id)
    if previa is not None:
        return int(Decimal(str(previa["points"]))), json.loads(previa["breakdown_json"] or "[]")
    evaluacion = LoyaltyAccrualEvaluator(connection).evaluate(
        customer_id=customer_id, branch_id=branch_id, total=total,
        credit_amount=credit_amount or 0, lines=lines or (), payments=payments or (),
        channel=channel, occurred_at=momento, sale_id=sale_id)
    desglose = [{"rule_id": a.rule_id, "code": a.code, "name": a.name, "points": a.points}
                for a in evaluacion.applied]
    with LoyaltyUnitOfWork(connection) as uow:
        cuenta = uow.accounts.get_by_customer_id(customer_id)
        repo = LoyaltyRuleRepository(uow.connection)
        cuando = momento.astimezone(timezone.utc).isoformat(timespec="seconds")
        repo.record_evaluation(sale_id=sale_id, customer_id=customer_id,
                               loyalty_account_id=cuenta.id if cuenta else None,
                               points=evaluacion.points, breakdown=desglose, evaluated_at=cuando)
        for aplicada in evaluacion.applied:
            if aplicada.rule_id:
                repo.record_application(rule_id=aplicada.rule_id, sale_id=sale_id,
                                        customer_id=customer_id, points=aplicada.points,
                                        applied_at=cuando)
    return evaluacion.points, desglose


class RemoveSalePointsUseCase(_LoyaltyBaseUseCase):
    """Quita los puntos de lo devuelto. `document_id` identifica la devolución
    (o la venta, en un reverso total): una por documento."""

    def execute(self, connection, *, sale_id: str, customer_id: str | None, document_id: str,
                sale_total, refunded_total, branch_id: str, actor_user_id: str,
                operation_id: str) -> LoyaltyResult:
        if not customer_id:
            return LoyaltyResult.ok("Venta de mostrador: sin puntos", operation_id=operation_id,
                                    points=0)
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.POINTS_REVERSE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            account = uow.accounts.get_by_customer_id(customer_id)
            if account is None:
                return LoyaltyResult.ok("El cliente no tiene cuenta de puntos",
                                        operation_id=operation_id, points=0)
            movimientos = uow.transactions.list_for_account(account.id)
            if any(t.source_document_id == document_id and t.reason_code == RETURN_REASON
                   for t in movimientos):
                return LoyaltyResult.ok("Puntos ya retirados (idempotente)",
                                        operation_id=operation_id, points=0,
                                        already_processed=True)
            ganados = int(sum((t.points_amount for t in movimientos
                               if t.sale_id == sale_id and t.transaction_type is TransactionType.EARN
                               and t.status is not TransactionStatus.REVERSED), Decimal("0")))
            quitados = int(-sum((t.points_amount for t in movimientos
                                 if t.sale_id == sale_id and t.reason_code == RETURN_REASON),
                                Decimal("0")))
            quitar = _points_to_remove_with_bonuses(
                connection, sale_id=sale_id, earned=ganados, sale_total=Decimal(str(sale_total)),
                refunded_total=Decimal(str(refunded_total)), already_removed=quitados)
            saldo = int(LoyaltyBalancePolicy.balance(movimientos))
            quitar = min(quitar, max(saldo, 0))
            if quitar <= 0:
                return LoyaltyResult.ok("No hay puntos que retirar", operation_id=operation_id,
                                        points=0)
            ajuste = LoyaltyTransaction.adjustment(
                loyalty_account_id=account.id, points_amount=Decimal(-quitar),
                operation_id=operation_id, reason_code=RETURN_REASON, source_module="sales",
                source_document_id=document_id, sale_id=sale_id, branch_id=branch_id,
                created_by_user_id=actor_user_id)
            uow.transactions.save(ajuste)
            self._emit(uow, LoyaltyEvents.POINTS_ADJUSTED, entity_id=ajuste.id,
                       operation_id=operation_id, branch_id=branch_id,
                       actor_user_id=actor_user_id, requested_by=actor_user_id,
                       points_amount=str(-quitar), reason_code=RETURN_REASON, sale_id=sale_id)
        return LoyaltyResult.ok("Puntos retirados por devolución", operation_id=operation_id,
                                points=quitar)


def _points_to_remove_with_bonuses(connection, *, sale_id: str, earned: int, sale_total: Decimal,
                                   refunded_total: Decimal, already_removed: int) -> int:
    """Devolución con reglas (decisión del usuario, 2026-10-03): la base y los
    multiplicadores se retiran EN PROPORCIÓN a lo devuelto; cada bono FIJO se
    retira completo sólo si la compra se devuelve toda o si lo que queda ya no
    cumple su condición (p. ej. queda bajo la compra mínima). Sin desglose
    guardado (ventas anteriores a las reglas) todo es proporcional, como antes."""
    import json
    from decimal import ROUND_DOWN

    from backend.domain.loyalty.services.rule_engine import (
        condition_holds_for_subtotal,
        is_fixed_bonus,
    )
    from backend.infrastructure.db.repositories.loyalty.rule_repository import (
        LoyaltyRuleRepository,
    )

    reglas = LoyaltyRuleRepository(connection)
    evaluacion = reglas.evaluation_for(sale_id)
    if evaluacion is None or earned <= 0 or sale_total <= 0:
        return LoyaltyAccrualPolicy.points_to_remove(
            earned=earned, sale_total=sale_total, refunded_total=refunded_total,
            already_removed=already_removed)
    total = refunded_total >= sale_total
    queda = max(sale_total - refunded_total, Decimal("0"))
    bonos_retirados = bonos = 0
    for aplicada in json.loads(evaluacion["breakdown_json"] or "[]"):
        regla = reglas.get(aplicada.get("rule_id")) if aplicada.get("rule_id") else None
        if regla is None or not is_fixed_bonus(regla):
            continue
        puntos = int(aplicada.get("points") or 0)
        bonos += puntos
        if total or not condition_holds_for_subtotal(regla.condition_definition, queda):
            bonos_retirados += puntos
    proporcional = max(earned - bonos, 0)
    proporcion = min(refunded_total / sale_total, Decimal("1"))
    objetivo = proporcional if total else int(
        (Decimal(proporcional) * proporcion).to_integral_value(rounding=ROUND_DOWN))
    return max(min(objetivo + bonos_retirados, earned) - already_removed, 0)


class RestoreSaleRedemptionUseCase(_LoyaltyBaseUseCase):
    """Devuelve el canje de una venta cancelada o reversada. Idempotente: un
    canje ya reversado no se vuelve a tocar."""

    def execute(self, connection, *, sale_id: str, customer_id: str | None, branch_id: str,
                actor_user_id: str, operation_id: str) -> LoyaltyResult:
        if not customer_id:
            return LoyaltyResult.ok("Venta de mostrador: sin canje", operation_id=operation_id,
                                    points=0)
        with LoyaltyUnitOfWork(connection) as uow:
            account = uow.accounts.get_by_customer_id(customer_id)
            canjes = [] if account is None else [
                t for t in uow.transactions.list_for_account(account.id)
                if t.sale_id == sale_id and t.transaction_type is TransactionType.REDEEM
                and t.status is not TransactionStatus.REVERSED]
        devueltos = 0
        for canje in canjes:
            result = ReverseLoyaltyTransactionUseCase(self._auth).execute(
                connection, transaction_id=canje.id, reason_code=RESTORE_REASON,
                actor_user_id=actor_user_id, actor_branch_id=branch_id,
                operation_id=new_uuid())
            if not result.success:
                return result
            devueltos += int(abs(canje.points_amount))
        return LoyaltyResult.ok(
            "Canje devuelto" if devueltos else "La venta no tenía canje",
            operation_id=operation_id, points=devueltos)


def _moment(occurred_at: str | None) -> datetime:
    if occurred_at:
        try:
            momento = datetime.fromisoformat(str(occurred_at))
            return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)
