"""FASE DS-7 — the component contract registry resolves and the gallery builds."""

import importlib
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from frontend.desktop import components as components_pkg  # noqa: E402
from frontend.desktop.design_system.component_contracts import (  # noqa: E402
    BUTTON_FACTORIES,
    CONTRACTS,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_every_contract_symbol_is_importable():
    for contract in CONTRACTS:
        module = importlib.import_module(contract.module)
        assert hasattr(module, contract.symbol), f"{contract.module}.{contract.symbol}"


def test_button_factories_are_exported():
    for factory in BUTTON_FACTORIES:
        assert hasattr(components_pkg, factory), factory


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_gallery_builds_in_both_themes(app, theme):
    from frontend.desktop.design_system.component_gallery import build_gallery
    widget = build_gallery(theme)
    assert widget is not None
