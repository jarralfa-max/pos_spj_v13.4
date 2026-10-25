"""Reglas puras de los lotes de cupones y vales (auditoría de Fidelidad 968e0bc)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.commercial_instruments.entities.instrument_batch import (
    BatchStatus,
    InstrumentBatch,
    InstrumentBatchError,
    InstrumentKind,
)
from backend.domain.commercial_instruments.value_objects.piece_code import (
    hash_piece_code,
    normalize_piece_code,
    printable_piece_code,
)
from backend.domain.commercial_instruments.value_objects.redemption_rules import (
    FundingSource,
    LeftoverPolicy,
    PercentBase,
    RedemptionMode,
    RedemptionRules,
    RedemptionRulesError,
)

D = Decimal


def _amount(rules, *, balance="100", requested="500", gross="500", net="500", prior=0,
            margin=None):
    return rules.applicable_amount(
        balance=D(balance), requested=D(requested), gross_base=D(gross), net_base=D(net),
        prior_redemptions=prior, margin_budget=None if margin is None else D(margin))


# ── reglas de canje ──────────────────────────────────────────────────────────
def test_multi_event_pays_what_fits_and_stays_open():
    reglas = RedemptionRules()
    assert _amount(reglas, balance="100", requested="30") == D("30.00")
    assert not reglas.closes_after(redemptions_after=1, remaining=D("70"))
    assert reglas.closes_after(redemptions_after=5, remaining=D("0"))


def test_percentage_cap_uses_the_chosen_base_and_rounds_down():
    bruto = RedemptionRules(max_percent_per_sale=D("20"))
    neto = RedemptionRules(max_percent_per_sale=D("20"), percent_base=PercentBase.NET)
    assert _amount(bruto, gross="333.33", net="300") == D("66.66")
    assert _amount(neto, gross="333.33", net="300") == D("60.00")


def test_one_event_require_full_use_rejects_partial_use():
    reglas = RedemptionRules(mode=RedemptionMode.ONE_EVENT)
    assert _amount(reglas, balance="100", requested="150") == D("100.00")
    with pytest.raises(RedemptionRulesError, match="un solo uso"):
        _amount(reglas, balance="100", requested="60")


def test_one_event_forfeit_allows_partial_and_then_closes():
    reglas = RedemptionRules(mode=RedemptionMode.ONE_EVENT,
                             leftover_policy=LeftoverPolicy.FORFEIT)
    assert _amount(reglas, balance="100", requested="60") == D("60.00")
    assert reglas.closes_after(redemptions_after=1, remaining=D("40"))


def test_max_redemptions_is_enforced():
    reglas = RedemptionRules(max_redemptions=2)
    assert _amount(reglas, prior=1) == D("100.00")
    with pytest.raises(RedemptionRulesError, match="2 canjes"):
        _amount(reglas, prior=2)
    with pytest.raises(RedemptionRulesError):
        RedemptionRules(mode=RedemptionMode.ONE_EVENT, max_redemptions=3)


def test_margin_budget_caps_only_business_funded_pieces():
    promocional = RedemptionRules(funding_source=FundingSource.PROMOTIONAL)
    tercero = RedemptionRules(funding_source=FundingSource.THIRD_PARTY)
    assert _amount(promocional, margin="25") == D("25.00")
    assert _amount(tercero, margin="25") == D("100.00")
    with pytest.raises(RedemptionRulesError, match="no admite"):
        _amount(promocional, margin="0")


def test_no_balance_is_rejected():
    with pytest.raises(RedemptionRulesError, match="saldo"):
        _amount(RedemptionRules(), balance="0")


# ── código de pieza ──────────────────────────────────────────────────────────
def test_piece_code_normalizes_and_rejects_folios():
    canonico = "VALABCDEFGHIJKLMNOP"
    assert normalize_piece_code("val-abcd-efgh-ijkl-mnop") == canonico
    assert normalize_piece_code(" VAL ABCD EFGH IJKL MNOP ") == canonico
    assert printable_piece_code(canonico) == "VAL-ABCD-EFGH-IJKL-MNOP"
    assert normalize_piece_code("VAL7F3A-00001") is None    # folio legible
    assert normalize_piece_code("VALABCDEFGHIJKLMNO1") is None   # 1 no es Base32
    assert hash_piece_code(canonico) == hash_piece_code("val-abcd-efgh-ijkl-mnop")


# ── lote ─────────────────────────────────────────────────────────────────────
def _lote(**cambios):
    datos = dict(kind=InstrumentKind.VOUCHER, definition_id="def", name="Navidad",
                 quantity=10, unit_value=D("100"), funding_source=FundingSource.PROMOTIONAL,
                 created_by_user_id="creador")
    datos.update(cambios)
    return InstrumentBatch.draft(**datos)


def test_lifecycle_and_segregation_of_duties():
    lote = _lote()
    with pytest.raises(InstrumentBatchError):
        lote.approve("otro")                     # primero se envía
    lote.submit()
    with pytest.raises(InstrumentBatchError, match="no puede aprobarlo"):
        lote.approve("creador")
    lote.approve("aprobador")
    with pytest.raises(InstrumentBatchError):
        lote.activate()                          # no se activa sin imprimir
    lote.mark_printed()
    lote.mark_printed()
    assert lote.status is BatchStatus.PRINTED and lote.printed_count == 2
    lote.activate()
    with pytest.raises(InstrumentBatchError):
        lote.cancel("tarde")                     # activo: ya no se cancela


def test_coupons_are_always_one_use_and_prepaid_is_not_batchable():
    cupon = _lote(kind=InstrumentKind.COUPON, unit_value=D("0"),
                  redemption_mode=RedemptionMode.MULTI_EVENT, max_redemptions=5)
    assert cupon.rules().effective_max_redemptions == 1
    with pytest.raises(InstrumentBatchError, match="prepagados"):
        _lote(funding_source=FundingSource.PREPAID)
    with pytest.raises(InstrumentBatchError):
        _lote(quantity=0)
    with pytest.raises(InstrumentBatchError):
        _lote(valid_from="2026-12-31", valid_to="2026-01-01")


def test_validity_is_by_day_and_branch_list_is_optional():
    lote = _lote(valid_from="2026-11-01", valid_to="2026-11-30", branch_ids=("S1",))
    assert lote.valid_at("2026-11-30T23:59:00+00:00")
    assert not lote.valid_at("2026-12-01T00:00:00+00:00")
    assert lote.allows_branch("S1") and not lote.allows_branch("S2")
    assert _lote().allows_branch("cualquiera")
