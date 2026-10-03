"""Fidelidad → Finanzas: el efecto contable de puntos, vales, cupones y premios
de sorteo (decisión del usuario, 2026-10-03: "contabiliza los puntos, cupones,
vales, boletos y cualquier programa de fidelidad").

Antes de esto NINGÚN movimiento de Fidelidad llegaba a contabilidad: los
manejadores de Finanzas existían (`LoyaltyPointsIssuedHandler`, …) y nadie los
llamaba, y varias vías (bonos de cumpleaños, retos, referidos) ni siquiera
emitían el evento. Por eso el puente lee los LIBROS, no los eventos: todo lo
que mueve un saldo pasa por el libro, se emita o no un evento.

Reglas contables (las cuentas salen de los perfiles contables, nunca de aquí):

* **Puntos** — cada acumulación (compra, bono, ajuste a favor) se reconoce al
  valor del punto vigente: Dr contra-ingreso de fidelidad / Cr pasivo por
  puntos. Los consumos se asignan FIFO a las acumulaciones (lo mismo que
  `LoyaltyBalancePolicy.fifo_remaining`), cada uno a su valor reconocido:
  canje → Dr pasivo / Cr ingreso (el canje en una venta acredita el DESCUENTO
  que la venta ya cargó por esos puntos, no un segundo ingreso); caducidad →
  Dr pasivo / Cr ingreso por expiración; ajuste en contra, reverso de una
  acumulación o traspaso enviado → retiro (espejo del reconocimiento). Un
  apartado (RESERVE) separa sus puntos y no asienta nada hasta confirmarse;
  si se libera, los devuelve. Un reverso a favor (venta cancelada) deshace el
  asiento del canje original.
* **Vales** — emisión/recarga reconocen el pasivo según su naturaleza; canje
  confirmado → Dr pasivo / Cr ingreso; caducidad → breakage; vale cancelado o
  vencido con saldo → se libera lo pendiente. El vale PREPAGADO no se
  reconoce sin perfil (exigiría un cobro que el sistema no registra).
* **Cupones** — no crean pasivo. Su efecto es el descuento que la venta ya
  asentó; el puente lo RECLASIFICA a "contra-ingreso por cupones" (o a cuenta
  por cobrar al proveedor si el cupón lo financia él).
* **Sorteos** — al activar la campaña se provisiona el costo estimado de cada
  premio (Dr gasto promocional / Cr provisión); al entregarlo, la provisión se
  usa; cancelada o resuelta la campaña, se libera lo que quede. Los boletos
  NO se venden en este sistema (no hay cobro): no tienen asiento propio; un
  boleto canjeado por puntos es un canje de puntos.

Idempotente y reintentable: cada movimiento deja su renglón en
`loyalty_finance_links`; uno fallido (sin perfil, periodo cerrado) queda
FAILED, detiene SÓLO su cuenta de puntos (el orden FIFO importa) y se
reintenta en la siguiente pasada.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

from backend.application.loyalty.queries.redemption_preview_query import (
    LoyaltyRedemptionPreviewQuery,
)
from backend.application.services.finance.commercial_instrument_processor import (
    CommercialInstrumentProcessor,
)
from backend.application.services.finance.finance_bootstrap import (
    ensure_finance_catalog_additions,
)
from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.enums import (
    CommercialInstrumentType,
    JournalType,
    PostingPurpose,
)
from backend.domain.finance.exceptions import PostingProfileNotFoundError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.infrastructure.db.repositories.loyalty.finance_link_repository import (
    LoyaltyFinanceLinkRepository,
)
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.loyalty.finance")

_CENT = Decimal("0.01")
_POINTS = CommercialInstrumentType.LOYALTY_POINTS
_PRIZE = CommercialInstrumentType.SWEEPSTAKES_PRIZE

_CREDIT_TYPES = frozenset({"EARN", "BONUS", "TRANSFER_IN"})
#: Débitos que retiran lo reconocido (no son canje ni caducidad).
_WITHDRAW_TYPES = frozenset({"TRANSFER_OUT"})

#: Tipo de vale → naturaleza contable del instrumento.
VOUCHER_INSTRUMENT = {
    "REFUND_VOUCHER": CommercialInstrumentType.REFUND_VOUCHER,
    "COMPENSATION_VOUCHER": CommercialInstrumentType.REFUND_VOUCHER,
    "STORE_CREDIT": CommercialInstrumentType.STORE_CREDIT,
    "PROMOTIONAL_VOUCHER": CommercialInstrumentType.PROMOTIONAL_BALANCE,
    "EMPLOYEE_AUTHORIZED_VOUCHER": CommercialInstrumentType.PROMOTIONAL_BALANCE,
    "PREPAID_VOUCHER": CommercialInstrumentType.PREPAID_VOUCHER,
    "SUPPLIER_FUNDED_VOUCHER": CommercialInstrumentType.THIRD_PARTY_VOUCHER,
}


class LoyaltyFinancePostingStatus(str, Enum):
    POSTED = "POSTED"
    HELD = "HELD"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class LoyaltyFinanceSourceType(str, Enum):
    LOYALTY_TRANSACTION = "LOYALTY_TRANSACTION"
    VOUCHER_TRANSACTION = "VOUCHER_TRANSACTION"
    VOUCHER_INSTANCE = "VOUCHER_INSTANCE"
    COUPON_REDEMPTION = "COUPON_REDEMPTION"
    SWEEPSTAKES_PRIZE = "SWEEPSTAKES_PRIZE"
    SWEEPSTAKES_WINNER = "SWEEPSTAKES_WINNER"


def _dec(value) -> Decimal:
    return Decimal(str(value if value not in (None, "") else "0"))


def _money(value: Decimal, currency: str = "MXN") -> Money:
    return Money(Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP), currency)


def _day(iso: str | None) -> date:
    if iso:
        try:
            return date.fromisoformat(str(iso)[:10])
        except ValueError:
            pass
    return datetime.now(timezone.utc).date()


@dataclass
class LoyaltyFinanceSummary:
    ready: bool = True
    posted: int = 0
    held: int = 0
    skipped: int = 0
    failed: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"ready": self.ready, "posted": self.posted, "held": self.held,
                "skipped": self.skipped, "failed": self.failed, "warnings": list(self.warnings)}


class _Hold(Exception):
    """El movimiento todavía no tiene efecto definitivo (apartado sin confirmar,
    acreditación diferida): se reintenta en la siguiente pasada."""


class _Skip(Exception):
    """El movimiento no tiene efecto contable."""


class LoyaltyFinancePostingService:
    def __init__(self, connection, *, point_value: Decimal | None = None) -> None:
        self._conn = connection
        self._links = LoyaltyFinanceLinkRepository(connection)
        self._processor = CommercialInstrumentProcessor()
        self._engine = PostingEngine()
        self._point_value = point_value

    # ── entrada ───────────────────────────────────────────────────────────
    def run(self, *, limit: int = 2000) -> LoyaltyFinanceSummary:
        summary = LoyaltyFinanceSummary()
        if not ensure_finance_catalog_additions(self._conn):
            # Finanzas aún no tiene catálogo: nada se puede asentar todavía; lo
            # pendiente se asentará cuando exista (el puente lee los libros).
            summary.ready = False
            return summary
        if not self._links.schema_ready():
            # La migración 294 crea el estado del puente; sin ella no hay dónde
            # registrar lo asentado y asentar sin registro duplicaría.
            logger.warning("Fidelidad→Finanzas: falta la migración 294")
            summary.ready = False
            return summary
        self._points(summary, limit)
        self._vouchers(summary, limit)
        self._closed_vouchers(summary)
        self._coupons(summary, limit)
        self._sweepstakes(summary)
        return summary

    # ── unidad de trabajo por movimiento ──────────────────────────────────
    def _apply(self, summary: LoyaltyFinanceSummary, key: str, source_type: str,
               source_id: str, action) -> bool:
        """Ejecuta `action(uow)` y su renglón de estado en UNA transacción."""
        try:
            with FinanceUnitOfWork(self._conn) as uow:
                # HELD y SKIPPED también confirman: un apartado guarda (o
                # anula) sus puntos separados aunque todavía no asiente nada.
                try:
                    result = action(uow)
                    estado = "POSTED"
                except _Hold as hold:
                    result, estado = (Decimal("0"), str(hold)), "HELD"
                except _Skip as skip:
                    result, estado = (Decimal("0"), str(skip)), "SKIPPED"
                amount, detail = result if isinstance(result, tuple) else (result, "")
                self._links.save_link(key, source_type, source_id, estado,
                                      amount=amount or "0", detail=detail)
            if estado == "POSTED":
                summary.posted += 1
                if detail:
                    summary.warnings.append(detail)
            elif estado == "HELD":
                summary.held += 1
            else:
                summary.skipped += 1
            return True
        except Exception as exc:  # noqa: BLE001 - queda FAILED y se reintenta
            logger.warning("Fidelidad→Finanzas: %s %s no se asentó: %s",
                           source_type, source_id, exc)
            self._links.save_link(key, source_type, source_id, "FAILED",
                                  detail=f"{type(exc).__name__}: {exc}")
            self._conn.commit()
            summary.failed += 1
            return False

    # ══ PUNTOS ═════════════════════════════════════════════════════════════
    def _unit_value(self) -> Decimal:
        if self._point_value is None:
            self._point_value = LoyaltyRedemptionPreviewQuery(self._conn).settings().point_value
        return max(self._point_value, Decimal("0"))

    def _points(self, summary: LoyaltyFinanceSummary, limit: int) -> None:
        detenidas: set[str] = set()
        for txn in self._links.pending_point_transactions(limit):
            cuenta = txn["loyalty_account_id"]
            if cuenta in detenidas:
                continue
            ok = self._apply(summary, f"points:{txn['id']}", "LOYALTY_TRANSACTION", txn["id"],
                             lambda uow, t=txn: self._point_effect(uow, t))
            if not ok:
                # FIFO: un movimiento sin asentar cambia a qué acumulación se
                # asignan los siguientes de la misma cuenta.
                detenidas.add(cuenta)

    def _point_effect(self, uow, txn: dict):
        tipo = txn["transaction_type"]
        puntos = _dec(txn["points_amount"])
        if tipo == "RELEASE":
            raise _Skip("Liberación de apartado: la resuelve el apartado")
        if tipo in _CREDIT_TYPES or (tipo == "ADJUSTMENT" and puntos > 0):
            return self._recognize_credit(uow, txn)
        if tipo == "RESERVE":
            return self._reservation(uow, txn)
        if tipo == "REDEEM":
            return self._consume(uow, txn, -puntos, kind="REDEEM")
        if tipo == "EXPIRE":
            return self._consume(uow, txn, -puntos, kind="EXPIRE",
                                 first_credit=txn.get("source_document_id"))
        if tipo in _WITHDRAW_TYPES or (tipo == "ADJUSTMENT" and puntos < 0):
            return self._consume(uow, txn, -puntos, kind="WITHDRAW")
        if tipo == "REVERSAL":
            return self._reversal(uow, txn)
        raise _Skip(f"Movimiento {tipo} sin efecto contable")

    def _recognize_credit(self, uow, txn: dict):
        if txn["status"] == "PENDING":
            raise _Hold("Acreditación diferida: se reconoce al quedar disponible")
        puntos = _dec(txn["points_amount"])
        valor = self._unit_value()
        importe = (puntos * valor).quantize(_CENT, rounding=ROUND_HALF_UP)
        self._links.save_credit(txn["id"], txn["loyalty_account_id"], puntos, valor, importe,
                                txn["created_at"])
        self._processor.recognize(
            uow, instrument_type=_POINTS, source_module="loyalty",
            source_instrument_id=txn["id"], amount=_money(importe),
            on_date=_day(txn["created_at"]), operation_id=new_uuid(),
            customer_id=txn.get("customer_id"), branch_id=txn.get("branch_id"),
            expires_at=txn.get("expires_at"))
        return importe

    # ── asignación FIFO ───────────────────────────────────────────────────
    def _remaining(self, credit: dict) -> tuple[Decimal, Decimal]:
        usados = self._links.active_allocations_for_credit(credit["credit_transaction_id"])
        puntos = _dec(credit["points"]) - sum((_dec(a["points"]) for a in usados), Decimal("0"))
        importe = _dec(credit["amount"]) - sum((_dec(a["amount"]) for a in usados), Decimal("0"))
        return puntos, importe

    def _allocate(self, txn: dict, points: Decimal, kind: str,
                  first_credit: str | None = None) -> tuple[list[dict], Decimal]:
        """Separa `points` de las acumulaciones de la cuenta, la más vieja
        primero (o primero de `first_credit`). Devuelve las asignaciones y lo
        que faltó (puntos sin respaldo contable)."""
        creditos = self._links.credits_for_account(txn["loyalty_account_id"])
        if first_credit:
            creditos.sort(key=lambda c: c["credit_transaction_id"] != first_credit)
        asignadas: list[dict] = []
        falta = points
        for credito in creditos:
            if falta <= 0:
                break
            quedan_puntos, quedan_importe = self._remaining(credito)
            if quedan_puntos <= 0:
                continue
            toma = min(falta, quedan_puntos)
            if toma == quedan_puntos:
                importe = quedan_importe
            else:
                importe = min(quedan_importe, (toma * _dec(credito["unit_value"])).quantize(
                    _CENT, rounding=ROUND_HALF_UP))
            allocation_id = self._links.add_allocation(
                txn["id"], credito["credit_transaction_id"], toma, importe, kind)
            asignadas.append({"id": allocation_id,
                              "credit_transaction_id": credito["credit_transaction_id"],
                              "points": toma, "amount": importe, "kind": kind})
            falta -= toma
        return asignadas, max(falta, Decimal("0"))

    def _post_allocation(self, uow, txn: dict, allocation: dict) -> None:
        importe = _dec(allocation["amount"])
        if importe <= 0:
            return
        kind = allocation["kind"]
        fecha = _day(txn["created_at"])
        if kind == "REDEEM":
            self._processor.redeem(
                uow, instrument_type=_POINTS,
                source_instrument_id=allocation["credit_transaction_id"],
                amount=_money(importe), on_date=fecha, operation_id=new_uuid(),
                redemption_id=allocation["id"],
                credit_account_id=self._sale_discount_account(uow, fecha)
                if txn.get("sale_id") else None)
        else:
            self._processor.release(
                uow, instrument_type=_POINTS,
                source_instrument_id=allocation["credit_transaction_id"],
                amount=_money(importe), on_date=fecha, operation_id=new_uuid(),
                release_id=allocation["id"], breakage=(kind == "EXPIRE"))

    def _consume(self, uow, txn: dict, points: Decimal, *, kind: str,
                 first_credit: str | None = None):
        if points <= 0:
            raise _Skip("Movimiento sin puntos")
        asignadas, falta = self._allocate(txn, points, kind, first_credit)
        for allocation in asignadas:
            self._post_allocation(uow, txn, allocation)
        total = sum((a["amount"] for a in asignadas), Decimal("0"))
        aviso = (f"{falta} puntos de {txn['id'][:8]} sin acumulación reconocida"
                 if falta > 0 else "")
        return total, aviso

    def _reservation(self, uow, txn: dict):
        estado = txn["status"]
        retenidas = self._links.allocations_for_debit(txn["id"], kinds=("HOLD",))
        if (not retenidas and estado != "CANCELLED"
                and not self._links.allocations_for_debit(txn["id"])):
            retenidas, _ = self._allocate(txn, -_dec(txn["points_amount"]), "HOLD")
        if estado == "RESERVED":
            raise _Hold("Apartado sin confirmar")
        if estado == "CONSUMED":
            for allocation in retenidas:
                self._links.set_allocation_kind(allocation["id"], "REDEEM")
                self._post_allocation(uow, txn, {**allocation, "kind": "REDEEM"})
            return sum((_dec(a["amount"]) for a in retenidas), Decimal("0"))
        for allocation in retenidas:
            self._links.void_allocation(allocation["id"])
        raise _Skip("Apartado liberado: los puntos vuelven a su acumulación")

    def _reversal(self, uow, txn: dict):
        puntos = _dec(txn["points_amount"])
        original = self._links.reversed_original(txn["id"])
        if puntos < 0:
            # Reverso de una acumulación: se retira de esa acumulación primero.
            return self._consume(uow, txn, -puntos, kind="WITHDRAW",
                                 first_credit=original["id"] if original else None)
        if original is None:
            return self._recognize_credit(uow, txn)
        restaurado = Decimal("0")
        fecha = _day(txn["created_at"])
        consumos = self._links.allocations_for_debit(original["id"])
        for allocation in consumos:
            importe = _dec(allocation["amount"])
            if allocation["kind"] != "HOLD" and importe > 0:
                credito = allocation["credit_transaction_id"]
                if allocation["kind"] == "REDEEM":
                    clave = f"{_POINTS.value}:{credito}:redeem:{allocation['id']}"
                    proposito = PostingPurpose.INSTRUMENT_REDEMPTION
                else:
                    clave = f"{_POINTS.value}:{credito}:release:{allocation['id']}"
                    proposito = (PostingPurpose.INSTRUMENT_EXPIRATION
                                 if allocation["kind"] == "EXPIRE"
                                 else PostingPurpose.INSTRUMENT_REVERSAL)
                self._processor.restore(
                    uow, instrument_type=_POINTS, source_instrument_id=credito,
                    amount=_money(importe), on_date=fecha, operation_id=new_uuid(),
                    effect_key=clave, effect_purpose=proposito,
                    from_redeemed=allocation["kind"] == "REDEEM",
                    reason=f"Reverso de puntos {txn['id'][:8]}")
                restaurado += importe
            self._links.void_allocation(allocation["id"])
        if not consumos:
            # El débito original no consumió acumulaciones reconocidas: los
            # puntos que vuelven se reconocen como acumulación nueva.
            return self._recognize_credit(uow, txn)
        return restaurado

    def _sale_discount_account(self, uow, on_date: date) -> str:
        perfil = uow.posting_profiles.find_effective("SALE", on_date)
        if perfil is None:
            raise PostingProfileNotFoundError("No hay perfil contable SALE vigente")
        return perfil.account_for("discount_account_id")

    # ══ VALES ══════════════════════════════════════════════════════════════
    def _vouchers(self, summary: LoyaltyFinanceSummary, limit: int) -> None:
        detenidos: set[str] = set()
        for txn in self._links.pending_voucher_transactions(limit):
            vale = txn["voucher_instance_id"]
            if vale in detenidos:
                continue
            if not self._apply(summary, f"voucher:{txn['id']}", "VOUCHER_TRANSACTION", txn["id"],
                               lambda uow, t=txn: self._voucher_effect(uow, t)):
                detenidos.add(vale)

    @staticmethod
    def _voucher_type(row: dict) -> CommercialInstrumentType:
        try:
            return VOUCHER_INSTRUMENT[str(row["voucher_type"])]
        except KeyError:
            raise _Skip(f"Tipo de vale sin naturaleza contable: {row['voucher_type']}") from None

    def _voucher_effect(self, uow, txn: dict):
        tipo = txn["transaction_type"]
        importe = _dec(txn["amount"])
        instrumento = self._voucher_type(txn)
        fecha = _day(txn["created_at"])
        vale = txn["voucher_instance_id"]
        if tipo == "ISSUE":
            self._processor.recognize(
                uow, instrument_type=instrumento, source_module="commercial_instruments",
                source_instrument_id=vale, amount=_money(importe), on_date=fecha,
                operation_id=new_uuid(), customer_id=txn.get("customer_id"),
                expires_at=txn.get("expires_at"))
            return importe
        if tipo in ("RELOAD", "REFUND") or (tipo == "ADJUSTMENT" and importe > 0):
            self._processor.reload(uow, instrument_type=instrumento, source_instrument_id=vale,
                                   amount=_money(importe), on_date=fecha,
                                   operation_id=new_uuid())
            return importe
        if tipo == "RELEASE":
            raise _Skip("Liberación de apartado: la resuelve el apartado")
        if tipo == "RESERVE":
            if txn["status"] == "RESERVED":
                raise _Hold("Apartado de vale sin confirmar")
            if txn["status"] != "CONSUMED":
                raise _Skip("Apartado de vale liberado")
            tipo = "REDEEM"
        if tipo == "REDEEM":
            self._processor.redeem(uow, instrument_type=instrumento, source_instrument_id=vale,
                                   amount=_money(-importe), on_date=fecha,
                                   operation_id=new_uuid(), redemption_id=txn["id"])
            return -importe
        if tipo == "EXPIRE" or (tipo == "ADJUSTMENT" and importe < 0):
            self._processor.release(uow, instrument_type=instrumento, source_instrument_id=vale,
                                    amount=_money(-importe), on_date=fecha,
                                    operation_id=new_uuid(), release_id=txn["id"],
                                    breakage=(tipo == "EXPIRE"))
            return -importe
        if tipo == "REVERSAL":
            original = self._links.voucher_reversed_original(txn["id"])
            if original is None:
                raise _Skip("Reverso de vale sin movimiento original")
            if original["transaction_type"] in ("REDEEM", "RESERVE"):
                clave = f"{instrumento.value}:{vale}:redeem:{original['id']}"
                self._processor.restore(
                    uow, instrument_type=instrumento, source_instrument_id=vale,
                    amount=_money(abs(importe)), on_date=fecha, operation_id=new_uuid(),
                    effect_key=clave, effect_purpose=PostingPurpose.INSTRUMENT_REDEMPTION,
                    from_redeemed=True, reason="Reverso de canje de vale")
            elif importe < 0:
                self._processor.release(uow, instrument_type=instrumento,
                                        source_instrument_id=vale, amount=_money(-importe),
                                        on_date=fecha, operation_id=new_uuid(),
                                        release_id=txn["id"], breakage=False)
            else:
                clave = f"{instrumento.value}:{vale}:release:{original['id']}"
                self._processor.restore(
                    uow, instrument_type=instrumento, source_instrument_id=vale,
                    amount=_money(importe), on_date=fecha, operation_id=new_uuid(),
                    effect_key=clave,
                    effect_purpose=(PostingPurpose.INSTRUMENT_EXPIRATION
                                    if original["transaction_type"] == "EXPIRE"
                                    else PostingPurpose.INSTRUMENT_REVERSAL),
                    from_redeemed=False, reason="Reverso de movimiento de vale")
            return abs(importe)
        raise _Skip(f"Movimiento de vale {tipo} sin efecto contable")

    def _closed_vouchers(self, summary: LoyaltyFinanceSummary) -> None:
        """Un vale cancelado o vencido SIN movimiento de libro conserva saldo
        reconocido: se libera (vencido → breakage; cancelado → retiro)."""
        for row in self._links.closed_voucher_instances():
            self._apply(summary, f"voucher-close:{row['id']}", "VOUCHER_INSTANCE", row["id"],
                        lambda uow, r=row: self._close_voucher(uow, r))

    def _close_voucher(self, uow, row: dict):
        instrumento = self._voucher_type(row)
        obligacion = uow.commercial_obligations.find_by_instrument(instrumento, row["id"])
        if obligacion is None or not obligacion.outstanding_amount.is_positive():
            raise _Skip("Sin saldo reconocido pendiente")
        pendiente = obligacion.outstanding_amount
        self._processor.release(
            uow, instrument_type=instrumento, source_instrument_id=row["id"], amount=pendiente,
            on_date=datetime.now(timezone.utc).date(), operation_id=new_uuid(),
            release_id=f"close:{row['id']}", breakage=row["status"] == "EXPIRED")
        return pendiente.amount

    # ══ CUPONES ════════════════════════════════════════════════════════════
    def _coupons(self, summary: LoyaltyFinanceSummary, limit: int) -> None:
        for row in self._links.pending_coupon_redemptions(limit):
            self._apply(summary, f"coupon:{row['id']}", "COUPON_REDEMPTION", row["id"],
                        lambda uow, r=row: self._coupon_effect(uow, r))

    def _coupon_effect(self, uow, row: dict):
        importe = _dec(row["amount_applied"])
        if importe <= 0:
            raise _Skip("Canje de cupón sin importe")
        if not row.get("sale_id"):
            raise _Skip("Canje sin venta: el descuento lo asienta el documento que lo aplicó")
        fecha = _day(row["redeemed_at"])
        perfil = uow.posting_profiles.find_effective(
            CommercialInstrumentType.PROMOTIONAL_COUPON.value, fecha,
            instrument_type=CommercialInstrumentType.PROMOTIONAL_COUPON)
        if perfil is None:
            raise PostingProfileNotFoundError("No hay perfil contable PROMOTIONAL_COUPON vigente")
        financiado = str(row.get("coupon_type")) == "SUPPLIER_FUNDED"
        cargo = perfil.account_for("third_party_receivable_account_id" if financiado
                                   else "contra_revenue_account_id")
        monto = _money(importe)
        self._engine.post(
            uow, JournalType.COMMERCIAL_INSTRUMENTS, fecha,
            f"Cupón en venta {str(row['sale_id'])[:8]}",
            PostingReference("commercial_instruments", f"COUPON:{row['id']}",
                             PostingPurpose.INSTRUMENT_REDEMPTION, new_uuid()),
            [LineSpec(cargo, debit=monto,
                      description=("Cupón financiado por proveedor (por cobrar)" if financiado
                                   else "Reclasificación a contra-ingreso por cupones")),
             LineSpec(self._sale_discount_account(uow, fecha), credit=monto,
                      description="Descuento de la venta aplicado por cupón")],
            currency_code=monto.currency_code)
        return importe

    # ══ SORTEOS ════════════════════════════════════════════════════════════
    def _sweepstakes(self, summary: LoyaltyFinanceSummary) -> None:
        for prize in self._links.prizes_to_provision():
            self._apply(summary, f"prize:{prize['id']}", "SWEEPSTAKES_PRIZE", prize["id"],
                        lambda uow, p=prize: self._provision_prize(uow, p))
        for winner in self._links.delivered_winners():
            self._apply(summary, f"winner:{winner['id']}", "SWEEPSTAKES_WINNER", winner["id"],
                        lambda uow, w=winner: self._deliver_prize(uow, w))
        for prize in self._links.prizes_to_release():
            self._apply(summary, f"prize-release:{prize['id']}", "SWEEPSTAKES_PRIZE",
                        prize["id"], lambda uow, p=prize: self._release_prize(uow, p))

    def _provision_prize(self, uow, prize: dict):
        importe = _dec(prize["estimated_cost"]) * _dec(prize["quantity"] or 1)
        if importe <= 0:
            raise _Skip("Premio sin costo estimado: no hay nada que provisionar")
        self._processor.recognize(
            uow, instrument_type=_PRIZE, source_module="sweepstakes",
            source_instrument_id=prize["id"], amount=_money(importe),
            on_date=datetime.now(timezone.utc).date(), operation_id=new_uuid(),
            branch_id=prize.get("branch_id"), campaign_id=prize.get("campaign_id"))
        return importe

    def _deliver_prize(self, uow, winner: dict):
        obligacion = uow.commercial_obligations.find_by_instrument(_PRIZE, winner["prize_id"])
        if obligacion is None:
            raise _Skip("Premio sin provisión (sin costo estimado)")
        importe = min(_money(_dec(winner["estimated_cost"])), obligacion.outstanding_amount)
        if not importe.is_positive():
            raise _Skip("La provisión del premio ya está agotada")
        fecha = _day(winner.get("delivered_at"))
        perfil = uow.posting_profiles.find_effective(_PRIZE.value, fecha, instrument_type=_PRIZE)
        if perfil is None:
            raise PostingProfileNotFoundError("No hay perfil contable SWEEPSTAKES_PRIZE vigente")
        self._processor.redeem(
            uow, instrument_type=_PRIZE, source_instrument_id=winner["prize_id"],
            amount=importe, on_date=fecha, operation_id=new_uuid(),
            redemption_id=winner["id"],
            credit_account_id=perfil.account_for("expense_account_id"))
        return importe.amount

    def _release_prize(self, uow, prize: dict):
        obligacion = uow.commercial_obligations.find_by_instrument(_PRIZE, prize["id"])
        if obligacion is None or not obligacion.outstanding_amount.is_positive():
            raise _Skip("Provisión del premio sin saldo")
        pendiente = obligacion.outstanding_amount
        self._processor.release(
            uow, instrument_type=_PRIZE, source_instrument_id=prize["id"], amount=pendiente,
            on_date=datetime.now(timezone.utc).date(), operation_id=new_uuid(),
            release_id=f"campaign:{prize['campaign_id']}", breakage=False,
            description=f"Liberación de provisión de premio {prize['id'][:8]}")
        return pendiente.amount


def post_loyalty_finance(connection) -> dict:
    """Atajo para los puntos de disparo (tras una venta, tras un comando de
    Fidelidad, al abrir Fidelidad). Nunca propaga: un fallo queda FAILED."""
    try:
        return LoyaltyFinancePostingService(connection).run().as_dict()
    except Exception:  # noqa: BLE001 - la operación de origen ya se confirmó
        logger.exception("Fidelidad→Finanzas: la pasada no pudo completarse")
        return {"ready": False, "error": True}


__all__ = ["LoyaltyFinancePostingService", "LoyaltyFinancePostingStatus",
           "LoyaltyFinanceSourceType", "LoyaltyFinanceSummary", "VOUCHER_INSTRUMENT",
           "post_loyalty_finance"]
