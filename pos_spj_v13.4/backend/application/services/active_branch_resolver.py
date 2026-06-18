# backend/application/services/active_branch_resolver.py
"""ActiveBranchResolver — single source of truth for resolving the active branch.

Resolution order (per SPJ_REFACTOR_SKILL.md):
  1. saved_branch_id exists, is active, and is in allowed_branches → use it.
  2. saved_branch_id is missing/invalid + exactly one allowed branch → use that one.
  3. saved_branch_id is missing/invalid + multiple allowed branches → raise NoBranchSelectedError.
  4. No allowed branches at all → raise NoAllowedBranchesError.

Never falls back to "Principal" or index 0 as a business rule.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

logger = logging.getLogger("spj.services.active_branch_resolver")


@dataclass(frozen=True)
class BranchDTO:
    """Immutable branch descriptor — branch_id is always a UUID string."""
    branch_id: str
    name: str
    is_active: bool = True

    def __post_init__(self) -> None:
        if not self.branch_id or not self.branch_id.strip():
            raise ValueError("BranchDTO.branch_id must not be empty")
        if not self.name or not self.name.strip():
            raise ValueError("BranchDTO.name must not be empty")


class ActiveBranchError(Exception):
    """Base for all resolver errors."""


class NoAllowedBranchesError(ActiveBranchError):
    """User has no active, allowed branches — block operational access."""


class NoBranchSelectedError(ActiveBranchError):
    """Multiple branches available; explicit user selection required."""


class ActiveBranchNotAvailableError(ActiveBranchError):
    """The saved branch_id is not in the allowed set (inactive, removed, or forbidden)."""

    def __init__(self, branch_id: str) -> None:
        super().__init__(f"Branch '{branch_id}' is not available for this user")
        self.branch_id = branch_id


class ActiveBranchResolver:
    """Stateless resolver — all state comes from the caller."""

    def resolve(
        self,
        saved_branch_id: str | None,
        allowed_branches: Sequence[BranchDTO],
    ) -> BranchDTO:
        """Return the branch that should become active.

        Parameters
        ----------
        saved_branch_id:
            The UUID string read from persistent config (may be None/empty).
        allowed_branches:
            Only **active** branches that the current user is permitted to use.
            Must be pre-filtered by the caller.

        Raises
        ------
        NoAllowedBranchesError
            When ``allowed_branches`` is empty.
        NoBranchSelectedError
            When ``saved_branch_id`` is not valid and there are multiple
            candidates — the UI must ask the user to choose.
        """
        active = [b for b in allowed_branches if b.is_active]

        if not active:
            logger.warning(
                "resolve: no allowed active branches for user (saved_id=%s)", saved_branch_id
            )
            raise NoAllowedBranchesError(
                "El usuario no tiene sucursales activas asignadas. "
                "Contacta al administrador."
            )

        # Rule 1 — use saved branch if valid
        if saved_branch_id and saved_branch_id.strip():
            sid = saved_branch_id.strip()
            match = next((b for b in active if b.branch_id == sid), None)
            if match:
                logger.debug(
                    "resolve: using saved branch '%s' (%s)", match.name, sid
                )
                return match
            logger.info(
                "resolve: saved_branch_id '%s' not found in allowed branches [%s]",
                sid,
                ", ".join(b.branch_id for b in active),
            )

        # Rule 2 — exactly one branch, no ambiguity
        if len(active) == 1:
            logger.info(
                "resolve: auto-selecting single available branch '%s' (%s)",
                active[0].name,
                active[0].branch_id,
            )
            return active[0]

        # Rule 3 — multiple branches, explicit selection needed
        logger.info(
            "resolve: multiple branches available (%d), explicit selection required",
            len(active),
        )
        raise NoBranchSelectedError(
            f"Se encontraron {len(active)} sucursales disponibles. "
            "Por favor selecciona una sucursal para continuar."
        )
