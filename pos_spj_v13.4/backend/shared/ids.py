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


# §4.1 named API — explicit UUIDv7 generation + validation.
def new_uuidv7() -> str:
    """Alias of :func:`new_uuid`: a canonical lowercase UUIDv7 string."""
    return new_uuid()


def is_uuidv7(value) -> bool:
    """True iff *value* is a canonical lowercase UUIDv7 string (version 7,
    RFC-4122 variant, hyphenated, lowercase). Non-raising probe."""
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    # Real version check (not just a pattern): must be v7, RFC-4122 variant,
    # and the exact canonical lowercase hyphenated form.
    return (parsed.version == 7
            and parsed.variant == uuid.RFC_4122
            and str(parsed) == value)


def validate_uuidv7(value: str) -> str:
    """Return *value* if it is a canonical lowercase UUIDv7, else raise ValueError.

    Rejects int-like ids ("1"), uuid4, uppercase/urn forms and any non-v7 value —
    identity must be a real UUIDv7 (REGLA CERO / §4.1), never merely TEXT."""
    if not is_uuidv7(value):
        raise ValueError(
            f"Identidad no válida: se requiere un UUIDv7 canónico en minúsculas, "
            f"recibido {value!r}")
    return value


# ── Centinelas de instalación (Plan B born-clean) ────────────────────────────
# Identidad ESTABLE de los registros semilla que toda instalación nueva crea
# (sucursal matriz y caja principal). Son UUIDs constantes con layout v7 y
# timestamp fijo documentado, NO enteros '1'. Cualquier código que asuma
# `sucursal_id == 1` está prohibido; debe resolver la sucursal real de la BD.
INSTALL_BRANCH_UUID = "01900000-0000-7000-8000-000000000001"
INSTALL_CASHBOX_UUID = "01900000-0000-7000-8000-000000000002"

# Identidad ESTABLE de la fila singleton de `installation` (SHELL-2): una
# instalación desplegada tiene un único ciclo de vida de aprovisionamiento,
# nunca uno por empresa/sucursal — igual razón que INSTALL_BRANCH_UUID.
INSTALLATION_SINGLETON_UUID = "01900000-0000-7000-8000-000000000003"

# Identidad ESTABLE de los roles del sistema. Son UUIDv7 canónicos (no enteros
# '1'..'6'): el seed de roles/rol_permisos y RBAC deben usar estas constantes
# para que Configuración → Permisos nunca reciba un role_id no-UUIDv7
# ("role_id must be a canonical lowercase UUIDv7"). El nombre del rol sigue
# siendo la referencia comercial; la identidad de dominio es este UUID.
SYSTEM_ROLE_UUIDS: dict[str, str] = {
    "admin":        "01900000-0000-7000-8000-0000000000a1",
    "gerente":      "01900000-0000-7000-8000-0000000000a2",
    "cajero":       "01900000-0000-7000-8000-0000000000a3",
    "almacen":      "01900000-0000-7000-8000-0000000000a4",
    "repartidor":   "01900000-0000-7000-8000-0000000000a5",
    "solo_lectura": "01900000-0000-7000-8000-0000000000a6",
    "delivery":     "01900000-0000-7000-8000-0000000000a7",
    "marketing":    "01900000-0000-7000-8000-0000000000a8",
    "finanzas":     "01900000-0000-7000-8000-0000000000a9",
    # SHELL-2: rol del primer propietario creado durante el provisioning —
    # distinto de "admin" (que sigue existiendo como rol operativo asignable
    # después). Acceso total, igual matriz que admin, ver migración 206.
    "system_owner": "01900000-0000-7000-8000-0000000000aa",
}


def role_uuid(nombre: str) -> str:
    """UUIDv7 canónico del rol de sistema, o uno nuevo para roles no-semilla."""
    return SYSTEM_ROLE_UUIDS.get(str(nombre or "").strip().lower(), new_uuid())
