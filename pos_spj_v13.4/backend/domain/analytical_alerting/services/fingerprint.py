"""Alert fingerprinting (§49, BI-20) — the dedup key.

Deliberately a plain composite string, not a cryptographic hash — the 3
components (`alert_type`, `branch_id`, `target_id`) are exactly what makes
two alerts "the same recurring problem" per §49, and keeping them visible in
the fingerprint itself makes debugging a dedup decision trivial (no hash to
reverse).
"""

from __future__ import annotations

from backend.domain.analytical_alerting.enums import AlertType


def build_fingerprint(alert_type: AlertType, branch_id: str, target_id: str) -> str:
    if not branch_id or not target_id:
        raise ValueError("build_fingerprint requires non-empty branch_id and target_id")
    return f"{alert_type.value}:{branch_id}:{target_id}"
