"""311 — fecha de negocio de los turnos ya abiertos (§33).

Hasta el 2026-10-07 `cash_shifts.business_date` quedaba siempre NULL (la
columna y su índice existían desde la 175, nadie la escribía). Desde hoy el
turno la recibe al abrir —el día LOCAL de la apertura— y el Corte Z la usa para
fechar su asiento. Esta migración la completa para los turnos anteriores con
la misma regla (`backend/shared/business_dates.py`): la base real tenía un
turno abierto desde el 2026-09-25.
"""

from __future__ import annotations

from backend.shared.business_dates import local_business_date


def run(conn) -> None:
    if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cash_shifts'"
    ).fetchone() is None:
        return
    pendientes = conn.execute(
        "SELECT id, opened_at FROM cash_shifts WHERE business_date IS NULL").fetchall()
    for shift_id, opened_at in pendientes:
        conn.execute("UPDATE cash_shifts SET business_date=? WHERE id=?",
                     (local_business_date(opened_at).isoformat(), shift_id))
    conn.commit()


up = run
