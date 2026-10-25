"""Tax configuration repository (§22): códigos, tasas con vigencia, reglas y cuentas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.finance.entities.tax import TaxCode, TaxPostingProfile, TaxRate, TaxRule
from backend.domain.finance.enums import TaxDirection, TaxKind
from backend.infrastructure.db.repositories.finance.base import (
    FinanceRepositoryBase,
    iso,
    parse_date,
)


def _code(row: dict) -> TaxCode:
    return TaxCode(id=row["id"], code=row["code"], name=row["name"],
                   kind=TaxKind(row["kind"]), direction=TaxDirection(row["direction"]),
                   active=bool(row["active"]), created_at=row["created_at"])


def _rate(row: dict) -> TaxRate:
    return TaxRate(id=row["id"], tax_code_id=row["tax_code_id"],
                   rate_percent=Decimal(str(row["rate_percent"])),
                   effective_from=date.fromisoformat(row["effective_from"]),
                   effective_to=parse_date(row["effective_to"]), created_at=row["created_at"])


def _rule(row: dict) -> TaxRule:
    return TaxRule(id=row["id"], tax_code_id=row["tax_code_id"], scope=row["scope"],
                   scope_id=row["scope_id"],
                   effective_from=date.fromisoformat(row["effective_from"]),
                   effective_to=parse_date(row["effective_to"]), active=bool(row["active"]),
                   created_at=row["created_at"])


class TaxRepository(FinanceRepositoryBase):
    def save_code(self, tax_code: TaxCode) -> None:
        self._insert("tax_codes", {
            "id": tax_code.id, "code": tax_code.code, "name": tax_code.name,
            "kind": tax_code.kind.value, "direction": tax_code.direction.value,
            "active": int(tax_code.active), "created_at": tax_code.created_at})

    def get_code(self, tax_code_id: str) -> TaxCode | None:
        row = self._query_one("SELECT * FROM tax_codes WHERE id=?", (tax_code_id,))
        return _code(row) if row else None

    def get_code_by_code(self, code: str) -> TaxCode | None:
        row = self._query_one("SELECT * FROM tax_codes WHERE code=?", ((code or "").upper(),))
        return _code(row) if row else None

    def list_codes(self) -> list[TaxCode]:
        return [_code(r) for r in self._query("SELECT * FROM tax_codes ORDER BY code")]

    def save_rate(self, rate: TaxRate) -> None:
        self._insert("tax_rates", {
            "id": rate.id, "tax_code_id": rate.tax_code_id,
            "rate_percent": format(rate.rate_percent, "f"),
            "effective_from": rate.effective_from.isoformat(),
            "effective_to": iso(rate.effective_to), "created_at": rate.created_at})

    def rate_on(self, tax_code_id: str, on_date: date) -> TaxRate | None:
        row = self._query_one(
            "SELECT * FROM tax_rates WHERE tax_code_id=? AND effective_from<=?"
            " AND (effective_to IS NULL OR effective_to>=?)"
            " ORDER BY effective_from DESC LIMIT 1",
            (tax_code_id, on_date.isoformat(), on_date.isoformat()))
        return _rate(row) if row else None

    def save_rule(self, rule: TaxRule) -> None:
        self._insert("tax_rules", {
            "id": rule.id, "tax_code_id": rule.tax_code_id, "scope": rule.scope,
            "scope_id": rule.scope_id, "effective_from": rule.effective_from.isoformat(),
            "effective_to": iso(rule.effective_to), "active": int(rule.active),
            "created_at": rule.created_at})

    def rules_on(self, on_date: date) -> list[TaxRule]:
        return [rule for rule in (_rule(r) for r in self._query(
            "SELECT * FROM tax_rules WHERE active=1")) if rule.applies_on(on_date)]

    def save_posting_profile(self, profile: TaxPostingProfile) -> None:
        self._insert("tax_posting_profiles", {
            "id": profile.id, "tax_code_id": profile.tax_code_id,
            "account_id": profile.account_id,
            "effective_from": profile.effective_from.isoformat(),
            "created_at": profile.created_at})

    def posting_account(self, tax_code_id: str, on_date: date) -> str | None:
        row = self._query_one(
            "SELECT account_id FROM tax_posting_profiles WHERE tax_code_id=?"
            " AND effective_from<=? ORDER BY effective_from DESC LIMIT 1",
            (tax_code_id, on_date.isoformat()))
        return row["account_id"] if row else None
