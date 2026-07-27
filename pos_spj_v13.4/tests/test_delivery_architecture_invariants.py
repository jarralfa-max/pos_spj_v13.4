"""Architecture guard tests for the delivery bounded context.

These tests enforce that:
- There is exactly ONE canonical DeliveryStatus enum (English values in value_objects.py)
- states.py re-exports the canonical enum without redefining it
- No Spanish status literals appear in domain/application layers
- LEGACY_STATUS_MAP is absent from value_objects.py
- SCHEDULED variant exists in the canonical enum
"""
from __future__ import annotations

import ast
import importlib
import inspect
import os
import re


# ── Helpers ──────────────────────────────────────────────────────────────────

_BASE = os.path.join(os.path.dirname(__file__), "..", "core", "delivery")
_BASE = os.path.normpath(_BASE)


def _read(relpath: str) -> str:
    return open(os.path.join(_BASE, relpath)).read()


def _domain_app_sources() -> list[tuple[str, str]]:
    """Return (relpath, source) for all .py files in domain/ and application/."""
    result = []
    for subdir in ("domain", "application"):
        dirpath = os.path.join(_BASE, subdir)
        for fname in os.listdir(dirpath):
            if fname.endswith(".py"):
                relpath = os.path.join(subdir, fname)
                result.append((relpath, _read(relpath)))
    return result


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_no_spanish_delivery_status_enum_in_states():
    """states.py must not define a DeliveryStatus class — it only re-exports."""
    src = _read("domain/states.py")
    tree = ast.parse(src)
    class_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    assert "DeliveryStatus" not in class_names, (
        "states.py must not redefine DeliveryStatus; it should re-export from value_objects"
    )


def test_no_legacy_status_map_in_value_objects():
    """value_objects.py must not contain LEGACY_STATUS_MAP."""
    src = _read("domain/value_objects.py")
    assert "LEGACY_STATUS_MAP" not in src, (
        "LEGACY_STATUS_MAP must be deleted from value_objects.py — it was a dual-source-of-truth artifact"
    )


def test_delivery_status_enum_uses_english_values():
    """All DeliveryStatus enum values must be lowercase English strings."""
    from core.delivery.domain.value_objects import DeliveryStatus
    spanish_words = {"pendiente", "preparacion", "en_ruta", "entregado", "cancelado", "programado"}
    for member in DeliveryStatus:
        assert member.value not in spanish_words, (
            f"DeliveryStatus.{member.name} has Spanish value {member.value!r}; must be English"
        )


def test_scheduled_status_exists_in_canonical_enum():
    """DeliveryStatus.SCHEDULED must exist with value 'scheduled'."""
    from core.delivery.domain.value_objects import DeliveryStatus
    assert hasattr(DeliveryStatus, "SCHEDULED"), "DeliveryStatus.SCHEDULED is missing"
    assert DeliveryStatus.SCHEDULED.value == "scheduled"


def test_states_exports_canonical_delivery_status():
    """states.py re-export of DeliveryStatus must be identical to value_objects version."""
    from core.delivery.domain import states, value_objects
    assert states.DeliveryStatus is value_objects.DeliveryStatus, (
        "states.DeliveryStatus must be the same object as value_objects.DeliveryStatus"
    )


_SPANISH_STATUS_PATTERN = re.compile(
    r"""["'](pendiente|preparacion|en_ruta|entregado|cancelado|programado|pendiente_wa|en_preparacion|en_camino)["']""",
)


def test_no_hardcoded_spanish_status_in_delivery_domain():
    """No hardcoded Spanish status strings in core/delivery/domain/ (except _SPANISH_COMPAT map in states.py)."""
    for relpath, src in _domain_app_sources():
        if "domain" not in relpath:
            continue
        # Strip comments and docstrings before checking, then strip dict literals for states.py
        src_check = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
        src_check = re.sub(r"'''.*?'''", "", src_check, flags=re.DOTALL)
        src_check = re.sub(r"#[^\n]*", "", src_check)
        if relpath == os.path.join("domain", "states.py"):
            # states.py is allowed to contain Spanish strings only inside its compat maps.
            src_check = re.sub(r"\{[^}]*\}", "", src_check)
        matches = _SPANISH_STATUS_PATTERN.findall(src_check)
        assert not matches, (
            f"{relpath}: hardcoded Spanish status strings found: {matches!r}. "
            "Use DeliveryStatus.*.value instead."
        )


def test_no_hardcoded_spanish_status_in_delivery_application():
    """No hardcoded Spanish status strings in delivery_orders context of application/."""
    for relpath, src in _domain_app_sources():
        if "application" not in relpath:
            continue
        # query_service.count_pending_whatsapp_sales queries the ventas table (different
        # bounded context) so Spanish ventas status strings there are intentional.
        if relpath.endswith("query_service.py"):
            # Only check code outside the ventas cross-context method
            start = src.find("def count_pending_whatsapp_sales")
            end = src.find("\n    def ", start + 1) if start >= 0 else -1
            src_check = (src[:start] + src[end:]) if start >= 0 and end > 0 else src
        else:
            src_check = src
        matches = _SPANISH_STATUS_PATTERN.findall(src_check)
        assert not matches, (
            f"{relpath}: hardcoded Spanish status strings found: {matches!r}. "
            "Use DeliveryStatus.*.value instead."
        )
