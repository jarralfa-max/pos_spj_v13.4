"""CRM-43 — la UI completa con el presentador REAL por rol: ninguna ruta
queda «en construcción» y ninguna falla al cargar (medido en la base real:
53 de 62 rutas eran placeholders y sólo el dueño podía abrir el módulo)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)

from tests.integration.crm43.conftest import presenter_for


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.mark.parametrize("role, expected_routes", [
    ("system_owner", 53), ("gerente", 53), ("solo_lectura", 37), ("cajero", 22)])
def test_every_visible_route_is_real_and_loads(app, conn, role, expected_routes):
    from frontend.desktop.modules.customers_crm.customers_crm_workspace import (
        CustomersCrmWorkspace,
    )
    presenter, _ = presenter_for(conn, role)
    workspace = CustomersCrmWorkspace(presenter)
    assert len(workspace._route_index_by_id) == expected_routes
    placeholders, failures = [], []
    for route_id in workspace._route_index_by_id:
        workspace.select_route(route_id)
        app.processEvents()
        page = workspace._stack.currentWidget().findChild(QtWidgets.QScrollArea).widget()
        texts = [label.text() for label in page.findChildren(QtWidgets.QLabel)
                 if not label.isHidden()]
        if any("construcci" in text for text in texts):
            placeholders.append(route_id)
        if any(text.startswith("No fue posible") for text in texts):
            failures.append(route_id)
    workspace.deleteLater()
    assert placeholders == []
    assert failures == []


def test_automation_form_offers_every_action_and_saves_a_notification_rule(app, conn,
                                                                          monkeypatch):
    """CRM-43: «Enviar aviso» y «Cambiar prioridad» estaban excluidas del formulario
    porque no hacían nada. Ahora se ofrecen las siete acciones y una regla de aviso
    se guarda tal cual la captura el usuario."""
    from frontend.desktop.modules.customers_crm import forms
    from frontend.desktop.modules.customers_crm.pages.control_pages import SettingsPage

    presenter, owner_id = presenter_for(conn, "system_owner")
    offered = {}

    def answer(dialog):
        action = dialog._inputs["action"]
        offered["actions"] = [action.itemData(i) for i in range(1, action.count())]
        dialog._inputs["name"].setText("Aviso de prospecto frío")
        dialog._inputs["trigger"].set_current_id("LEAD_IDLE")
        dialog._inputs["days"].setValue(5)
        action.set_current_id("SEND_NOTIFICATION")
        dialog._inputs["user"].set_current_id(owner_id)
        dialog._inputs["responsible"].setChecked(True)
        dialog._submit()
        return 1 if dialog.result() == 1 else 0

    monkeypatch.setattr(forms.CrmFormDialog, "exec_", answer)
    page = SettingsPage(presenter)
    page._new_rule()

    assert offered["actions"] == ["CREATE_TASK", "ASSIGN_OWNER", "SEND_NOTIFICATION",
                                  "CHANGE_PRIORITY", "ESCALATE_CASE", "ADD_TAG",
                                  "ADD_TO_SEGMENT"]
    rule = conn.execute("SELECT trigger_type, action_type, trigger_config, action_config"
                        " FROM crm_automation_rules").fetchone()
    assert (rule[0], rule[1]) == ("LEAD_IDLE", "SEND_NOTIFICATION")
    assert '"days": 5' in rule[2]
    assert owner_id in rule[3] and '"notify_responsible": true' in rule[3]
    page.deleteLater()


def test_quote_detail_shows_lines_and_only_applicable_actions(app, conn):
    """CRM-43: las acciones de la cotización que no aplican a su estado se ocultan
    (con once el encabezado desbordaba); un borrador muestra sus partidas."""
    from datetime import date, timedelta

    from frontend.desktop.modules.customers_crm.pages.quote_pages import QuoteDetailPage
    from tests.integration.crm43.conftest import add_product, new_customer

    presenter, _ = presenter_for(conn, "system_owner")
    customer = new_customer(presenter, "Cocina Económica Doña Mary")
    product = add_product(conn, "Molida", "160.00", unit="KG")
    quote = presenter.run("create_quote", customer_id=customer, branch_id=presenter.branch_id(),
                          valid_until=(date.today() + timedelta(days=7)).isoformat(),
                          lines=[{"product_id": product, "quantity": "3"}]).entity_id
    page = QuoteDetailPage(presenter)
    page.show_quote(quote)
    app.processEvents()

    visible = sorted(a.label for a, b in page._page_buttons if not b.isHidden())
    assert visible == ["Agregar producto", "Cancelar", "Editar datos", "Terminar"]
    assert page._table.rowCount() == 1
    presenter.run("submit_quote", quote_id=quote)
    page.reload()
    visible = sorted(a.label for a, b in page._page_buttons if not b.isHidden())
    assert visible == ["Aceptó", "Cancelar", "Marcar enviada", "Nueva versión", "PDF",
                       "Rechazó", "Regresar a borrador"]
    page.deleteLater()
