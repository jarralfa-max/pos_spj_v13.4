"""DateInput / DateTimeInput (FASE DS-4) — canonical date & datetime fields."""

from __future__ import annotations

from datetime import date, datetime

from PyQt5.QtCore import QDate, QDateTime
from PyQt5.QtWidgets import QDateEdit, QDateTimeEdit

_DATE_FORMAT = "dd/MM/yyyy"
_DATETIME_FORMAT = "dd/MM/yyyy HH:mm"


class DateInput(QDateEdit):
    def __init__(self, parent=None, *, default_today: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("dateInput")
        self.setDisplayFormat(_DATE_FORMAT)
        self.setCalendarPopup(True)
        if default_today:
            self.setDate(QDate.currentDate())

    def date_value(self) -> date:
        d = self.date()
        return date(d.year(), d.month(), d.day())

    def set_date_value(self, value: date | None) -> None:
        if value is None:
            return
        self.setDate(QDate(value.year, value.month, value.day))


class DateTimeInput(QDateTimeEdit):
    def __init__(self, parent=None, *, default_now: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("dateTimeInput")
        self.setDisplayFormat(_DATETIME_FORMAT)
        self.setCalendarPopup(True)
        if default_now:
            self.setDateTime(QDateTime.currentDateTime())

    def datetime_value(self) -> datetime:
        return self.dateTime().toPyDateTime()

    def set_datetime_value(self, value: datetime | None) -> None:
        if value is None:
            return
        self.setDateTime(QDateTime(value))
