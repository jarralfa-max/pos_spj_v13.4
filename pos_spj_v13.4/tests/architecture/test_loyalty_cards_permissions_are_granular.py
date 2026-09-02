"""LOY-1 (master prompt §59, §64) — the Loyalty Cards sub-bounded context
uses granular permissions only, registered under the existing
"TARJETAS_FIDELIDAD" key (its own, real sidebar entry — not folded into
"GROWTH_ENGINE", since master prompt §30 calls this out as a specialized
subdomain with its own navigation)."""

from __future__ import annotations

from backend.application.loyalty_cards.permissions import (
    ALL_LOYALTY_CARDS_PERMISSIONS,
    LoyaltyCardsPermissions,
)
from core.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS


def test_loyalty_cards_permissions_are_granular():
    assert len(ALL_LOYALTY_CARDS_PERMISSIONS) >= 20
    for code in (
        LoyaltyCardsPermissions.CARD_BLOCK,
        LoyaltyCardsPermissions.CARD_REPLACE,
        LoyaltyCardsPermissions.TEMPLATE_APPROVE,
        LoyaltyCardsPermissions.BATCH_APPROVE,
        LoyaltyCardsPermissions.QR_ROTATE,
        LoyaltyCardsPermissions.REPRINT,
    ):
        assert code in ALL_LOYALTY_CARDS_PERMISSIONS


def test_every_permission_is_tarjetas_fidelidad_prefixed_string():
    for code in ALL_LOYALTY_CARDS_PERMISSIONS:
        assert isinstance(code, str) and code.startswith("TARJETAS_FIDELIDAD.")


def test_no_duplicate_codes():
    values = list(vars(LoyaltyCardsPermissions).values())
    codes = [v for v in values if isinstance(v, str)]
    assert len(codes) == len(set(codes))


def test_every_loyalty_cards_permission_registered_in_catalog_key():
    registered = set(CANONICAL_MODULE_PERMISSIONS["TARJETAS_FIDELIDAD"])
    for code in ALL_LOYALTY_CARDS_PERMISSIONS:
        suffix = code.split(".", 1)[1]
        assert suffix in registered, f"{code} not registered under TARJETAS_FIDELIDAD in permission_catalog.py"
