"""CRM-1 (§3, §53) — Clientes/CRM never owns Fidelidad's entities.

Fidelidad owns points/tiers/cards/coupons/vouchers (master prompt §3). CRM may
only *read* a summary via a query service such as
``LoyaltyCustomerSummaryQuery`` — it must never write to
``tarjetas_fidelidad``/``loyalty_ledger``/``loyalty_scores``, never import
``CardBatchEngine``, and never define its own points/tier/card entities.
"""

from __future__ import annotations

from .customers_crm_guardrails import ALL_CRM_CODE_ROOTS, crm_py_files, relative

_FORBIDDEN_TOKENS = (
    "tarjetas_fidelidad",
    "CardBatchEngine",
    "loyalty_ledger",
    "loyalty_scores",
    "loyalty_card_template",
    "loyalty_card_batch",
    "loyalty_qr",
    "coupon_ledger",
    "voucher_ledger",
    "tier_history",
    "points_ledger",
    "points_balance",
)


def test_customers_crm_does_not_own_loyalty_entities():
    offenders = []
    for path in crm_py_files(ALL_CRM_CODE_ROOTS):
        source = path.read_text(encoding="utf-8")
        hits = [t for t in _FORBIDDEN_TOKENS if t in source]
        if hits:
            offenders.append(f"{relative(path)}: {hits}")
    assert not offenders, (
        "Fidelidad-owned entities/tables referenced from the CRM bounded context — "
        "use a read-only Loyalty*SummaryQuery projection instead:\n"
        + "\n".join(offenders)
    )
