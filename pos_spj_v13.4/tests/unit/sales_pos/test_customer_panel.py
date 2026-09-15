"""`CustomerPanel._search_provider` used to read `result.id` on a
`CustomerLookupResult`, which only has `.customer_id` — every real search
result raised `AttributeError`, which `SearchSelector.refresh`'s blanket
`except Exception` swallowed right back into "no results". Protects the
translation from the presenter's backend DTO to the widget's `SearchOption`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication  # noqa: E402

from frontend.desktop.modules.sales_pos.components.customer_panel import CustomerPanel  # noqa: E402


@dataclass(frozen=True)
class _FakeLookupResult:
    customer_id: str
    display_name: str
    phone_e164: str | None = None


class _FakePresenter:
    def __init__(self, results):
        self._results = results

    def search_customers(self, query):
        return self._results


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_search_provider_maps_customer_id_not_id(app):
    presenter = _FakePresenter([
        _FakeLookupResult(customer_id="cust-123", display_name="Restaurante El Sol",
                          phone_e164="+5215512345678"),
    ])
    panel = CustomerPanel(presenter)

    options = panel._search_provider("Sol")

    assert len(options) == 1
    assert options[0].id == "cust-123"
    assert options[0].label == "Restaurante El Sol"
    assert options[0].subtitle == "+5215512345678"


def test_search_provider_returns_nothing_for_blank_query(app):
    panel = CustomerPanel(_FakePresenter([]))

    assert panel._search_provider("") == []
