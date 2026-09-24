"""A live density change must resize existing controls without replacing state."""
import pytest
from PyQt5 import sip
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from backend.shared.ids import new_uuid
from frontend.desktop.components.buttons import IconButton, PrimaryButton
from frontend.desktop.components.icons import Icons
from frontend.desktop.components.integer_input import IntegerInput
from frontend.desktop.components.selection_controls import StandardComboBox
from frontend.desktop.components.side_nav import SideNav
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.components.tabs import Tabs
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_density_round_trip_resizes_existing_controls_and_preserves_state(qt_font_resources, ui_tmp_path, monkeypatch, theme):
    app = qt_font_resources
    settings = QSettings(str(ui_tmp_path / "density.ini"), QSettings.IniFormat)
    manager = ThemeManager(settings)
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, theme, density="compact")
    host = QWidget()
    layout = QVBoxLayout(host)
    line = StandardLineEdit(keyboard_enabled=False)
    line.setText("Referencia en captura")
    line.setSelection(0, 10)
    integer = IntegerInput()
    integer.setValue(7)
    combo = StandardComboBox(accessible_name="Estado de consulta")
    combo.addItems(("Pendiente", "Confirmado"))
    combo.setCurrentIndex(1)
    for control in (line, integer, combo):
        layout.addWidget(control)
    actions = QHBoxLayout()
    primary, icon = PrimaryButton("Consultar"), IconButton(Icons.SEARCH, "Buscar")
    actions.addWidget(primary)
    actions.addWidget(icon)
    actions.addStretch()
    layout.addLayout(actions)
    content = QHBoxLayout()
    nav = SideNav()
    nav.add_section("Resumen", Icons.HOME)
    nav.add_section("Movimientos", Icons.CASH)
    nav.select(1)
    content.addWidget(nav)
    tabs = Tabs()
    tabs.addTab(QWidget(), "Resumen")
    table = StandardTable([ColumnSpec("Descripción"), ColumnSpec("Cantidad", "numeric")])
    row_ids = [new_uuid(), new_uuid()]
    table.load_rows([["Primero", "2"], ["Segundo", "7"]], row_ids=row_ids)
    table.selectRow(1)
    tabs.addTab(table, "Movimientos")
    tabs.setCurrentIndex(1)
    content.addWidget(tabs, 1)
    layout.addLayout(content, 1)
    host.resize(900, 650)
    try:
        host.show()
        measurements = []
        for profile in ("compact", "comfortable", "touch", "compact"):
            manager.set_density(profile)
            for _ in range(4):
                app.processEvents()
            metrics = density_metrics(profile)
            assert all(control.height() >= metrics.input_height for control in (line, integer, combo))
            assert primary.height() >= metrics.button_height
            assert min(icon.width(), icon.height()) >= metrics.icon_button_size
            assert table.rowHeight(1) == metrics.table_row_height
            assert nav.visualItemRect(nav.item(1)).height() == metrics.sidebar_item_height
            assert tabs.tabBar().tabRect(1).height() >= metrics.tab_height
            assert line.text() == "Referencia en captura" and line.selectedText() == "Referencia"
            assert integer.value() == 7 and combo.currentIndex() == 1
            assert table.selected_row_id() == row_ids[1]
            assert tabs.currentIndex() == 1 and nav.currentRow() == 1
            assert settings.value("appearance/density") == profile
            assert app.property("spjDensity") == profile and manager.theme == theme
            assert all(not widget.styleSheet() for widget in (line, integer, combo, primary, icon, nav, tabs, table))
            measurements.append((line.height(), integer.height(), combo.height(), primary.height(),
                                 icon.height(), table.rowHeight(1), tabs.tabBar().tabRect(1).height()))
        assert measurements[-1] == measurements[0], "Compacta debe recuperar su geometría tras usar Táctil."
    finally:
        host.close()
        sip.delete(host)
