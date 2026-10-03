"""View-models for the Fidelidad desktop workspace (LOY-25).

Mirrors ``frontend/desktop/modules/customers_crm/view_models.py``'s shape —
one coarse capability flag per nav group (not per individual route), each
mapped to that group's most representative existing granular permission
(see ``capability_resolver.py``). Every permission reused here was already
built by LOY-1 (``LoyaltyPermissions``) — no new permission codes needed
for this phase.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FidelidadCapabilities:
    module_view: bool = False
    programs: bool = False
    members: bool = False
    points: bool = False
    rewards: bool = False
    challenges: bool = False
    referrals: bool = False
    birthdays: bool = False
    campaigns: bool = False
    coupons: bool = False
    vouchers: bool = False
    sweepstakes: bool = False
    fraud: bool = False
    settings: bool = False
    # LOY-29
    alerts: bool = False
    retention: bool = False
    audit: bool = False
    cards: bool = False
    card_templates: bool = False
    card_designer: bool = False
