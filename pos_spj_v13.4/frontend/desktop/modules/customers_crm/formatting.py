"""Formato de fechas e importes para Clientes y CRM (CRM-43).

El dominio guarda instantes en UTC ISO-8601 con zona (``…+00:00``); la
pantalla los muestra en hora LOCAL y los formularios convierten la hora local
capturada a UTC antes de enviarla. Una fecha sin hora (``2026-10-08``) se
muestra tal cual: no tiene zona que convertir.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from frontend.desktop.formatters.date_formatter import format_date
from frontend.desktop.formatters.money_formatter import format_money


def to_utc_iso(value: datetime) -> str:
    """Hora local capturada (ingenua) → ISO UTC con zona, a segundos."""
    if value.tzinfo is None:
        value = value.astimezone()  # interpreta la ingenua como hora local
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_instant(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone()


def fmt_datetime(value) -> str:
    """``2026-10-08T21:30:00+00:00`` → ``08/10/2026 15:30`` (hora local)."""
    if isinstance(value, str) and len(value) == 10:
        return format_date(value)
    moment = parse_instant(value)
    if moment is None:
        return "—"
    return f"{moment.day:02d}/{moment.month:02d}/{moment.year} {moment.hour:02d}:{moment.minute:02d}"


def fmt_date(value) -> str:
    if value in (None, ""):
        return "—"
    if isinstance(value, date) and not isinstance(value, datetime):
        return format_date(value)
    if isinstance(value, str) and len(value) == 10:
        return format_date(value)
    moment = parse_instant(value)
    return format_date(moment.date()) if moment else "—"


def fmt_money(value) -> str:
    return format_money(value) if value not in (None, "") else "—"


def fmt_percent(value) -> str:
    return "—" if value is None else f"{int(value)}%"


def local_now() -> datetime:
    return datetime.now().astimezone()
