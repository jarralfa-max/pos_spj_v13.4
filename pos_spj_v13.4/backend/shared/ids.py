"""Canonical UUIDv7 identity generation for the SPJ backend."""

from __future__ import annotations

import secrets
import time
import uuid


def _uuid7_fallback() -> uuid.UUID:
    """Return a UUIDv7 value when the runtime does not expose uuid.uuid7()."""
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
    return uuid.UUID(int=value)


def _uuid7() -> uuid.UUID:
    generator = getattr(uuid, "uuid7", None)
    if generator is not None:
        return generator()
    return _uuid7_fallback()


def new_uuid() -> str:
    """Return a canonical lowercase UUIDv7 string."""
    return str(_uuid7())
