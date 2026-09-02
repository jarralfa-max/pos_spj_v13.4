"""Canonical account-recovery errors — SHELL-1 security foundation."""
from __future__ import annotations


class RecoveryTokenInvalidError(ValueError):
    """The presented recovery token does not match any issued token, or has
    already been used. Deliberately generic — never reveals which case it
    was (unknown token vs. already-consumed) to avoid leaking account
    existence/state to an attacker."""


class RecoveryTokenExpiredError(ValueError):
    """The token matched a real, unused recovery request, but its expiry
    window has passed."""
