"""Canonical UUIDv7 identity; backend is an installed runtime dependency."""
from backend.shared.ids import new_uuid

def new_id() -> str:
    return new_uuid()
