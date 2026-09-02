"""Single permission-to-capability map for the Fidelidad UI (LOY-25).

Mirrors ``frontend/desktop/modules/customers_crm/capability_resolver.py``.
Every capability reuses an existing granular permission from
``backend.application.loyalty.permissions.LoyaltyPermissions`` (built
LOY-1) — Coupons/Vouchers/Sweepstakes share that same ``GROWTH_ENGINE``
permission surface even though their entities live in the
``commercial_instruments``/``sweepstakes`` bounded contexts (LOY-1's own
design), so no new permission codes were needed for this phase either.
"""

from __future__ import annotations

from collections.abc import Callable

from backend.application.loyalty.permissions import LoyaltyPermissions
from frontend.desktop.modules.fidelidad.view_models import FidelidadCapabilities


def resolve_fidelidad_capabilities(can: Callable[[str], bool]) -> FidelidadCapabilities:
    return FidelidadCapabilities(
        module_view=can(LoyaltyPermissions.VIEW),
        programs=can(LoyaltyPermissions.PROGRAM_VIEW),
        members=can(LoyaltyPermissions.MEMBERSHIP_VIEW),
        points=can(LoyaltyPermissions.POINTS_VIEW),
        rewards=can(LoyaltyPermissions.REWARD_VIEW),
        challenges=can(LoyaltyPermissions.CHALLENGE_VIEW),
        referrals=can(LoyaltyPermissions.REFERRAL_VIEW),
        birthdays=can(LoyaltyPermissions.BIRTHDAY_VIEW),
        campaigns=can(LoyaltyPermissions.CAMPAIGN_VIEW),
        coupons=can(LoyaltyPermissions.COUPON_VIEW),
        vouchers=can(LoyaltyPermissions.VOUCHER_VIEW),
        sweepstakes=can(LoyaltyPermissions.SWEEPSTAKES_VIEW),
        fraud=can(LoyaltyPermissions.FRAUD_VIEW),
        settings=can(LoyaltyPermissions.CONFIG_VIEW),
    )
