# utils/operation_context.py — SPJ POS v13.1
"""
Contexto de operación thread-local (no variable global compartida).
Antes: _current_operation_id era variable de módulo — dos hilos la pisaban mutuamente.
Ahora: threading.local() garantiza un valor por hilo.
"""
from __future__ import annotations
import threading
import uuid
from datetime import datetime, timezone

_local = threading.local()


def generate_operation_id() -> str:
    """Genera un ID único para una operación (UUID + timestamp)."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"OP-{ts}-{uuid.uuid4().hex[:8].upper()}"


def set_operation_id(op_id: str | None = None) -> str:
    """Establece el ID de operación para el hilo actual."""
    _local.operation_id = op_id or generate_operation_id()
    return _local.operation_id


def get_operation_id() -> str | None:
    """Retorna el ID de operación del hilo actual (None si no hay ninguno)."""
    return getattr(_local, "operation_id", None)


def clear_operation_id() -> None:
    """Limpia el ID de operación del hilo actual."""
    _local.operation_id = None


def now_iso() -> str:
    """Timestamp ISO 8601 UTC para logs y eventos."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
