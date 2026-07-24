"""PRC-7 — view models de pricing (labels es-MX + formato money/pct, sin Qt)."""

from frontend.desktop.modules.pricing.view_models import (
    cost_method_es,
    costs_table,
    history_table,
    list_kind_es,
    list_status_es,
    list_status_variant,
    price_lists_table,
    price_source_es,
    product_prices_table,
)


def test_labels_es():
    assert list_status_es("ACTIVE") == "Activa"
    assert list_status_variant("ACTIVE") == "success"
    assert list_kind_es("CUSTOMER") == "Cliente"
    assert cost_method_es("AVERAGE") == "Promedio"
    assert price_source_es("VOLUME") == "Volumen"


def test_price_lists_table():
    t = price_lists_table([{"id": "l1", "code": "BASE", "name": "Base", "kind": "BASE",
                            "status": "ACTIVE", "discount_pct": "10"}])
    assert t.total == 1 and t.row_ids == ["l1"]
    assert t.rows[0] == ["BASE", "Base", "Base", "Activa", "10.0%"]


def test_product_prices_table_money_and_branch():
    t = product_prices_table([{"id": "pp1", "product_id": "p1", "product_code": "A-1",
                               "product_name": "Bistec", "branch_id": "", "sale_price": "100",
                               "currency": "MXN", "min_price": "120", "list_name": "Base"}])
    assert t.rows[0][0] == "A-1 · Bistec"
    assert t.rows[0][2] == "Todas"
    assert t.rows[0][3] == "$100.00" and t.rows[0][4] == "$120.00"


def test_product_prices_table_branch_specific():
    t = product_prices_table([{"id": "pp1", "product_id": "p1", "branch_id": "b1",
                               "sale_price": "95", "currency": "MXN", "list_name": "Base"}])
    assert t.rows[0][2] == "b1" and t.rows[0][0] == "p1"


def test_costs_table():
    t = costs_table([{"product_id": "p1", "product_name": "Bistec", "product_code": "A-1",
                      "average_cost": "60", "currency": "MXN", "last_cost": "62",
                      "standard_cost": None, "cost_method": "AVERAGE"}])
    assert t.rows[0] == ["A-1 · Bistec", "$60.00", "$62.00", "—", "Promedio"]


def test_history_table():
    t = history_table([{"product_id": "p1", "field": "cost", "old_value": "58",
                        "new_value": "60", "currency": "MXN", "user_id": "u1",
                        "authorized_by": None, "created_at": "2026-01-01"}])
    assert t.rows[0][2] == "Costo" and t.rows[0][3] == "$58.00"
    assert t.rows[0][4] == "$60.00" and t.rows[0][5] == "u1"
