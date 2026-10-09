"""Pricing composition, overflow and full workspace captures without a database.

Pricing/Purchasing use neutral page bodies; POS uses its unwired presenter.
Set SPJ_MODULE_LAYOUT_ARTIFACTS to retain PNGs for visual review.
"""

import os
from pathlib import Path

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QPoint, QRect, QSettings
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import ModuleLayout, SideNav, StandardLineEdit
from frontend.desktop.themes.theme_manager import ThemeManager
from tests.ui.test_module_sidebar_icon_visuals import _build, _settle


RESOLUTIONS = [(1280, 720), (1366, 768), (1440, 900), (1600, 900), (1920, 1080)]


def _rect(widget, owner):
    return QRect(widget.mapTo(owner, QPoint()), widget.size())


@pytest.fixture
def themed_app(qt_font_resources, ui_tmp_path, monkeypatch):
    manager = ThemeManager(settings=QSettings(str(ui_tmp_path / "theme.ini"), QSettings.IniFormat))
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    return qt_font_resources, manager


@pytest.mark.parametrize("module_name", ["pricing", "purchasing", "sales_pos"])
@pytest.mark.parametrize("resolution", RESOLUTIONS)
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["comfortable", "touch"])
def test_module_layout_at_supported_resolutions(
        themed_app, monkeypatch, module_name, resolution, theme, density):
    app, manager = themed_app
    manager.apply(app, theme, density=density)
    if module_name == "sales_pos":
        from frontend.desktop.modules.sales_pos.sales_pos_workspace import SalesPosWorkspace
        from tests.unit.test_sales_pos_workspace import _unwired_presenter

        owner, nav = SalesPosWorkspace(_unwired_presenter()), None
    else:
        owner, nav = _build(module_name, monkeypatch)
        stack = owner._stack if module_name == "pricing" else owner.content
        page = stack.currentWidget()
        page.setMinimumSize(0, 0)
        if page.layout() is None:
            body = QVBoxLayout(page)
            body.addWidget(QLabel("Contenido de prueba del módulo"))
            body.addWidget(StandardLineEdit(placeholder="Captura pendiente", keyboard_enabled=False))
            body.addStretch()
    try:
        layout = owner.module_layout
        owner.resize(*resolution)
        owner.show()
        _settle(app)
        content = layout.viewport.page()
        header = _rect(layout.header, owner)
        assert owner.size().width() == resolution[0]
        assert owner.size().height() == resolution[1]
        assert header.x() == 20 and header.y() == 16
        assert header.width() == owner.width() - 40
        for collapsed in ((False, True) if nav is not None else (False,)):
            if nav is not None:
                nav.set_collapsed(collapsed)
            _settle(app)
            assert _rect(layout.header, owner) == header
            viewport = _rect(layout.viewport, owner)
            assert viewport.y() == header.bottom() + 13
            assert owner.rect().contains(viewport)
            assert viewport.right() == owner.width() - 21
            assert viewport.bottom() == owner.height() - 17
            assert layout.viewport.page() is content
            if nav is not None:
                side = _rect(nav, owner)
                assert side.x() == 20 and side.y() == viewport.y()
                assert side.height() == viewport.height()
                assert side.width() == (64 if collapsed else 240)
                assert viewport.x() == side.right() + 17
                assert nav._toggle.isVisible()
            else:
                assert viewport.x() == 20
                assert owner._splitter.count() == 2
                assert owner._splitter.widget(0) is owner.catalog
                assert owner._splitter.widget(1) is owner.checkout
            directory = os.environ.get("SPJ_MODULE_LAYOUT_ARTIFACTS")
            if directory:
                target = Path(directory)
                target.mkdir(parents=True, exist_ok=True)
                suffix = "collapsed" if collapsed else "expanded"
                name = f"{module_name}-{theme}-{density}-{resolution[0]}x{resolution[1]}-{suffix}.png"
                assert owner.grab().save(str(target / name))
    finally:
        owner.close()
        sip.delete(owner)
        _settle(app)


def test_overflow_scrolls_only_body_and_context_order_is_stable(themed_app):
    app, manager = themed_app
    manager.apply(app, "light", density="comfortable")
    owner, content = QWidget(), QWidget()
    content.setMinimumSize(1800, 1200)
    field = StandardLineEdit(content, keyboard_enabled=False)
    field.setText("Captura sin guardar")
    nav = SideNav(owner)
    nav.add_section("Resumen")
    layout = ModuleLayout(owner, title="Módulo", sidebar=nav, content=content)
    first, second = QLabel("Contexto"), QLabel("Estado")
    layout.add_context(first)
    layout.add_context(second)
    owner.resize(1280, 720)
    owner.show()
    _settle(app)
    try:
        assert layout.itemAt(1).widget() is first
        assert layout.itemAt(2).widget() is second
        assert not layout.viewport.isAncestorOf(layout.header)
        assert not layout.viewport.isAncestorOf(nav)
        geometry = (layout.header.geometry(), nav.geometry(), first.geometry(), second.geometry())
        for scroll in (layout.viewport.horizontalScrollBar(), layout.viewport.verticalScrollBar()):
            assert scroll.maximum() > 0
            scroll.setValue(scroll.maximum())
        _settle(app)
        assert geometry == (layout.header.geometry(), nav.geometry(), first.geometry(), second.geometry())
        nav.set_collapsed(True)
        _settle(app)
        assert field.text() == "Captura sin guardar"
        assert layout.viewport.page() is content
    finally:
        owner.close()
        sip.delete(owner)
