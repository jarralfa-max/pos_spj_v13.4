"""LOY-13 — Voucher use cases: Define, Issue, Reserve, Confirm (partial or
full), Release, Reload, Adjust, Reverse, Expire (master prompt §22, phase
list "LOY-13 — Vales": Definición, Emisión, Ledger, Canje parcial, Reserva,
Reverso).

Every balance-changing use case computes the voucher's current balance via
`VoucherBalancePolicy.balance()` fresh from the ledger on every call —
mirrors LOY-6's own ledger use cases exactly, since a voucher's balance
follows the identical append-only design as the points ledger (see
`VoucherTransaction`'s own docstring).
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.commercial_instruments.dto import (
    VoucherInstanceDTO,
    VoucherTransactionDTO,
)
from backend.application.commercial_instruments.result import (
    CommercialInstrumentResult,
    fail_from_domain_error,
)
from backend.application.commercial_instruments.use_cases._base import (
    _CommercialInstrumentBaseUseCase,
)
from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.domain.commercial_instruments.entities.voucher_definition import VoucherDefinition
from backend.domain.commercial_instruments.entities.voucher_instance import VoucherInstance
from backend.domain.commercial_instruments.entities.voucher_redemption import VoucherRedemption
from backend.domain.commercial_instruments.entities.voucher_transaction import VoucherTransaction
from backend.domain.commercial_instruments.enums import VoucherInstanceStatus, VoucherType
from backend.domain.commercial_instruments.events import CommercialInstrumentEvents
from backend.domain.commercial_instruments.exceptions import (
    CommercialInstrumentDomainError,
    VoucherDefinitionNotFoundError,
    VoucherInsufficientBalanceError,
    VoucherNotFoundError,
    VoucherTransactionNotFoundError,
)
from backend.domain.loyalty.exceptions import LoyaltyDomainError
from backend.shared.ids import new_uuid
from backend.domain.commercial_instruments.policies.voucher_balance_policy import (
    VoucherBalancePolicy,
)
from backend.infrastructure.db.repositories.commercial_instruments.unit_of_work import (
    CommercialInstrumentsUnitOfWork,
)


def _balance(uow, voucher_instance_id: str) -> Decimal:
    ledger = uow.voucher_transactions.list_for_instance(voucher_instance_id)
    return VoucherBalancePolicy.balance(ledger)


class CreateVoucherDefinitionUseCase(_CommercialInstrumentBaseUseCase):
    def execute(self, connection, *, code: str, name: str, voucher_type: VoucherType,
                actor_user_id: str, operation_id: str) -> CommercialInstrumentResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.VOUCHER_ISSUE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            try:
                definition = VoucherDefinition.create(code, name, voucher_type)
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.voucher_definitions.save(definition)
        return CommercialInstrumentResult.ok(
            "Definición de vale creada", entity_id=definition.id, operation_id=operation_id)


class IssueVoucherInstanceUseCase(_CommercialInstrumentBaseUseCase):
    def execute(
        self, connection, *, definition_id: str, code: str, amount: Decimal,
        actor_user_id: str, actor_branch_id: str, operation_id: str,
        customer_id: str | None = None, expires_at: str | None = None,
        currency_code: str = "MXN",
    ) -> CommercialInstrumentResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.VOUCHER_ISSUE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            definicion = uow.voucher_definitions.get(definition_id)
            if definicion is None:
                return fail_from_domain_error(
                    VoucherDefinitionNotFoundError(f"Definición {definition_id} no existe"),
                    operation_id=operation_id)
            if definicion.voucher_type is VoucherType.PREPAID_VOUCHER:
                # Decisión del usuario (2026-10-03): el prepagado se VENDE en caja,
                # donde el dinero entra al turno. Emitirlo aquí lo regalaría.
                return CommercialInstrumentResult.fail(
                    "El vale prepagado se vende en el punto de venta (botón «Vender vale»), "
                    "donde se cobra.", "VALIDATION", operation_id=operation_id)
            instance = VoucherInstance.issue(definition_id, code, customer_id=customer_id,
                                             expires_at=expires_at)
            uow.voucher_instances.save(instance)
            try:
                issue_txn = VoucherTransaction.issue(
                    voucher_instance_id=instance.id, amount=amount, operation_id=operation_id,
                    created_by_user_id=actor_user_id)
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.voucher_transactions.save(issue_txn)
            self._emit(
                uow, CommercialInstrumentEvents.VOUCHER_ISSUED, entity_id=instance.id,
                operation_id=operation_id, branch_id=actor_branch_id,
                actor_user_id=actor_user_id, instrument_id=instance.id,
                face_value=str(amount), currency_code=currency_code, customer_id=customer_id,
                source_module="commercial_instruments",
            )
        return CommercialInstrumentResult.ok(
            "Vale emitido", entity_id=instance.id, operation_id=operation_id,
            instance=VoucherInstanceDTO.from_entity(instance, amount))


class ReserveVoucherAmountUseCase(_CommercialInstrumentBaseUseCase):
    def execute(
        self, connection, *, voucher_instance_id: str, amount: Decimal, sale_id: str,
        actor_branch_id: str, operation_id: str,
    ) -> CommercialInstrumentResult:
        if amount <= 0:
            return fail_from_domain_error(
                CommercialInstrumentDomainError("El monto a reservar debe ser positivo"),
                operation_id=operation_id)
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            instance = uow.voucher_instances.get(voucher_instance_id)
            if instance is None:
                return fail_from_domain_error(
                    VoucherNotFoundError(f"Vale {voucher_instance_id} no existe"),
                    operation_id=operation_id)
            balance = _balance(uow, voucher_instance_id)
            if balance < amount:
                return fail_from_domain_error(
                    VoucherInsufficientBalanceError(
                        f"Saldo insuficiente: disponible {balance}, solicitado {amount}"),
                    operation_id=operation_id)
            try:
                instance.reserve(sale_id)
                reservation = VoucherTransaction.reserve(
                    voucher_instance_id=voucher_instance_id, amount=-amount,
                    operation_id=operation_id, sale_id=sale_id)
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.voucher_instances.save(instance)
            uow.voucher_transactions.save(reservation)
            self._emit(uow, CommercialInstrumentEvents.VOUCHER_RESERVED, entity_id=reservation.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_branch_id, voucher_instance_id=voucher_instance_id)
        return CommercialInstrumentResult.ok(
            "Vale reservado", entity_id=reservation.id, operation_id=operation_id,
            transaction=VoucherTransactionDTO.from_entity(reservation))


class ConfirmVoucherRedemptionUseCase(_CommercialInstrumentBaseUseCase):
    def execute(
        self, connection, *, reservation_transaction_id: str, redeemed_by_user_id: str,
        actor_branch_id: str, operation_id: str, currency_code: str = "MXN",
    ) -> CommercialInstrumentResult:
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            reservation = uow.voucher_transactions.get(reservation_transaction_id)
            if reservation is None:
                return fail_from_domain_error(
                    VoucherTransactionNotFoundError(
                        f"Transacción {reservation_transaction_id} no existe"),
                    operation_id=operation_id)
            instance = uow.voucher_instances.get(reservation.voucher_instance_id)
            try:
                reservation.mark_consumed()
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.voucher_transactions.save(reservation)
            remaining = _balance(uow, instance.id)
            try:
                instance.mark_redeemed(fully=(remaining == 0))
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.voucher_instances.save(instance)
            amount_applied = -reservation.amount
            redemption = VoucherRedemption.record(
                instance.id, reservation.sale_id, amount_applied, redeemed_by_user_id)
            uow.voucher_redemptions.add(redemption)
            self._emit(
                uow, CommercialInstrumentEvents.VOUCHER_REDEEMED, entity_id=instance.id,
                operation_id=operation_id, branch_id=actor_branch_id,
                actor_user_id=redeemed_by_user_id, instrument_id=instance.id,
                redeemed_value=str(amount_applied), currency_code=currency_code,
                redemption_id=redemption.id,
            )
        return CommercialInstrumentResult.ok(
            "Canje de vale confirmado", entity_id=instance.id, operation_id=operation_id,
            instance=VoucherInstanceDTO.from_entity(instance, remaining))


class ReleaseVoucherReservationUseCase(_CommercialInstrumentBaseUseCase):
    """Restores the instance to ACTIVE if it has never had a real
    redemption yet, or PARTIALLY_REDEEMED if at least one prior redemption
    exists — determined by whether any `VoucherRedemption` audit row
    already exists for this instance (not by balance level, since a
    voucher can legitimately sit at its full original balance while still
    being "partially redeemed" in spirit after a reload, e.g.)."""

    def execute(self, connection, *, reservation_transaction_id: str, actor_branch_id: str,
                operation_id: str, actor_user_id: str) -> CommercialInstrumentResult:
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            reservation = uow.voucher_transactions.get(reservation_transaction_id)
            if reservation is None:
                return fail_from_domain_error(
                    VoucherTransactionNotFoundError(
                        f"Transacción {reservation_transaction_id} no existe"),
                    operation_id=operation_id)
            instance = uow.voucher_instances.get(reservation.voucher_instance_id)
            try:
                release = VoucherTransaction.release_of(reservation, operation_id=operation_id,
                                                        created_by_user_id=actor_user_id)
                reservation.cancel_reservation()
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.voucher_transactions.save(reservation)
            uow.voucher_transactions.save(release)

            has_prior_redemption = len(
                uow.voucher_redemptions.list_for_instance(instance.id)) > 0
            restore_status = (VoucherInstanceStatus.PARTIALLY_REDEEMED if has_prior_redemption
                              else VoucherInstanceStatus.ACTIVE)
            try:
                instance.release(restore_status=restore_status)
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.voucher_instances.save(instance)
            balance = _balance(uow, instance.id)
            self._emit(uow, CommercialInstrumentEvents.VOUCHER_RELEASED, entity_id=release.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id, voucher_instance_id=instance.id)
        return CommercialInstrumentResult.ok(
            "Reserva de vale liberada", entity_id=release.id, operation_id=operation_id,
            instance=VoucherInstanceDTO.from_entity(instance, balance))


class RefundToVoucherUseCase(_CommercialInstrumentBaseUseCase):
    """Devuelve al vale lo que una devolución o un reverso de venta regresa por
    ese medio (2026-10-03). Lo dispara Ventas por el bus (delegado del cajero);
    idempotente por documento: un reintento no abona dos veces."""

    def execute(self, connection, *, voucher_instance_id: str, amount: Decimal, sale_id: str,
                document_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> CommercialInstrumentResult:
        if amount <= 0:
            return CommercialInstrumentResult.ok("Nada que abonar", operation_id=operation_id)
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            instance = uow.voucher_instances.get(voucher_instance_id)
            if instance is None:
                return fail_from_domain_error(
                    VoucherNotFoundError(f"Vale {voucher_instance_id} no existe"),
                    operation_id=operation_id)
            motivo = f"SALE_REFUND:{document_id}"
            if any(t.reason_code == motivo
                   for t in uow.voucher_transactions.list_for_instance(instance.id)):
                return CommercialInstrumentResult.ok("Abono ya registrado (idempotente)",
                                                     entity_id=instance.id,
                                                     operation_id=operation_id)
            try:
                instance.restore_after_refund()
                abono = VoucherTransaction.refund_for_sale(
                    Decimal(str(amount)), voucher_instance_id=instance.id, sale_id=sale_id,
                    document_id=document_id, operation_id=operation_id,
                    created_by_user_id=actor_user_id)
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.voucher_instances.save(instance)
            uow.voucher_transactions.save(abono)
            self._emit(uow, CommercialInstrumentEvents.VOUCHER_RELEASED, entity_id=abono.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id, voucher_instance_id=instance.id,
                       refunded_amount=str(amount), sale_id=sale_id)
        return CommercialInstrumentResult.ok("Abonado al vale", entity_id=instance.id,
                                             operation_id=operation_id)


class PreparePrepaidVoucherForSaleUseCase(_CommercialInstrumentBaseUseCase):
    """Vale PREPAGADO vendido en caja (decisión del usuario, 2026-10-03): se
    crea sin saldo y sin poder usarse, ligado a la venta; al cobrarse la venta
    se activa con su saldo (`ActivatePrepaidVouchersForSaleUseCase`)."""

    def execute(self, connection, *, definition_id: str, code: str, sale_id: str,
                actor_branch_id: str, operation_id: str,
                customer_id: str | None = None) -> CommercialInstrumentResult:
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            definicion = uow.voucher_definitions.get(definition_id)
            if definicion is None:
                return fail_from_domain_error(
                    VoucherDefinitionNotFoundError(f"Definición {definition_id} no existe"),
                    operation_id=operation_id)
            if definicion.voucher_type is not VoucherType.PREPAID_VOUCHER or not definicion.active:
                return CommercialInstrumentResult.fail(
                    "Sólo un vale PREPAGADO activo se vende en caja", "VALIDATION",
                    operation_id=operation_id)
            try:
                instancia = VoucherInstance.prepare_for_sale(
                    definition_id, code, sale_id=sale_id, customer_id=customer_id)
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.voucher_instances.save(instancia)
        return CommercialInstrumentResult.ok("Vale preparado", entity_id=instancia.id,
                                             operation_id=operation_id, code=instancia.code)


class ActivatePrepaidVouchersForSaleUseCase(_CommercialInstrumentBaseUseCase):
    """Al cobrarse la venta: cada vale prepagado vendido recibe su saldo (ISSUE
    con la venta) y queda usable; los preparados que salieron del ticket se
    anulan. Idempotente."""

    def execute(self, connection, *, sale_id: str, vouchers, actor_user_id: str,
                actor_branch_id: str, customer_id: str | None = None) -> CommercialInstrumentResult:
        vendidos = {str(v["voucher_instance_id"]): Decimal(str(v["amount"])) for v in vouchers}
        activados = 0
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            for instancia in uow.voucher_instances.list_pending_for_sale(sale_id):
                monto = vendidos.get(instancia.id)
                if monto is None:
                    instancia.cancel("Salió del ticket antes de cobrar")
                    uow.voucher_instances.save(instancia)
                    continue
                instancia.activate_after_payment(customer_id=customer_id)
                uow.voucher_instances.save(instancia)
                uow.voucher_transactions.save(VoucherTransaction.issue(
                    voucher_instance_id=instancia.id, amount=monto, operation_id=new_uuid(),
                    sale_id=sale_id, created_by_user_id=actor_user_id))
                self._emit(uow, CommercialInstrumentEvents.VOUCHER_ISSUED, entity_id=instancia.id,
                           operation_id=new_uuid(), branch_id=actor_branch_id,
                           actor_user_id=actor_user_id, instrument_id=instancia.id,
                           face_value=str(monto), sale_id=sale_id,
                           source_module="sales")
                activados += 1
        return CommercialInstrumentResult.ok(f"{activados} vales activados", entity_id=sale_id)


class CancelPrepaidVouchersForSaleUseCase(_CommercialInstrumentBaseUseCase):
    """Venta cancelada (sin cobrar) o reversada: los vales prepagados que vendió
    se anulan. Uno ya usado no se anula: lo impide antes el reverso."""

    def execute(self, connection, *, sale_id: str, reason: str) -> CommercialInstrumentResult:
        anulados = 0
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            for instancia in uow.voucher_instances.list_for_sale(sale_id):
                if instancia.status in (VoucherInstanceStatus.CANCELLED,
                                        VoucherInstanceStatus.REDEEMED):
                    continue
                instancia.cancel(reason)
                uow.voucher_instances.save(instancia)
                anulados += 1
        return CommercialInstrumentResult.ok(f"{anulados} vales anulados", entity_id=sale_id)

