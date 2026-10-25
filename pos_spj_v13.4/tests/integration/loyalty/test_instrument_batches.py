"""Lotes físicos de cupones y vales con canje configurable (auditoría de
Fidelidad 968e0bc, ampliación), de punta a punta: Fidelidad crea, aprueba,
imprime y activa; el cajero escanea en la pantalla real del POS.

* Aprobar emite piezas que todavía NO se pueden canjear y no mueve dinero.
* Activar da saldo a los vales y publica VOUCHER_ISSUED (el pasivo nace aquí).
* Reimprimir da los mismos códigos; retirar una pieza anula su código impreso.
* El folio es legible y no sirve para canjear.
* Reglas por pieza: un uso / varios usos, tope % por venta, sobrante que se
  pierde o que impide el canje, margen protegido si lo paga el negocio.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

pytest.importorskip("PyQt5")

from backend.application.commercial_instruments.queries.piece_resolver import (  # noqa: E402
    resolve_instrument,
)
from backend.application.commercial_instruments.use_cases import (  # noqa: E402
    batch_use_cases as b,
)
from backend.infrastructure.db.repositories.commercial_instruments.unit_of_work import (  # noqa: E402
    CommercialInstrumentsUnitOfWork,
)
from backend.shared.ids import new_uuid  # noqa: E402
from tests.integration.sales.test_sales_pos_coupons_vouchers import (  # noqa: E402,F401
    AUTH,
    _apply_coupon,
    _balance,
    _ok,
    _pay,
    app,
    conn,
    pos,
)
from tests.integration.sales.test_sales_pos_screen_flows import _producto  # noqa: E402

CREADOR, APROBADOR, MATRIZ = new_uuid(), new_uuid(), new_uuid()
D = Decimal


def _ctx(actor=APROBADOR, branch=MATRIZ):
    return {"actor_user_id": actor, "actor_branch_id": branch, "operation_id": new_uuid()}


def _definition(conn, kind):
    if kind == "COUPON":
        from backend.application.commercial_instruments.use_cases import coupon_use_cases as cu
        from backend.domain.commercial_instruments.enums import CommercialBenefitType, CouponType
        return _ok(cu.CreateCouponDefinitionUseCase(AUTH).execute(
            conn, code=f"D{new_uuid()[-5:]}", name="Cupón navideño",
            coupon_type=CouponType.PUBLIC_CODE,
            benefit_type=CommercialBenefitType.FIXED_AMOUNT, benefit_value=D("15"),
            actor_user_id=new_uuid(), operation_id=new_uuid())).entity_id
    from backend.application.commercial_instruments.use_cases import voucher_use_cases as v
    from backend.domain.commercial_instruments.enums import VoucherType
    return _ok(v.CreateVoucherDefinitionUseCase(AUTH).execute(
        conn, code=f"VD{new_uuid()[-5:]}", name="Vale de regalo",
        voucher_type=VoucherType.PROMOTIONAL_VOUCHER, actor_user_id=new_uuid(),
        operation_id=new_uuid())).entity_id


def _batch(conn, kind="VOUCHER", *, activate=True, quantity=3, **reglas):
    datos = dict(kind=kind, definition_id=_definition(conn, kind), name="Navidad",
                 quantity=quantity, funding_source=reglas.pop("funding_source", "THIRD_PARTY"))
    if kind == "VOUCHER":
        datos["unit_value"] = D(reglas.pop("unit_value", "100"))
    datos.update(reglas)
    lote = _ok(b.CreateInstrumentBatchUseCase(AUTH).execute(
        conn, **_ctx(CREADOR), **datos)).entity_id
    _ok(b.SubmitInstrumentBatchUseCase(AUTH).execute(conn, batch_id=lote, **_ctx(CREADOR)))
    _ok(b.ApproveInstrumentBatchUseCase(AUTH).execute(conn, batch_id=lote, **_ctx()))
    piezas = _ok(b.PrintInstrumentBatchUseCase(AUTH).execute(
        conn, batch_id=lote, **_ctx())).data["pieces"]
    if activate:
        _ok(b.ActivateInstrumentBatchUseCase(AUTH).execute(conn, batch_id=lote, **_ctx()))
    return lote, piezas


def _events(conn, name):
    return [json.loads(r[0]) for r in conn.execute(
        "SELECT payload_json FROM commercial_instruments_outbox WHERE event_name=?", (name,))]


def _warnings(monkeypatch):
    """Lo que el cobro le dijo al cajero (el POS rechaza el pago con un aviso)."""
    from PyQt5.QtWidgets import QMessageBox

    avisos = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda _p, _t, texto, *_a: avisos.append(texto)))
    return avisos


def _resolve(conn, code, kind="VOUCHER", branch=None):
    return resolve_instrument(CommercialInstrumentsUnitOfWork(conn), code, kind=kind,
                              branch_id=branch)


# ── ciclo del lote ───────────────────────────────────────────────────────────
def test_creator_cannot_approve_own_batch(conn):
    lote = _ok(b.CreateInstrumentBatchUseCase(AUTH).execute(
        conn, **_ctx(CREADOR), kind="VOUCHER", definition_id=_definition(conn, "VOUCHER"),
        name="X", quantity=2, funding_source="THIRD_PARTY", unit_value=D("50"))).entity_id
    _ok(b.SubmitInstrumentBatchUseCase(AUTH).execute(conn, batch_id=lote, **_ctx(CREADOR)))
    r = b.ApproveInstrumentBatchUseCase(AUTH).execute(conn, batch_id=lote, **_ctx(CREADOR))
    assert not r.success and "no puede aprobarlo" in r.message


def test_prepaid_definition_cannot_be_batched(conn):
    from backend.application.commercial_instruments.use_cases import voucher_use_cases as v
    from backend.domain.commercial_instruments.enums import VoucherType
    d = _ok(v.CreateVoucherDefinitionUseCase(AUTH).execute(
        conn, code="PRE", name="Prepago", voucher_type=VoucherType.PREPAID_VOUCHER,
        actor_user_id=new_uuid(), operation_id=new_uuid())).entity_id
    r = b.CreateInstrumentBatchUseCase(AUTH).execute(
        conn, **_ctx(CREADOR), kind="VOUCHER", definition_id=d, name="X", quantity=2,
        funding_source="THIRD_PARTY", unit_value=D("50"))
    assert not r.success and "prepagados" in r.message


def test_approved_pieces_are_not_redeemable_and_move_no_money(conn):
    _lote, piezas = _batch(conn, activate=False)
    assert len(piezas) == 3 and len({p.code for p in piezas}) == 3
    assert conn.execute("SELECT COUNT(*) FROM voucher_transactions").fetchone()[0] == 0
    assert _events(conn, "VOUCHER_ISSUED") == []
    resuelto, motivo = _resolve(conn, piezas[0].code)
    assert resuelto is None and "todavía no está activo" in motivo
    # El código completo no se guarda: sólo su huella y un prefijo.
    guardado = " ".join(str(v) for r in conn.execute("SELECT * FROM instrument_batch_items")
                        for v in tuple(r))
    assert piezas[0].code.replace("-", "") not in guardado.replace("-", "")


def test_activation_issues_balance_and_events(conn):
    lote, piezas = _batch(conn)
    eventos = _events(conn, "VOUCHER_ISSUED")
    assert len(eventos) == 3
    assert {e["payload"]["batch_id"] for e in eventos} == {lote}
    assert {e["payload"]["funding_source"] for e in eventos} == {"THIRD_PARTY"}
    resuelto, _ = _resolve(conn, piezas[0].code)
    assert resuelto is not None and resuelto.from_batch


def test_reprint_gives_same_codes_and_revoke_rotates_the_code(conn):
    lote, piezas = _batch(conn)
    otra = _ok(b.PrintInstrumentBatchUseCase(AUTH).execute(
        conn, batch_id=lote, **_ctx())).data["pieces"]
    assert [p.code for p in otra] == [p.code for p in piezas]

    item = conn.execute("SELECT id FROM instrument_batch_items WHERE folio=?",
                        (piezas[0].folio,)).fetchone()[0]
    r = _ok(b.RevokeBatchPieceUseCase(AUTH).execute(
        conn, item_id=item, reason="extraviado", **_ctx()))
    nueva = r.data["piece"]
    assert nueva.folio == piezas[0].folio and nueva.code != piezas[0].code
    assert _resolve(conn, piezas[0].code)[0] is None
    assert _resolve(conn, nueva.code)[0] is not None


def test_folio_is_not_a_redeemable_code(conn):
    _lote, piezas = _batch(conn)
    resuelto, motivo = _resolve(conn, piezas[0].folio)
    assert resuelto is None and "folio" in motivo


def test_branch_and_validity_are_enforced(conn):
    _lote, piezas = _batch(conn, branch_ids=("S-NORTE",))
    assert _resolve(conn, piezas[0].code, branch="S-SUR")[1].endswith("en esta sucursal.")
    assert _resolve(conn, piezas[0].code, branch="S-NORTE")[0] is not None
    _lote, vencidas = _batch(conn, valid_to="2020-01-31")
    assert "vigencia" in _resolve(conn, vencidas[0].code)[1]


def test_coupon_code_is_rejected_where_a_voucher_is_expected(conn):
    _lote, piezas = _batch(conn, "COUPON")
    assert "de un cupón" in _resolve(conn, piezas[0].code, kind="VOUCHER")[1]


# ── en la caja ───────────────────────────────────────────────────────────────
def test_scanning_a_piece_is_routed_not_searched_as_a_product(pos):
    _lote, piezas = _batch(pos.conn)
    pos._on_product_selected(_producto(pos, "Huacal"))
    r = pos._presenter.scan_code(sale_id=pos._sale_id, code=piezas[0].code, context="AUTO")
    assert r.error_code == "INSTRUMENT_SCANNED"
    assert r.data["instrument_kind"] == "VOUCHER" and r.data["code"] == piezas[0].code


def test_coupon_piece_discounts_the_ticket(pos):
    _lote, piezas = _batch(pos.conn, "COUPON")
    pos._on_product_selected(_producto(pos, "Huacal"))
    _apply_coupon(pos, piezas[0].code)
    assert pos._sale.coupon_total == D("15.00")
    _pay(pos, [("CASH", "85", None)])
    instancia = pos.conn.execute(
        "SELECT instance_id FROM instrument_batch_items WHERE folio=?",
        (piezas[0].folio,)).fetchone()[0]
    assert pos.conn.execute("SELECT status FROM coupon_instances WHERE id=?",
                            (instancia,)).fetchone()[0] == "REDEEMED"


def test_multi_use_voucher_with_percentage_cap(pos):
    _lote, piezas = _batch(pos.conn, max_percent_per_sale=D("20"))
    codigo = piezas[0].code
    pos._on_product_selected(_producto(pos, "Huacal"))
    _pay(pos, [("VOUCHER", "100", codigo), ("CASH", "80", None)])
    assert _balance(pos.conn, codigo) == D("80.00")


def test_one_use_voucher_requires_full_use(pos, monkeypatch):
    _lote, piezas = _batch(pos.conn, unit_value="150", redemption_mode="ONE_EVENT")
    codigo = piezas[0].code
    avisos = _warnings(monkeypatch)
    pos._on_product_selected(_producto(pos, "Huacal"))
    _pay(pos, [("VOUCHER", "100", codigo), ("CASH", "100", None)])
    assert any("un solo uso" in a for a in avisos), avisos
    assert _balance(pos.conn, codigo) == D("150.00")


def test_one_use_voucher_forfeits_the_leftover(pos):
    _lote, piezas = _batch(pos.conn, unit_value="150", redemption_mode="ONE_EVENT",
                           leftover_policy="FORFEIT")
    codigo = piezas[0].code
    pos._on_product_selected(_producto(pos, "Huacal"))
    _pay(pos, [("VOUCHER", "100", codigo)])
    assert _balance(pos.conn, codigo) == D("0")
    vencidos = _events(pos.conn, "VOUCHER_EXPIRED")
    assert len(vencidos) == 1 and D(vencidos[0]["payload"]["expired_value"]) == D("50.00")
    assert pos.conn.execute(
        "SELECT COUNT(*) FROM voucher_transactions WHERE transaction_type='EXPIRE'"
    ).fetchone()[0] == 1


def test_personal_voucher_needs_its_holder(pos, monkeypatch):
    _lote, piezas = _batch(pos.conn)
    instancia = pos.conn.execute(
        "SELECT instance_id FROM instrument_batch_items WHERE folio=?",
        (piezas[0].folio,)).fetchone()[0]
    pos.conn.execute("UPDATE voucher_instances SET customer_id=? WHERE id=?",
                     (new_uuid(), instancia))
    avisos = _warnings(monkeypatch)
    pos._on_product_selected(_producto(pos, "Huacal"))
    _pay(pos, [("VOUCHER", "100", piezas[0].code), ("CASH", "100", None)])
    assert any("personal" in a for a in avisos), avisos
    assert _balance(pos.conn, piezas[0].code) == D("100.00")


def test_business_funded_voucher_respects_protected_margin(pos, monkeypatch):
    import backend.application.sales.cost_lookup as lookup

    # Huacal cuesta $85 sobre $100: con 10 % de margen mínimo quedan $5 para regalar.
    monkeypatch.setattr(lookup, "sale_unit_costs", lambda c, sale, **_k: (
        {ln.product_id: D("85") for ln in sale.goods_lines}, []))
    _lote, piezas = _batch(pos.conn, funding_source="PROMOTIONAL")
    pos._on_product_selected(_producto(pos, "Huacal"))
    _pay(pos, [("VOUCHER", "100", piezas[0].code), ("CASH", "95", None)])
    assert _balance(pos.conn, piezas[0].code) == D("95.00")
