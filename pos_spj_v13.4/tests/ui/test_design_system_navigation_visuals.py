"""Reviewable Qt evidence for authentication, module navigation and touch input."""
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QEvent, QPoint, QRect
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.auth.login_window import LoginWindow
from frontend.desktop.components import (
    DashboardPage, FormPage, KPIDTO, PrimaryButton, StandardLineEdit,
    StandardWindow, Tabs,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.components.side_nav import SideNav
from frontend.desktop.components.virtual_keyboard import VirtualKeyboard
from frontend.desktop.shell.application_shell.top_bar import TopBar
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import ResponsiveBreakpoints, density_metrics
from tests.ui.shell.conftest import make_context
from tests.ui.test_design_system_visual_matrix import save, settle


@pytest.mark.parametrize("size", ResponsiveBreakpoints.VALIDATION_SIZES)
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["comfortable", "touch"])
def test_navigation_authentication_and_keyboard_visuals(qt_font_resources, ui_tmp_path, monkeypatch, size, theme, density):
    app = qt_font_resources
    ThemeManager.instance().apply(app, theme, density=density)
    artifacts = Path(os.environ.get("SPJ_UI_VISUAL_ARTIFACTS", str(ui_tmp_path)))
    label = f"{theme}-{density}-{size[0]}x{size[1]}"
    summary = SimpleNamespace(get_summary=lambda: SimpleNamespace(company_name="JUANIS", branch_name="Sucursal Centro"))
    login = LoginWindow(
        authenticate_use_case=None, begin_recovery_use_case=None,
        complete_recovery_use_case=None, installation_summary_query=summary,
    )
    monkeypatch.setattr(login, "available_geometry", lambda: QRect(0, 0, *size))
    login.show()
    settle(app)
    assert login.available_geometry().contains(login.frameGeometry())
    assert login.viewport.viewport().rect().contains(QRect(
        login._login_btn.mapTo(login.viewport.viewport(), QPoint()), login._login_btn.size()))
    save(login, artifacts, label + "-login")
    login.close()
    login.deleteLater()

    window = StandardWindow()
    body = QWidget()
    root = QVBoxLayout(body)
    top_bar = TopBar()
    top_bar.set_context(make_context(user_name="Ana Ruiz"))
    root.addWidget(top_bar)
    row = QHBoxLayout()
    root.addLayout(row, 1)
    nav = SideNav()
    nav.add_group("Tesorería", Icons.FINANCE)
    nav.add_section("Cuentas y transferencias", Icons.TRANSFERS)
    nav.add_section("Conciliación bancaria", Icons.FINANCE)
    nav.add_group("Cobranza", Icons.CUSTOMERS)
    nav.add_section("Clientes", Icons.CUSTOMERS)
    nav.select(1)
    row.addWidget(nav)
    tabs = Tabs()
    row.addWidget(tabs, 1)
    dashboard = DashboardPage(title="Resumen de tesorería", subtitle="Información de la sucursal seleccionada")
    dashboard.context_bar.set_context({"Sucursal": "Centro", "Periodo": "Actual"})
    dashboard.kpis.set_cards([KPIDTO("balance", "Saldo disponible", "$12,450.00", icon=Icons.CASH)])
    dashboard.grid.add_full_width(QLabel("Sin movimientos pendientes de conciliación"))
    tabs.addTab(dashboard, "Resumen")
    form = FormPage(title="Datos de consulta")
    first = StandardLineEdit(placeholder="Referencia", keyboard_enabled=False)
    form.add_content(first)
    for index in range(24):
        form.add_content(StandardLineEdit(placeholder=f"Campo {index + 1}", keyboard_enabled=False))
    action = PrimaryButton("Consultar")
    form.add_action(action)
    tabs.addTab(form, "Consulta")
    window.setCentralWidget(body)
    window.show()
    window.resize(*size)
    settle(app)
    assert window.size().width() == size[0]
    assert tabs.tabBar().tabSizeHint(0).height() >= density_metrics(density).tab_height
    save(window, artifacts, label + "-module-expanded")
    nav.toggle_group(0)
    settle(app)
    assert nav.item(1).isHidden() and nav.item(2).isHidden()
    save(window, artifacts, label + "-module-group-collapsed")

    nav.set_collapsed(True)
    tabs.setCurrentIndex(1)
    settle(app)
    assert form.viewport.verticalScrollBar().maximum() > 0
    assert window.rect().contains(QRect(action.mapTo(window, QPoint()), action.size()))
    save(window, artifacts, label + "-module-collapsed-form")
    menu = nav.group_menu(0)
    menu.popup(nav.mapToGlobal(QPoint(nav.width(), 0)))
    settle(app)
    assert [item.text() for item in menu.actions()] == ["Cuentas y transferencias", "Conciliación bancaria"]
    save(menu, artifacts, label + "-module-flyout")
    menu.close()
    top_bar.file_menu.popup(top_bar.mapToGlobal(QPoint(0, top_bar.height())))
    settle(app)
    save(top_bar.file_menu, artifacts, label + "-file-menu")
    top_bar.file_menu.close()

    keyboard = VirtualKeyboard(first)
    monkeypatch.setattr(keyboard, "available_geometry", lambda: QRect(0, 0, *size))
    keyboard.show()
    settle(app)
    assert keyboard.available_geometry().contains(keyboard.frameGeometry())
    assert all(key.height() >= density_metrics("touch").button_height for key in keyboard.keys.values())
    assert keyboard.viewport.horizontalScrollBar().maximum() == 0
    assert keyboard.viewport.verticalScrollBar().maximum() == 0
    save(keyboard, artifacts, label + "-keyboard")
    keyboard.close()
    window.close()
    window.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
