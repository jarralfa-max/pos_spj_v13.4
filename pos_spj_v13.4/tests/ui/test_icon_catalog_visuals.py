"""Reviewable Qt contact sheets of every registered symbol in each state."""
import math
import os
from pathlib import Path

import pytest
from PyQt5.QtCore import QEvent
from PyQt5.QtWidgets import QGridLayout, QLabel, QWidget

from frontend.desktop.components.icons import IconProvider, all_icons, icon_accessible_name
from frontend.desktop.themes.theme_manager import ThemeManager


PAGE_SIZE = 28
STATES = (("normal", "Normal"), ("hover", "Hover"), ("selected", "Seleccionado"),
          ("disabled", "Deshabilitado"), ("danger", "Peligro"),
          ("success", "Éxito"), ("warning", "Advertencia"), ("info", "Información"))


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("page_number", range(math.ceil(len(all_icons()) / PAGE_SIZE)))
def test_icon_catalog_states_render(qt_font_resources, ui_tmp_path, monkeypatch, theme, page_number):
    app = qt_font_resources
    manager = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, theme)
    sheet = QWidget()
    sheet.setWindowTitle("Catálogo IconProvider JUANIS")
    layout = QGridLayout(sheet)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setVerticalSpacing(12)
    layout.setHorizontalSpacing(18)
    layout.addWidget(QLabel(f"JUANIS · {'Claro' if theme == 'light' else 'Oscuro'} · {page_number + 1}"), 0, 0)
    for column, (_, title) in enumerate(STATES, 1):
        layout.addWidget(QLabel(title), 0, column)
    icons = all_icons()[page_number * PAGE_SIZE:(page_number + 1) * PAGE_SIZE]
    labels = []
    for row, name in enumerate(icons, 1):
        layout.addWidget(QLabel(f"{icon_accessible_name(name)}\n{name}"), row, 0)
        for column, (state, _) in enumerate(STATES, 1):
            label = QLabel()
            IconProvider.bind(label, name, size=24, state=state)
            label.setEnabled(state != "disabled")
            layout.addWidget(label, row, column)
            labels.append(label)
    try:
        sheet.show()
        app.processEvents()
        for label in labels:
            assert label.isVisible() and not label.pixmap().isNull()
            assert label.accessibleName()
        directory = Path(os.environ.get("SPJ_UI_VISUAL_ARTIFACTS", str(ui_tmp_path)))
        directory.mkdir(parents=True, exist_ok=True)
        assert sheet.grab().save(str(directory / f"catalog-{theme}-{page_number + 1}.png"))
    finally:
        sheet.close()
        sheet.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
