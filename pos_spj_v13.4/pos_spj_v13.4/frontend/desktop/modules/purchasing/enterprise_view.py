"""Compatibility name for the canonical PurchasingModuleShell."""

from __future__ import annotations

from frontend.desktop.modules.purchasing.purchasing_module_shell import PurchasingModuleShell


class EnterprisePurchasingView(PurchasingModuleShell):
    """Temporary import-compatible class; contains no legacy behavior."""
