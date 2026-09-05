# application/idempotency_fingerprint.py — WA-10/WA-11 (§19 del prompt maestro)
"""Único punto que calcula un fingerprint de idempotencia de negocio —
determinístico sobre CONTENIDO, nunca sobre el texto del mensaje que
disparó la acción (§19: "confirmar pedido" y "sí, confirmar" deben
producir el mismo fingerprint). Usado por `order_draft_service.py`
(WA-10) y `quote_draft_service.py` (WA-11) — un solo algoritmo, no uno
por caso de uso."""
from __future__ import annotations

import hashlib


def compute_fingerprint(operation_type: str, *parts: str) -> str:
    raw = ":".join([operation_type, *parts])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
