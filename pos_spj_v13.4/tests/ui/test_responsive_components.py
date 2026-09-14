"""Executable overflow, data integrity and hardware-input regression cases."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
from PyQt5.QtCore import QEvent, QPoint, QRect, QSettings, Qt
from PyQt5.QtGui import QFocusEvent, QIntValidator, QKeyEvent, QMouseEvent
from PyQt5.QtWidgets import QApplication, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout, QWidget

from frontend.desktop.components.buttons import create_primary_button
from frontend.desktop.components.dialogs import DestructiveConfirmationDialog, StandardDialog
from frontend.desktop.components.page_viewport import PageViewport
from frontend.desktop.components.pages import FormPage, TabbedPage, WizardPage
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.components.text_inputs import PasswordInput, StandardLineEdit
from frontend.desktop.components.virtual_keyboard import KeyboardAwareInput, VirtualKeyboard, attach_virtual_keyboard_action
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics

RESOLUTIONS = [(1280, 720), (1366, 768), (1440, 900), (1600, 900), (1920, 1080)]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(ui_tmp_path):
    return QSettings(str(ui_tmp_path / "ui.ini"), QSettings.IniFormat)


def process(app):
    for _ in range(4):
        app.processEvents()


@pytest.mark.parametrize("resolution", RESOLUTIONS)
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["comfortable", "touch"])
def test_long_form_scrolls_while_save_and_dialog_footer_remain_visible(app, monkeypatch, resolution, theme, density):
    manager = ThemeManager.instance()
    manager.set_density(density, app=app)
    manager.apply(app, theme)
    page = FormPage(title="Formulario extenso")
    for index in range(40):
        page.add_content(StandardLineEdit(placeholder=f"Campo {index}", keyboard_enabled=False))
    save = create_primary_button(text="Guardar")
    page.add_action(save)
    page.resize(*resolution)
    page.show()
    process(app)
    assert page.viewport.verticalScrollBar().maximum() > 0
    assert page.rect().contains(QRect(save.mapTo(page, QPoint()), save.size()))
    page.viewport.verticalScrollBar().setValue(page.viewport.verticalScrollBar().maximum())
    process(app)
    last = page.content_layout.itemAt(page.content_layout.count() - 1).widget()
    assert page.viewport.viewport().rect().intersects(QRect(last.mapTo(page.viewport.viewport(), QPoint()), last.size()))
    assert save.height() >= density_metrics(density).button_height

    dialog = StandardDialog(title="Captura extensa", width=resolution[0] * 2)
    monkeypatch.setattr(dialog, "available_geometry", lambda: QRect(0, 0, *resolution))
    for index in range(40):
        dialog.content_layout().addWidget(StandardLineEdit(placeholder=f"Dato {index}", keyboard_enabled=False))
    box = dialog.add_button_box(ok_text="Guardar")
    dialog.show()
    process(app)
    assert dialog.available_geometry().contains(dialog.frameGeometry())
    assert dialog.viewport.verticalScrollBar().maximum() > 0
    assert dialog.rect().contains(QRect(box.mapTo(dialog, QPoint()), box.size()))
    assert box.button(QDialogButtonBox.Ok).height() >= density_metrics(density).button_height
    dialog.close()
    page.close()


def test_page_viewport_scrolls_oversized_content_in_both_directions(app):
    viewport = PageViewport()
    content = QWidget()
    content.setMinimumSize(1800, 1200)
    viewport.set_page(content)
    viewport.resize(640, 480)
    viewport.show()
    process(app)
    assert viewport.size().width() == 640
    assert viewport.horizontalScrollBar().maximum() > 0
    assert viewport.verticalScrollBar().maximum() > 0
    viewport.close()


def test_table_reload_while_sorted_keeps_each_uuid_with_all_of_its_values(app):
    table = StandardTable([ColumnSpec("Nombre"), ColumnSpec("Importe", "numeric")])
    table.setSortingEnabled(True)
    table.sortItems(0, Qt.AscendingOrder)
    table.load_rows([["Zeta", "2"], ["Alfa", "10"], ["Beta", "$1,000.00"]], row_ids=["z", "a", "b"])
    for row, (label, amount, identity) in enumerate([("Alfa", "10", "a"), ("Beta", "$1,000.00", "b"), ("Zeta", "2", "z")]):
        assert [table.item(row, col).text() for col in range(2)] == [label, amount]
        assert all(table.item(row, col).data(Qt.UserRole) == identity for col in range(2))
    table.sortItems(1, Qt.AscendingOrder)
    assert [table.item(row, 1).text() for row in range(3)] == ["2", "10", "$1,000.00"]


def test_table_minimum_width_scroll_visibility_and_saved_width_survive_resize(app, settings):
    columns = [ColumnSpec("Nombre", key="name", min_width=220, preferred_width=250),
               ColumnSpec("Importe", "numeric", key="amount", min_width=140),
               ColumnSpec("Notas", key="notes", priority=2, hide_below=700)]
    table = StandardTable(columns, settings=settings, settings_key="inventory")
    table.resize(340, 300)
    table.show()
    process(app)
    assert not table.isColumnHidden(0) and not table.isColumnHidden(1)
    assert table.isColumnHidden(2)
    assert table.columnWidth(0) >= 220 and table.columnWidth(1) >= 140
    assert table.horizontalScrollBar().maximum() > 0
    table.setColumnWidth(0, 310)
    table.set_column_visible(2, False)
    table.resize(1200, 400)
    process(app)
    assert table.columnWidth(0) == 310
    restored = StandardTable(columns, settings=settings, settings_key="inventory")
    restored.resize(1200, 400)
    restored.show()
    process(app)
    assert restored.columnWidth(0) == 310
    assert restored.isColumnHidden(2)
    table.close()
    restored.close()


def test_table_rejects_incomplete_rows_without_destroying_existing_data(app):
    table = StandardTable([ColumnSpec("Nombre"), ColumnSpec("Estado")])
    table.load_rows([["Conservado", "Activo"]], row_ids=["existing"])
    with pytest.raises(ValueError):
        table.load_rows([["Incompleto"]], row_ids=["new"])
    assert table.item(0, 0).text() == "Conservado"
    with pytest.raises(ValueError):
        table.load_rows([["Completo", "Activo"]], row_ids=[])
    assert table.item(0, 0).data(Qt.UserRole) == "existing"


def test_table_filter_loading_and_manual_population_state(app):
    table = StandardTable([ColumnSpec("Nombre")])
    table.load_rows([["Alfa"], ["Beta"]])
    table.set_filter("beta")
    assert table.isRowHidden(0) and not table.isRowHidden(1)
    table.set_filter("no existe")
    assert table._state_label.text() == "Sin resultados"
    table.set_loading()
    assert table._state_label.text() == "Cargando…" and not table.isEnabled()
    table.load_rows([["Beta nueva"]])
    table.set_filter("")
    assert table._state_label.isHidden() and table.isEnabled()
    table.setRowCount(0)
    assert not table._state_label.isHidden()
    table.setRowCount(1)
    assert table._state_label.isHidden()


def test_runtime_density_updates_existing_inputs_tables_and_tabs(app):
    line = StandardLineEdit(keyboard_enabled=False)
    password = PasswordInput()
    table = StandardTable([ColumnSpec("Nombre")])
    table.load_rows([["Prueba"]])
    tabs = TabbedPage()
    tabs.tabs.addTab(QWidget(), "Datos")
    for density in ("compact", "touch", "comfortable"):
        ThemeManager.instance().set_density(density, app=app)
        process(app)
        metrics = density_metrics(density)
        assert line.minimumHeight() == metrics.input_height
        assert password.minimumHeight() == metrics.input_height
        assert table.rowHeight(0) >= metrics.table_row_height
        assert tabs.tabs.tabBar().tabSizeHint(0).height() >= metrics.tab_height


def test_virtual_keyboard_preserves_validation_selection_and_read_only(app):
    line = QLineEdit()
    line.setValidator(QIntValidator(0, 999, line))
    line.setText("12")
    line.selectAll()
    keyboard = VirtualKeyboard(line, input_mode="integer")
    keyboard.insert_text("8")
    assert line.text() == "8"
    keyboard.insert_text("x")
    assert line.text() == "8"
    keyboard.backspace()
    assert line.text() == ""
    line.setReadOnly(True)
    keyboard.insert_text("9")
    assert line.text() == ""
    assert "." not in keyboard.keys
    assert all(key.minimumHeight() >= 48 for key in keyboard.keys.values())


def test_virtual_keyboard_keeps_touch_targets_after_global_density_changes(app):
    from PyQt5.QtWidgets import QPushButton

    line = QLineEdit()
    keyboard = VirtualKeyboard(line)
    keyboard.show()
    manager = ThemeManager.instance()
    for density in ("touch", "compact", "comfortable"):
        manager.set_density(density, app=app)
        process(app)
        buttons = keyboard.findChildren(QPushButton)
        assert buttons
        assert all(button.minimumHeight() >= density_metrics("touch").button_height
                   for button in buttons)
        assert all(button.minimumWidth() >= density_metrics("touch").icon_button_size
                   for button in keyboard.keys.values())
        assert all(button.height() >= density_metrics("touch").button_height for button in buttons)
    keyboard.keys["Mayús"].click()
    keyboard.keys["a"].click()
    keyboard.keys["ñ"].click()
    keyboard.keys["Espacio"].click()
    keyboard.keys["Mayús"].click()
    keyboard.keys["b"].click()
    assert line.text() == "AÑ b"
    keyboard.close()


@pytest.mark.parametrize("input_mode", ["text", "integer", "decimal", "money", "weight", "phone", "email"])
def test_keyboard_modes_are_scoped_by_terminal_and_hardware_never_opens_it(app, settings, input_mode):
    line = QLineEdit()
    controller = KeyboardAwareInput(line, input_mode=input_mode, terminal_key="touch", settings=settings)
    controller.set_mode("auto_open")
    restored = KeyboardAwareInput(QLineEdit(), terminal_key="touch", settings=settings)
    other = KeyboardAwareInput(QLineEdit(), terminal_key="desktop", settings=settings)
    assert restored.mode == "auto_open" and other.mode == "icon_only"
    controller.eventFilter(line, QFocusEvent(QEvent.FocusIn, Qt.TabFocusReason))
    controller.eventFilter(line, QKeyEvent(QEvent.KeyPress, Qt.Key_1, Qt.NoModifier, "1"))
    assert controller.keyboard is None
    line.setProperty("hardwareInput", "scanner")
    controller.open()
    assert controller.keyboard is None
    line.setProperty("hardwareInput", "scale")
    controller.open()
    assert controller.keyboard is None
    controller.set_mode("disabled")
    assert not controller.action.isVisible()


def test_keyboard_attach_is_idempotent_and_destructive_default_is_cancel(app):
    line = QLineEdit()
    first = attach_virtual_keyboard_action(line)
    assert attach_virtual_keyboard_action(line) is first
    assert len(line.actions()) == 1
    dialog = DestructiveConfirmationDialog(title="Eliminar", message="¿Eliminar registro?")
    box = dialog._button_boxes[0]
    assert box.button(QDialogButtonBox.Cancel).isDefault()
    assert not box.button(QDialogButtonBox.Ok).isDefault()


def test_wizard_prevents_navigation_past_first_or_last_step(app):
    wizard = WizardPage()
    wizard.add_step(QWidget())
    wizard.add_step(QWidget())
    assert not wizard.previous_button.isEnabled() and wizard.next_button.isEnabled()
    wizard.next_button.click()
    assert wizard.steps.currentIndex() == 1
    assert wizard.previous_button.isEnabled() and not wizard.next_button.isEnabled()


def test_pricing_scroll_preserves_lazy_routes_when_opened_out_of_order(app):
    from frontend.desktop.modules.pricing.navigation import PRICING_NAV
    from frontend.desktop.modules.pricing.pricing_workspace import PricingWorkspace

    built = []
    def build(page_id, _presenter):
        built.append(page_id)
        page = QLabel(page_id)
        page.setMinimumSize(1600, 900)
        return page

    workspace = PricingWorkspace(None, has_permission=lambda _code: True, page_builder=build)
    assert len(built) == 1
    workspace.resize(1000, 600)
    workspace.show()
    process(app)
    for index in (len(PRICING_NAV) - 1, 1, len(PRICING_NAV) - 1, 0):
        page_id = PRICING_NAV[index].page_id
        workspace.select_page(page_id)
        process(app)
        assert workspace._stack.currentWidget().text() == page_id
        assert workspace.viewport.horizontalScrollBar().maximum() > 0
        assert workspace.viewport.verticalScrollBar().maximum() > 0
    assert len(built) == 3
    workspace.close()


def test_yield_monitoring_uses_page_scroll_without_eager_queries(app):
    from frontend.desktop.modules.losses.pages.yield_monitoring_page import YieldMonitoringPage

    page = YieldMonitoringPage(None)
    page.resize(800, 200)
    page.show()
    process(app)
    assert not page._loaded
    assert isinstance(page.viewport, PageViewport)
    assert page.viewport.verticalScrollBar().maximum() > 0
    page.close()
