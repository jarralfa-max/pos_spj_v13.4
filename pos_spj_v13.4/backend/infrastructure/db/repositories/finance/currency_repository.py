"""Currency and exchange-rate repository (§24)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.finance.entities.currency import Currency, ExchangeRateRecord
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase


def _currency(row: dict) -> Currency:
    return Currency(id=row["id"], code=row["code"], name=row["name"],
                    decimal_places=int(row["decimal_places"]),
                    rounding_mode=row["rounding_mode"], active=bool(row["active"]),
                    created_at=row["created_at"])


def _rate(row: dict) -> ExchangeRateRecord:
    return ExchangeRateRecord(
        id=row["id"], from_currency=row["from_currency"], to_currency=row["to_currency"],
        rate=Decimal(str(row["rate"])), effective_date=date.fromisoformat(row["effective_date"]),
        source=row["source"], created_by=row["created_by"], created_at=row["created_at"])


class CurrencyRepository(FinanceRepositoryBase):
    def save(self, currency: Currency) -> None:
        self._insert("currencies", {
            "id": currency.id, "code": currency.code, "name": currency.name,
            "decimal_places": currency.decimal_places, "rounding_mode": currency.rounding_mode,
            "active": int(currency.active), "created_at": currency.created_at})

    def get_by_code(self, code: str) -> Currency | None:
        row = self._query_one("SELECT * FROM currencies WHERE code=?", ((code or "").upper(),))
        return _currency(row) if row else None

    def list_active(self) -> list[Currency]:
        return [_currency(r) for r in
                self._query("SELECT * FROM currencies WHERE active=1 ORDER BY code")]

    def save_rate(self, record: ExchangeRateRecord) -> None:
        self._insert("exchange_rates", {
            "id": record.id, "from_currency": record.from_currency,
            "to_currency": record.to_currency, "rate": format(record.rate, "f"),
            "effective_date": record.effective_date.isoformat(), "source": record.source,
            "created_by": record.created_by, "created_at": record.created_at})

    def rate_on(self, from_currency: str, to_currency: str,
                on_date: date) -> ExchangeRateRecord | None:
        """Tipo vigente: el de la fecha más reciente que no sea posterior a ``on_date``."""
        row = self._query_one(
            "SELECT * FROM exchange_rates WHERE from_currency=? AND to_currency=?"
            " AND effective_date<=? ORDER BY effective_date DESC LIMIT 1",
            (from_currency.upper(), to_currency.upper(), on_date.isoformat()))
        return _rate(row) if row else None

    def list_rates(self, limit: int = 200) -> list[ExchangeRateRecord]:
        return [_rate(r) for r in self._query(
            "SELECT * FROM exchange_rates ORDER BY effective_date DESC LIMIT ?", (limit,))]
