"""Registros del módulo de Fidelidad para las pantallas (LOY-29).

Hasta LOY-28 las pantallas sólo podían leer lo que un caso de uso de escritura
necesitaba (p. ej. `programs.list_active()`), así que "Programas" mostraba sólo
los ACTIVOS y el botón "Aprobar" nunca encontraba un borrador que aprobar; las
demás rutas eran un letrero de "en construcción".

Una consulta por pantalla, cada una con SU permiso de lectura (§59): el permiso
se valida aquí, en el backend, no sólo ocultando el botón.

* Los saldos (puntos por cuenta, saldo de cada vale) se derivan del libro con
  la política de dominio (`LoyaltyBalancePolicy`, `VoucherBalancePolicy`), nunca
  con un SUM en SQL que duplicaría la regla (§11, §22).
* Los indicadores del resumen (§64) se calculan aquí; la UI sólo los pinta.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Mapping

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.permissions import LoyaltyPermissions as LP
from backend.application.loyalty_cards.authorization import LoyaltyCardsAuthorizationPolicy
from backend.application.loyalty_cards.permissions import LoyaltyCardsPermissions as CP
from backend.domain.commercial_instruments.policies.voucher_balance_policy import (
    VoucherBalancePolicy,
)
from backend.domain.loyalty.enums import TransactionType
from backend.domain.loyalty.policies.balance_policy import LoyaltyBalancePolicy
from backend.infrastructure.db.repositories.commercial_instruments.voucher_repository import (
    VoucherTransactionRepository,
)
from backend.infrastructure.db.repositories.loyalty.transaction_repository import (
    LoyaltyTransactionRepository,
)
from backend.infrastructure.db.repositories.loyalty_records import specs
from backend.infrastructure.db.repositories.loyalty_records.engine import (
    RecordPage,
    RecordPageReader,
    RecordSpec,
)


class LoyaltyRecord(str, Enum):
    PROGRAMS = "programs"
    MEMBERSHIPS = "memberships"
    ACCOUNTS = "accounts"
    LEDGER = "ledger"
    TIERS = "tiers"
    REWARDS = "rewards"
    REWARD_REDEMPTIONS = "reward_redemptions"
    CHALLENGES = "challenges"
    REFERRALS = "referrals"
    CAMPAIGNS = "campaigns"
    RETENTION_CAMPAIGNS = "retention_campaigns"
    BIRTHDAYS = "birthdays"
    FRAUD_CASES = "fraud_cases"
    LOYALTY_AUDIT = "loyalty_audit"
    FINANCE_POSTINGS = "finance_postings"
    COUPON_DEFINITIONS = "coupon_definitions"
    COUPONS = "coupons"
    VOUCHER_DEFINITIONS = "voucher_definitions"
    VOUCHERS = "vouchers"
    SWEEPSTAKES_CAMPAIGNS = "sweepstakes_campaigns"
    SWEEPSTAKES_ENTRIES = "sweepstakes_entries"
    SWEEPSTAKES_TICKETS = "sweepstakes_tickets"
    SWEEPSTAKES_PRIZES = "sweepstakes_prizes"
    SWEEPSTAKES_DRAWS = "sweepstakes_draws"
    SWEEPSTAKES_WINNERS = "sweepstakes_winners"
    CARDS = "cards"
    CARD_REPLACEMENTS = "card_replacements"
    CARD_ASSIGNMENTS = "card_assignments"
    CARD_TEMPLATES = "card_templates"
    CARD_TEMPLATE_VERSIONS = "card_template_versions"
    CARD_SHEETS = "card_sheets"
    CARD_IMPOSITIONS = "card_impositions"
    CARD_BATCHES = "card_batches"
    CARD_PRINT_JOBS = "card_print_jobs"
    CARD_REPRINTS = "card_reprints"
    DIGITAL_CARDS = "digital_cards"
    CARD_AUDIT = "card_audit"


R = LoyaltyRecord

#: Especificación de lectura y permiso de cada registro.
_REGISTROS: dict[LoyaltyRecord, tuple[RecordSpec, str]] = {
    R.PROGRAMS: (specs.PROGRAMS, LP.PROGRAM_VIEW),
    R.MEMBERSHIPS: (specs.MEMBERSHIPS, LP.MEMBERSHIP_VIEW),
    R.ACCOUNTS: (specs.ACCOUNTS, LP.POINTS_VIEW),
    R.LEDGER: (specs.LEDGER, LP.POINTS_VIEW),
    R.TIERS: (specs.TIERS, LP.TIER_VIEW),
    R.REWARDS: (specs.REWARDS, LP.REWARD_VIEW),
    R.REWARD_REDEMPTIONS: (specs.REWARD_REDEMPTIONS, LP.REWARD_VIEW),
    R.CHALLENGES: (specs.CHALLENGES, LP.CHALLENGE_VIEW),
    R.REFERRALS: (specs.REFERRALS, LP.REFERRAL_VIEW),
    R.CAMPAIGNS: (specs.CAMPAIGNS, LP.CAMPAIGN_VIEW),
    R.RETENTION_CAMPAIGNS: (specs.RETENTION_CAMPAIGNS, LP.RETENTION_VIEW),
    R.BIRTHDAYS: (specs.BIRTHDAYS, LP.BIRTHDAY_VIEW),
    R.FRAUD_CASES: (specs.FRAUD_CASES, LP.FRAUD_VIEW),
    R.LOYALTY_AUDIT: (specs.LOYALTY_AUDIT, LP.AUDIT_VIEW),
    R.FINANCE_POSTINGS: (specs.FINANCE_POSTINGS, LP.AUDIT_VIEW),
    R.COUPON_DEFINITIONS: (specs.COUPON_DEFINITIONS, LP.COUPON_VIEW),
    R.COUPONS: (specs.COUPONS, LP.COUPON_VIEW),
    R.VOUCHER_DEFINITIONS: (specs.VOUCHER_DEFINITIONS, LP.VOUCHER_VIEW),
    R.VOUCHERS: (specs.VOUCHERS, LP.VOUCHER_VIEW),
    R.SWEEPSTAKES_CAMPAIGNS: (specs.SWEEPSTAKES_CAMPAIGNS, LP.SWEEPSTAKES_VIEW),
    R.SWEEPSTAKES_ENTRIES: (specs.SWEEPSTAKES_ENTRIES, LP.SWEEPSTAKES_VIEW),
    R.SWEEPSTAKES_TICKETS: (specs.SWEEPSTAKES_TICKETS, LP.SWEEPSTAKES_VIEW),
    R.SWEEPSTAKES_PRIZES: (specs.SWEEPSTAKES_PRIZES, LP.SWEEPSTAKES_VIEW),
    R.SWEEPSTAKES_DRAWS: (specs.SWEEPSTAKES_DRAWS, LP.SWEEPSTAKES_VIEW),
    R.SWEEPSTAKES_WINNERS: (specs.SWEEPSTAKES_WINNERS, LP.SWEEPSTAKES_VIEW),
    R.CARDS: (specs.CARDS, CP.CARD_VIEW),
    R.CARD_REPLACEMENTS: (specs.CARD_REPLACEMENTS, CP.CARD_VIEW),
    R.CARD_ASSIGNMENTS: (specs.CARD_ASSIGNMENTS, CP.CARD_VIEW),
    R.CARD_TEMPLATES: (specs.CARD_TEMPLATES, CP.TEMPLATE_VIEW),
    R.CARD_TEMPLATE_VERSIONS: (specs.CARD_TEMPLATE_VERSIONS, CP.TEMPLATE_VIEW),
    R.CARD_SHEETS: (specs.CARD_SHEETS, CP.VIEW),
    R.CARD_IMPOSITIONS: (specs.CARD_IMPOSITIONS, CP.VIEW),
    R.CARD_BATCHES: (specs.CARD_BATCHES, CP.VIEW),
    R.CARD_PRINT_JOBS: (specs.CARD_PRINT_JOBS, CP.VIEW),
    R.CARD_REPRINTS: (specs.CARD_REPRINTS, CP.VIEW),
    R.DIGITAL_CARDS: (specs.DIGITAL_CARDS, CP.CARD_VIEW),
    R.CARD_AUDIT: (specs.CARD_AUDIT, CP.AUDIT_VIEW),
}

PAGE_SIZE = 50


@dataclass(frozen=True)
class LoyaltyAlert:
    severity: str          # "warning" | "danger" | "info"
    area: str
    message: str
    count: int
    route_id: str


@dataclass(frozen=True)
class LoyaltyOverview:
    active_members: int
    available_points: Decimal
    expiring_points: Decimal
    redemptions_in_period: int
    active_coupons: int
    outstanding_voucher_balance: Decimal
    expiring_window_days: int


class LoyaltyRecordsQueryService:
    def __init__(
        self, connection, *, authorization: LoyaltyAuthorizationPolicy | None = None,
        cards_authorization: LoyaltyCardsAuthorizationPolicy | None = None,
    ) -> None:
        self._conn = connection
        self._reader = RecordPageReader(connection)
        self._auth = authorization or LoyaltyAuthorizationPolicy()
        self._cards_auth = cards_authorization or LoyaltyCardsAuthorizationPolicy()

    def permission_for(self, record: LoyaltyRecord) -> str:
        return _REGISTROS[LoyaltyRecord(record)][1]

    def page(self, record: LoyaltyRecord, *, actor_user_id: str, query: str = "",
             status: str | None = None, filters: Mapping[str, str] | None = None,
             page: int = 0, page_size: int = PAGE_SIZE) -> RecordPage:
        record = LoyaltyRecord(record)
        spec, permission = _REGISTROS[record]
        self._require(actor_user_id, permission)
        if record is R.FINANCE_POSTINGS and not self._reader.scalar(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
                " AND name = 'loyalty_finance_links'"):
            # Base sin la migración 294: nada contabilizado todavía.
            return RecordPage(rows=[], total=0)
        result = self._reader.page(spec, query=query, status=status, filters=filters,
                                   limit=page_size, offset=max(page, 0) * page_size)
        if record is R.ACCOUNTS:
            return RecordPage(rows=[self._with_points(r) for r in result.rows], total=result.total)
        if record is R.VOUCHERS:
            return RecordPage(rows=[self._with_voucher_balance(r) for r in result.rows],
                              total=result.total)
        return result

    def overview(self, *, actor_user_id: str, now: datetime | None = None,
                 expiring_window_days: int = 30) -> LoyaltyOverview:
        self._require(actor_user_id, LP.DASHBOARD_VIEW)
        momento = now or datetime.now(timezone.utc)
        hasta = (momento + timedelta(days=expiring_window_days)).isoformat(timespec="seconds")
        inicio_mes = momento.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        repo = LoyaltyTransactionRepository(self._conn)
        cuentas = [r[0] for r in self._conn.execute(
            "SELECT id FROM loyalty_accounts WHERE status = 'ACTIVE'").fetchall()]
        disponibles = Decimal("0")
        por_expirar = Decimal("0")
        for cuenta in cuentas:
            movimientos = repo.list_for_account(cuenta)
            disponibles += max(LoyaltyBalancePolicy.balance(movimientos), Decimal("0"))
            for credito in movimientos:
                if (credito.transaction_type in (TransactionType.EARN, TransactionType.BONUS)
                        and credito.expires_at and credito.expires_at <= hasta
                        and credito.expires_at >= momento.isoformat(timespec="seconds")):
                    por_expirar += LoyaltyBalancePolicy.fifo_remaining(credito, movimientos)
        canjes = int(self._reader.scalar(
            "SELECT COUNT(*) FROM loyalty_transactions WHERE transaction_type = ?"
            " AND created_at >= ?",
            (TransactionType.REDEEM.value, inicio_mes.isoformat(timespec="seconds"))) or 0)
        cupones = int(self._reader.scalar(
            "SELECT COUNT(*) FROM coupon_instances WHERE status IN ('ISSUED', 'ACTIVE')") or 0)
        vales = VoucherTransactionRepository(self._conn)
        saldo_vales = Decimal("0")
        for (vale_id,) in self._conn.execute(
                "SELECT id FROM voucher_instances WHERE status IN"
                " ('ISSUED', 'ACTIVE', 'PARTIALLY_REDEEMED', 'RESERVED')").fetchall():
            saldo_vales += VoucherBalancePolicy.balance(vales.list_for_instance(vale_id))
        return LoyaltyOverview(
            active_members=len(cuentas), available_points=disponibles,
            expiring_points=por_expirar, redemptions_in_period=canjes,
            active_coupons=cupones, outstanding_voucher_balance=saldo_vales,
            expiring_window_days=expiring_window_days)

    def cards_overview(self, *, actor_user_id: str) -> dict[str, int]:
        """Conteos del resumen de Tarjetas: por estado, lotes por aprobar e
        impresiones fallidas. Mismos estados que filtran sus listas."""
        self._require(actor_user_id, CP.VIEW)
        por_estado = {estado: int(n) for estado, n in self._conn.execute(
            "SELECT status, COUNT(*) FROM loyalty_cards GROUP BY status").fetchall()}
        return {
            "unassigned": por_estado.get("UNASSIGNED", 0),
            "active": por_estado.get("ACTIVE", 0),
            "issued": por_estado.get("ISSUED", 0),
            "blocked": por_estado.get("BLOCKED", 0),
            "replaced": por_estado.get("REPLACED", 0),
            "batches_pending": int(self._reader.scalar(
                "SELECT COUNT(*) FROM loyalty_card_batches WHERE status = 'PENDING_APPROVAL'")
                or 0),
            "print_failed": int(self._reader.scalar(
                "SELECT COUNT(*) FROM loyalty_card_print_jobs WHERE status = 'FAILED'") or 0),
        }

    def alerts(self, *, actor_user_id: str, now: datetime | None = None,
               expiring_window_days: int = 7) -> list[LoyaltyAlert]:
        """Lo que pide que alguien haga algo, con la pantalla donde se atiende.

        Cada alerta es un conteo sobre el mismo estado que muestra la lista de
        esa pantalla: el aviso y la lista no pueden decir cosas distintas.
        """
        self._require(actor_user_id, LP.DASHBOARD_VIEW)
        momento = now or datetime.now(timezone.utc)
        hasta = (momento + timedelta(days=expiring_window_days)).isoformat(timespec="seconds")
        ahora = momento.isoformat(timespec="seconds")

        def contar(sql: str, params: tuple = ()) -> int:
            return int(self._reader.scalar(sql, params) or 0)

        candidatos = (
            ("warning", "Programas", "programas esperan aprobación o activación",
             contar("SELECT COUNT(*) FROM loyalty_program_definitions"
                    " WHERE status = 'PENDING_APPROVAL'"), "loyalty.programs"),
            ("warning", "Campañas", "campañas esperan aprobación",
             contar("SELECT COUNT(*) FROM loyalty_campaigns WHERE status = 'PENDING_APPROVAL'"),
             "loyalty.campaigns"),
            ("danger", "Antifraude", "casos de fraude abiertos o en revisión",
             contar("SELECT COUNT(*) FROM loyalty_fraud_cases"
                    " WHERE status IN ('OPEN', 'UNDER_REVIEW')"), "fidelidad.fraud"),
            ("info", "Puntos", f"acumulaciones vencen en los próximos {expiring_window_days} días",
             contar("SELECT COUNT(*) FROM loyalty_transactions WHERE transaction_type IN"
                    " ('EARN', 'BONUS') AND expires_at IS NOT NULL AND expires_at >= ?"
                    " AND expires_at <= ?", (ahora, hasta)), "loyalty.points"),
            ("danger", "Contabilidad", "movimientos de fidelidad no se pudieron contabilizar",
             contar("SELECT COUNT(*) FROM loyalty_finance_links WHERE status = 'FAILED'")
             if self._reader.scalar("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
                                    " AND name = 'loyalty_finance_links'") else 0,
             "fidelidad.accounting"),
            ("warning", "Sorteos", "campañas de sorteo esperan aprobación",
             contar("SELECT COUNT(*) FROM sweepstakes_campaigns WHERE status = 'PENDING_APPROVAL'"),
             "sweepstakes.campaigns"),
            ("warning", "Sorteos", "ganadores por validar",
             contar("SELECT COUNT(*) FROM sweepstakes_winners WHERE status = 'PENDING_VALIDATION'"),
             "sweepstakes.draws"),
            ("warning", "Tarjetas", "plantillas esperan aprobación",
             contar("SELECT COUNT(*) FROM loyalty_card_templates WHERE status = 'PENDING_APPROVAL'"),
             "cards.templates"),
            ("warning", "Tarjetas", "lotes esperan aprobación",
             contar("SELECT COUNT(*) FROM loyalty_card_batches WHERE status = 'PENDING_APPROVAL'"),
             "cards.batches"),
            ("danger", "Tarjetas", "trabajos de impresión fallaron",
             contar("SELECT COUNT(*) FROM loyalty_card_print_jobs WHERE status = 'FAILED'"),
             "cards.printing"),
        )
        return [LoyaltyAlert(severity=sev, area=area, message=msg, count=n, route_id=ruta)
                for sev, area, msg, n, ruta in candidatos if n > 0]

    # ── internos ───────────────────────────────────────────────────────────
    def _require(self, actor_user_id: str, permission: str) -> None:
        if permission.startswith("TARJETAS_FIDELIDAD."):
            self._cards_auth.require(actor_user_id, permission)
        else:
            self._auth.require(actor_user_id, permission)

    def _with_points(self, row: dict) -> dict:
        movimientos = LoyaltyTransactionRepository(self._conn).list_for_account(row["id"])
        return {**row, "points": LoyaltyBalancePolicy.balance(movimientos),
                "reserved": LoyaltyBalancePolicy.reserved_amount(movimientos)}

    def _with_voucher_balance(self, row: dict) -> dict:
        movimientos = VoucherTransactionRepository(self._conn).list_for_instance(row["id"])
        return {**row, "balance": VoucherBalancePolicy.balance(movimientos)}


__all__ = ["LoyaltyAlert", "LoyaltyOverview", "LoyaltyRecord", "LoyaltyRecordsQueryService", "PAGE_SIZE"]
