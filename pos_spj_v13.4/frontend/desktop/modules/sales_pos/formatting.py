"""Formato de presentación compartido por los diálogos del POS."""

from __future__ import annotations

from datetime import datetime


def local_time(stamp: str | None) -> str:
    """"2026-10-02T13:09:00+00:00" → hora LOCAL "2026-10-02 07:09". Las marcas
    se guardan en UTC; mostrarlas tal cual le daba al cajero la hora de otro
    huso."""
    if not stamp:
        return ""
    try:
        moment = datetime.fromisoformat(str(stamp))
    except ValueError:
        return str(stamp)[:16].replace("T", " ")
    if moment.tzinfo is not None:
        moment = moment.astimezone()
    return moment.strftime("%Y-%m-%d %H:%M")
