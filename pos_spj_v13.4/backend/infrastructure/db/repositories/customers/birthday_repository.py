"""Persistencia del cumpleaños del cliente (2026-10-03)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from backend.domain.customers.value_objects.birthday import CustomerBirthday


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CustomerBirthdayRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def get(self, customer_id: str) -> CustomerBirthday | None:
        try:
            fila = self._conn.execute(
                "SELECT birth_month, birth_day, birth_year FROM customer_birthdays"
                " WHERE customer_id=?", (customer_id,)).fetchone()
        except sqlite3.OperationalError:
            return None
        return CustomerBirthday(int(fila[0]), int(fila[1]), fila[2]) if fila else None

    def save(self, customer_id: str, birthday: CustomerBirthday, *, actor_user_id: str) -> None:
        ahora = _now()
        self._conn.execute(
            "INSERT INTO customer_birthdays (customer_id, birth_month, birth_day, birth_year,"
            " consent_at, recorded_by_user_id, updated_at) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(customer_id) DO UPDATE SET birth_month=excluded.birth_month,"
            " birth_day=excluded.birth_day, birth_year=excluded.birth_year,"
            " recorded_by_user_id=excluded.recorded_by_user_id, updated_at=excluded.updated_at",
            (customer_id, birthday.month, birthday.day, birthday.year, ahora, actor_user_id,
             ahora))

    def delete(self, customer_id: str) -> None:
        self._conn.execute("DELETE FROM customer_birthdays WHERE customer_id=?", (customer_id,))

    def all_customer_ids(self) -> list[str]:
        try:
            return [f[0] for f in self._conn.execute("SELECT customer_id FROM customer_birthdays")]
        except sqlite3.OperationalError:
            return []

    def customers_around(self, month: int, day: int) -> list[str]:
        try:
            return [f[0] for f in self._conn.execute(
                "SELECT customer_id FROM customer_birthdays WHERE birth_month=? AND birth_day=?",
                (month, day))]
        except sqlite3.OperationalError:
            return []


__all__ = ["CustomerBirthdayRepository"]
