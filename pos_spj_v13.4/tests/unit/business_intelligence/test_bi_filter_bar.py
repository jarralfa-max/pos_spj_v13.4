"""SDLC-BI-001: la barra de filtros sólo ofrece el alcance y aplica lo elegido."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt5.QtCore import QDate  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.application.analytics.access import BiAccess  # noqa: E402
from frontend.desktop.components.date_range_filter import DateRange  # noqa: E402
from frontend.desktop.modules.business_intelligence.presenters.bi_filters import (  # noqa: E402
    ALL_BRANCHES_LABEL,
    BiFilterState,
)
from frontend.desktop.modules.business_intelligence.widgets.bi_filter_bar import (  # noqa: E402
    BiFilterBar,
)


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


class _Consulta:
    def filter_options(self) -> dict:
        return {"branches": [{"id": "a", "nombre": "Centro"}, {"id": "b", "nombre": "Norte"}]}


def _barra(acceso: BiAccess) -> tuple[BiFilterBar, BiFilterState]:
    estado = BiFilterState(acceso, _Consulta())
    return BiFilterBar(estado), estado


def _textos(barra: BiFilterBar) -> list[str]:
    combo = barra.branch_selector
    return [combo.itemText(i) for i in range(combo.count())]


def test_a_scoped_user_only_gets_its_branches_and_no_all_option(qapp):
    barra, estado = _barra(BiAccess(can=lambda _c: True, allowed_branch_ids=("b",),
                                    default_branch_id="b"))
    assert _textos(barra) == ["Norte"]
    assert barra.branch_selector.currentData() == "b"
    assert estado.branch_label() == "Norte"


def test_a_company_wide_user_starts_on_all_branches(qapp):
    barra, estado = _barra(BiAccess.permissive_for_tests())
    assert _textos(barra) == [ALL_BRANCHES_LABEL, "Centro", "Norte"]
    assert estado.current.branch_id == ""
    assert estado.branch_label() == ALL_BRANCHES_LABEL


def test_choosing_a_branch_updates_the_filters_and_notifies(qapp):
    barra, estado = _barra(BiAccess.permissive_for_tests())
    avisos: list[bool] = []
    barra.filters_changed.connect(lambda: avisos.append(True))

    barra.branch_selector.setCurrentIndex(barra.branch_selector.findData("b"))

    assert estado.current.branch_id == "b"
    assert avisos == [True]


def test_the_custom_period_uses_the_chosen_dates(qapp):
    barra, estado = _barra(BiAccess.permissive_for_tests())
    barra.date_range.set_range(DateRange(QDate(2026, 1, 1), QDate(2026, 1, 31)))

    barra.period_selector.setCurrentIndex(barra.period_selector.findData("custom"))

    filtros = estado.current
    assert (filtros.preset, filtros.date_from, filtros.date_to) == (
        "custom", "2026-01-01", "2026-01-31")


def test_a_user_with_no_branch_can_open_the_page_and_nothing_is_offered(qapp):
    barra, _estado = _barra(BiAccess())
    assert _textos(barra) == []


def test_a_reversed_range_is_rejected(qapp):
    _barra_, estado = _barra(BiAccess.permissive_for_tests())
    with pytest.raises(ValueError):
        estado.set(preset="custom", date_from="2026-02-01", date_to="2026-01-01")
