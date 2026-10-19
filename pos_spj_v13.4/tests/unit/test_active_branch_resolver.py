# tests/unit/test_active_branch_resolver.py
"""Tests for ActiveBranchResolver.

Coverage:
 - ActiveBranchResolver resolution rules (tests 01-16)
 - Architecture guards (tests 28-32)

2026-10-16: removed tests 17-27 — they covered the legacy `core.session_context`,
`core.events.domain_events` and a copy of the deleted MainWindow's
`_leer_sucursal_instalacion`, all gone with `core/`.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from backend.application.services.active_branch_resolver import (
    ActiveBranchNotAvailableError,
    ActiveBranchResolver,
    BranchDTO,
    NoAllowedBranchesError,
    NoBranchSelectedError,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _branch(branch_id: str, name: str, is_active: bool = True) -> BranchDTO:
    return BranchDTO(branch_id=branch_id, name=name, is_active=is_active)


BRANCH_A = _branch("uuid-a-0001", "Sucursal A")
BRANCH_B = _branch("uuid-b-0002", "Sucursal B")
BRANCH_C = _branch("uuid-c-0003", "Sucursal C")
BRANCH_INACTIVE = _branch("uuid-d-0004", "Inactiva", is_active=False)

resolver = ActiveBranchResolver()


# ── Tests 01-04: Basic resolution ────────────────────────────────────────────

def test_01_saved_branch_active_and_allowed_is_returned():
    result = resolver.resolve("uuid-a-0001", [BRANCH_A, BRANCH_B])
    assert result.branch_id == "uuid-a-0001"
    assert result.name == "Sucursal A"


def test_02_saved_branch_b_selected_even_with_multiple():
    result = resolver.resolve("uuid-b-0002", [BRANCH_A, BRANCH_B])
    assert result.branch_id == "uuid-b-0002"


def test_03_single_allowed_branch_auto_selected_when_no_saved():
    result = resolver.resolve(None, [BRANCH_A])
    assert result.branch_id == "uuid-a-0001"


def test_04_single_allowed_branch_auto_selected_when_saved_invalid():
    result = resolver.resolve("uuid-z-9999", [BRANCH_A])
    assert result.branch_id == "uuid-a-0001"


# ── Tests 05-07: Empty saved_branch_id ───────────────────────────────────────

def test_05_empty_string_saved_id_treated_as_not_set():
    result = resolver.resolve("", [BRANCH_A])
    assert result.branch_id == "uuid-a-0001"


def test_06_whitespace_saved_id_treated_as_not_set():
    result = resolver.resolve("   ", [BRANCH_A])
    assert result.branch_id == "uuid-a-0001"


def test_07_none_saved_id_with_single_branch_auto_selects():
    result = resolver.resolve(None, [BRANCH_A])
    assert result.branch_id == BRANCH_A.branch_id


# ── Tests 08-10: Inactive branch ─────────────────────────────────────────────

def test_08_inactive_branch_excluded_from_candidates():
    with pytest.raises(NoAllowedBranchesError):
        resolver.resolve(None, [BRANCH_INACTIVE])


def test_09_inactive_saved_branch_falls_to_single_remaining():
    result = resolver.resolve("uuid-d-0004", [BRANCH_INACTIVE, BRANCH_A])
    assert result.branch_id == "uuid-a-0001"


def test_10_inactive_branch_id_in_saved_triggers_multi_error_when_two_active():
    with pytest.raises(NoBranchSelectedError):
        resolver.resolve("uuid-d-0004", [BRANCH_INACTIVE, BRANCH_A, BRANCH_B])


# ── Tests 11-13: No allowed branches ─────────────────────────────────────────

def test_11_empty_allowed_list_raises_no_allowed():
    with pytest.raises(NoAllowedBranchesError):
        resolver.resolve("uuid-a-0001", [])


def test_12_only_inactive_branches_raises_no_allowed():
    with pytest.raises(NoAllowedBranchesError):
        resolver.resolve(None, [BRANCH_INACTIVE])


def test_13_no_allowed_error_message_is_user_friendly():
    try:
        resolver.resolve(None, [])
    except NoAllowedBranchesError as exc:
        assert "administrador" in str(exc).lower() or "sucursal" in str(exc).lower()


# ── Tests 14-16: Multiple branches, explicit selection required ───────────────

def test_14_multiple_branches_no_saved_raises_no_branch_selected():
    with pytest.raises(NoBranchSelectedError):
        resolver.resolve(None, [BRANCH_A, BRANCH_B])


def test_15_multiple_branches_invalid_saved_raises_no_branch_selected():
    with pytest.raises(NoBranchSelectedError):
        resolver.resolve("non-existent-id", [BRANCH_A, BRANCH_B, BRANCH_C])


def test_16_no_branch_selected_error_mentions_count():
    try:
        resolver.resolve(None, [BRANCH_A, BRANCH_B, BRANCH_C])
    except NoBranchSelectedError as exc:
        assert "3" in str(exc)


# ── Tests 28-32: Architecture guards ─────────────────────────────────────────

def test_28_principal_is_not_a_valid_branch_id_in_resolver():
    with pytest.raises((NoAllowedBranchesError, NoBranchSelectedError)):
        resolver.resolve("Principal", [BRANCH_A, BRANCH_B])


def test_29_resolver_never_returns_branch_named_principal_unless_that_is_the_data():
    result = resolver.resolve(None, [_branch("uuid-p-0001", "Principal")])
    assert result.name == "Principal"
    assert result.branch_id == "uuid-p-0001"


def test_30_branchdto_branch_id_cannot_be_empty():
    with pytest.raises(ValueError):
        BranchDTO(branch_id="", name="Centro")


def test_31_branchdto_name_cannot_be_empty():
    with pytest.raises(ValueError):
        BranchDTO(branch_id="uuid-a-0001", name="")


def test_32_active_branch_resolver_has_no_default_fallback_to_first_element():
    with pytest.raises(NoBranchSelectedError):
        resolver.resolve(None, [BRANCH_A, BRANCH_B])
    # Confirm it's not silently returning BRANCH_A (index 0)
