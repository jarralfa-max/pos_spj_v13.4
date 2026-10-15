"""Fecha de NEGOCIO de un instante guardado en UTC.

Los eventos y documentos guardan su instante en UTC ("2026-10-01T02:10:00+00:00").
Recortar los primeros 10 caracteres da el día UTC, no el del negocio: lo
capturado después de las 18:00 en México quedaba fechado al día siguiente y, el
último día del mes, el asiento caía en el periodo contable equivocado.
"""

from __future__ import annotations

from datetime import date, datetime, tzinfo


def local_business_date(timestamp: str | None, *, tz: tzinfo | None = None) -> date:
    """Día local (zona del equipo, o ``tz``) del instante; hoy si no hay o no se
    entiende. Una fecha sin hora ("2026-09-30") se toma tal cual."""
    text = str(timestamp or "").strip()
    if not text:
        return datetime.now(tz).date() if tz else date.today()
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return datetime.now(tz).date() if tz else date.today()
    if moment.tzinfo is None:
        return moment.date()
    return moment.astimezone(tz).date()


DEFAULT_BUSINESS_TIMEZONE = "America/Mexico_City"


def resolve_timezone(name: str | None) -> tzinfo:
    """Zona IANA del negocio/sucursal. Si el sistema no trae la base de zonas
    (``tzdata`` en Windows), la Ciudad de México cae a UTC-6 fijo — sin horario
    de verano desde 2022 — en vez de tratar la hora local como UTC."""
    from datetime import timedelta, timezone

    zone_name = str(name or "").strip() or DEFAULT_BUSINESS_TIMEZONE
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(zone_name)
    except Exception:
        if zone_name == DEFAULT_BUSINESS_TIMEZONE:
            return timezone(timedelta(hours=-6), "CST")
        return timezone.utc


def as_aware(moment: datetime, tz: tzinfo) -> datetime:
    """Un instante sin zona se interpreta como hora LOCAL de ``tz`` (contrato de
    captura manual); uno con zona se respeta. Nunca se etiqueta local como UTC."""
    return moment.replace(tzinfo=tz) if moment.tzinfo is None else moment
