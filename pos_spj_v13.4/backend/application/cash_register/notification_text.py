"""Texto legible de los avisos de Caja (CASH-26 bloque 2, 2026-10-07).

Hasta hoy el aviso era «Caja · CASH_DIFFERENCE_DETECTED» con la carga del
evento como JSON crudo (UUIDs incluidos), también por WhatsApp. Aquí se
traduce cada evento alertable a un título y un cuerpo que una persona entiende
sin abrir el sistema; los identificadores se sustituyen por folio y nombre.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Callable

#: Eventos que tiene sentido avisar, con su nombre para la persona.
ALERTABLE_EVENTS = {
    "CASH_DIFFERENCE_DETECTED": "Diferencia en Corte Z",
    "CASH_Z_CUT_GENERATED": "Corte Z generado",
    "CASH_HARDWARE_OPERATION_FAILED": "Falla de cajón o impresora",
    "CASH_HANDOVER_DISPUTED": "Entrega de valores con diferencia",
    "CASH_SHIFT_FORCE_CLOSED": "Turno cerrado a la fuerza",
}

_SEVERITY = {"REVIEW": "requiere revisión", "CRITICAL": "CRÍTICA",
             "TOLERATED": "dentro de tolerancia"}
_HARDWARE = {"OPEN_DRAWER": "abrir el cajón", "PRINT": "imprimir", "CHARGE": "cobrar con terminal"}

Lookup = Callable[[str | None], str]


def money(value: object) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value or "")
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def describe_cash_event(event_name: str, payload: dict, *, user_name: Lookup,
                        cut_folio: Lookup) -> tuple[str, str]:
    label = ALERTABLE_EVENTS.get(event_name, "Aviso de Caja")
    title = f"Caja · {label}"
    if event_name == "CASH_DIFFERENCE_DETECTED":
        amount = Decimal(str(payload.get("amount") or "0"))
        tipo = "Sobrante" if amount > 0 else "Faltante"
        lines = [
            f"{tipo} de {money(abs(amount))} en el corte {cut_folio(payload.get('z_cut_id'))}.",
            f"Cajero: {user_name(payload.get('responsible_user_id'))}.",
            f"Severidad: {_SEVERITY.get(str(payload.get('severity')), payload.get('severity'))}.",
        ]
        if int(payload.get("recurrence_count") or 1) > 1:
            lines.append(f"Es su diferencia número {payload['recurrence_count']} en el periodo.")
        return title, "\n".join(lines)
    if event_name == "CASH_Z_CUT_GENERATED":
        return title, "\n".join([
            f"Corte {payload.get('document_number') or ''} cerrado.",
            f"Esperado {money(payload.get('expected_cash'))}, contado "
            f"{money(payload.get('counted_cash'))}, diferencia {money(payload.get('difference'))}.",
        ])
    if event_name == "CASH_HARDWARE_OPERATION_FAILED":
        accion = _HARDWARE.get(str(payload.get("command")), "operar el dispositivo")
        return title, f"No se pudo {accion} ({payload.get('error_code') or 'sin código'})."
    if event_name == "CASH_HANDOVER_DISPUTED":
        return title, (f"Se entregaron {money(payload.get('expected_amount'))} y se recibieron "
                       f"{money(payload.get('received_amount'))}.")
    return title, "Revisa el detalle en Caja."
