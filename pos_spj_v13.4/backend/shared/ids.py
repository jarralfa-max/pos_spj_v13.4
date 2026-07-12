"""Canonical UUIDv7 identity generation for the SPJ backend."""

from __future__ import annotations

import secrets
import threading
import time
import uuid

_monotonic_lock = threading.Lock()
_last_value = 0


def _uuid7_fallback() -> uuid.UUID:
    """Return a UUIDv7 value when the runtime does not expose uuid.uuid7().

    Garantiza monotonicidad dentro del proceso: dos UUIDs generados en el
    mismo milisegundo conservan orden lexicográfico == orden de generación.
    Los checkpoints incrementales (p. ej. loyalty_snapshots.ultimo_evento_id)
    dependen de esta propiedad.
    """
    global _last_value

    timestamp_ms = time.time_ns() // 1_000_000
    if timestamp_ms >= 1 << 48:
        raise OverflowError("UUIDv7 timestamp exceeds 48 bits")

    random_bits = secrets.randbits(74)
    rand_a = (random_bits >> 62) & 0x0FFF
    rand_b = random_bits & ((1 << 62) - 1)

    value = timestamp_ms << 80
    value |= 0x7 << 76
    value |= rand_a << 64
    value |= 0b10 << 62
    value |= rand_b

    with _monotonic_lock:
        if value <= _last_value:
            # Mismo milisegundo con random menor: avanzar 1 conserva
            # versión/variant (solo crece rand_b; overflow es teórico).
            value = _last_value + 1
        _last_value = value
    return uuid.UUID(int=value)


def _uuid7() -> uuid.UUID:
    generator = getattr(uuid, "uuid7", None)
    if generator is not None:
        return generator()
    return _uuid7_fallback()


def new_uuid() -> str:
    """Return a canonical lowercase UUIDv7 string."""
    return str(_uuid7())


# ── Centinelas de instalación (Plan B born-clean) ────────────────────────────
# Identidad ESTABLE de los registros semilla que toda instalación nueva crea
# (sucursal matriz y caja principal). Son UUIDs constantes con layout v7 y
# timestamp fijo documentado, NO enteros '1'. Cualquier código que asuma
# `sucursal_id == 1` está prohibido; debe resolver la sucursal real de la BD.
INSTALL_BRANCH_UUID = "01900000-0000-7000-8000-000000000001"
INSTALL_CASHBOX_UUID = "01900000-0000-7000-8000-000000000002"
