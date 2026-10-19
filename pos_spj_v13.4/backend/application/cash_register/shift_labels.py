"""Etiqueta legible de un turno de Caja (auditoría de Caja CJA-05, cierre de
pendientes 2026-10-16): «Caja Principal · Juan Pérez · 16/10 09:00».

Las pantallas mostraban `TUR-1A2B3C` (los últimos 6 caracteres del UUID): ni
único ni reconocible para el cajero. El UUID queda como clave interna."""

from __future__ import annotations


def shift_labels(connection, shift_ids) -> dict[str, str]:
    ids = sorted({str(i) for i in shift_ids if i})
    if not ids or connection is None:
        return {}
    marks = ",".join("?" for _ in ids)
    try:
        tables = {r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        users = "usuarios" in tables
        rows = connection.execute(
            "SELECT s.id, COALESCE(r.name,''), s.opened_at, "
            + ("COALESCE(NULLIF(trim(u.nombre),''), u.usuario, '')" if users else "''")
            + " FROM cash_shifts s LEFT JOIN cash_registers r ON r.id=s.register_id "
            + ("LEFT JOIN usuarios u ON u.id=s.cashier_user_id " if users else "")
            + f"WHERE s.id IN ({marks})", tuple(ids)).fetchall()
    except Exception:  # noqa: BLE001 - base sin Caja: sin etiqueta
        return {}
    labels = {}
    for shift_id, register, opened, cashier in rows:
        opened = str(opened or "")
        when = f"{opened[8:10]}/{opened[5:7]} {opened[11:16]}" if len(opened) >= 16 else opened
        labels[str(shift_id)] = " · ".join(p for p in (register, cashier, when) if p) or "Turno"
    return labels


def shift_label(connection, shift_id: str | None) -> str:
    return shift_labels(connection, [shift_id]).get(str(shift_id or ""), "Turno") if shift_id \
        else "Sin turno"
