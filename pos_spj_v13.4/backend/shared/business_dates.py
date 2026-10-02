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
