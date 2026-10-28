"""Page prompts preserve cancellation, validation and presenter payloads."""

from importlib import import_module
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from PyQt5.QtWidgets import QInputDialog

from frontend.desktop.components.dialogs import FormDialog, MessageDialog


ENTITY_ID = "019f327a-1694-7000-8000-000000000001"


@pytest.fixture
def prompts(monkeypatch):
    text, item = Mock(), Mock()
    # Both providers use the same result contract; this fixture also protects
    # the original page behavior before the canonical provider is adopted.
    monkeypatch.setattr(QInputDialog, "getText", text)
    monkeypatch.setattr(QInputDialog, "getItem", item)
    monkeypatch.setattr(FormDialog, "get_text", text, raising=False)
    monkeypatch.setattr(FormDialog, "get_item", item, raising=False)
    monkeypatch.setattr(MessageDialog, "information", Mock())
    monkeypatch.setattr(MessageDialog, "warning", Mock())
    return text, item


def _class(module, name):
    return getattr(import_module(f"frontend.desktop.modules.{module}"), name)


@pytest.mark.parametrize("module,name,method,presenter_method,title,label,kwargs", [
    ("hr.pages.employees_page", "EmployeesPage", "_deactivate", "deactivate_employee",
     "Dar de baja", "Motivo de la baja:", True),
    ("purchasing.pages.enterprise_pages", "InvoicesPage", "_cancel_invoice", "cancel_invoice",
     "Cancelar factura", "Motivo de la cancelación:", False),
    ("finance.pages.bank_reconciliation_page", "BankReconciliationPage", "_revert", "revert_reconciliation",
     "Revertir conciliación", "Motivo:", False),
])
@pytest.mark.parametrize("answer,accepted", [(" motivo capturado ", True), (" motivo capturado ", False), ("   ", True)])
def test_reason_actions_preserve_validation_and_payload(prompts, module, name, method, presenter_method,
                                                        title, label, kwargs, answer, accepted):
    text, _ = prompts
    text.return_value = answer, accepted
    presenter = Mock()
    write = getattr(presenter, presenter_method)
    write.return_value = (True, "Hecho", ENTITY_ID) if presenter_method == "cancel_invoice" else (True, "Hecho")
    page = SimpleNamespace(
        _presenter=presenter, selected_id=Mock(return_value=ENTITY_ID),
        _selected=Mock(return_value=ENTITY_ID), _selected_or_warn=Mock(return_value=ENTITY_ID),
        notify=Mock(), _notify=Mock(), reload=Mock())

    getattr(_class(module, name), method)(page)

    text.assert_called_once_with(page, title, label)
    if accepted and answer.strip():
        if kwargs:
            write.assert_called_once_with(ENTITY_ID, reason=answer.strip())
        else:
            write.assert_called_once_with(ENTITY_ID, answer.strip())
    else:
        write.assert_not_called()


@pytest.mark.parametrize("answer,accepted", [(f" {ENTITY_ID} ", True), (ENTITY_ID, False), (" ", True)])
def test_receivable_prompt_preserves_customer_selection(prompts, answer, accepted):
    text, _ = prompts
    text.return_value = answer, accepted
    page = SimpleNamespace(show_crm_summary_for=Mock())
    _class("finance.pages.accounts_receivable_page", "AccountsReceivablePage")._show_crm_summary(page)
    text.assert_called_once_with(page, "Resumen CRM", "ID de cliente (legacy):")
    if accepted and answer.strip():
        page.show_crm_summary_for.assert_called_once_with(ENTITY_ID)
    else:
        page.show_crm_summary_for.assert_not_called()


@pytest.mark.parametrize("accepted", [False, True])
def test_quality_prompt_preserves_reason_without_new_normalization(prompts, accepted):
    text, _ = prompts
    text.return_value = " motivo capturado ", accepted
    presenter = Mock()
    presenter.needs_reason.return_value = True
    presenter.decide.return_value = True, "Hecho"
    page = SimpleNamespace(_presenter=presenter, table=Mock(), refresh=Mock())
    page.table.selected_row_id.return_value = ENTITY_ID

    _class("meat_processing.pages.quality_inspection_page", "PendingInspectionsPage")._on_decide(page, "BLOCKED")

    text.assert_called_once_with(page, "Calidad", "Motivo (obligatorio):")
    if accepted:
        presenter.decide.assert_called_once_with(ENTITY_ID, "BLOCKED", " motivo capturado ")
        page.refresh.assert_called_once_with()
    else:
        presenter.decide.assert_not_called()
        page.refresh.assert_not_called()


@pytest.mark.parametrize("answer,accepted", [(" diferencia ", True), (" diferencia ", False), (" ", True)])
def test_reconciliation_difference_retries_only_after_a_valid_reason(prompts, answer, accepted):
    text, _ = prompts
    text.return_value = answer, accepted
    presenter = Mock()
    presenter.complete_reconciliation.side_effect = [(False, "Partidas sin conciliar"), (True, "Completada")]
    page = SimpleNamespace(_presenter=presenter, _selected_or_warn=Mock(return_value=ENTITY_ID),
                           notify=Mock(), reload=Mock())

    _class("finance.pages.bank_reconciliation_page", "BankReconciliationPage")._complete(page)

    text.assert_called_once_with(page, "Diferencia aceptada",
        "Partidas sin conciliar\nMotivo de la diferencia (requiere permiso para aceptarla):")
    expected = [call(ENTITY_ID)]
    if accepted and answer.strip():
        expected.append(call(ENTITY_ID, difference_reason=answer.strip()))
    assert presenter.complete_reconciliation.call_args_list == expected
    page.reload.assert_called_once_with()


@pytest.mark.parametrize("answer,text_accepted,item_accepted", [
    (" Nuevo surtido ", True, True), (" Nuevo surtido ", False, True),
    (" ", True, True), (" Nuevo surtido ", True, False),
])
def test_assortment_two_prompts_preserve_channel_mapping(prompts, answer, text_accepted, item_accepted):
    text, item = prompts
    text.return_value = answer, text_accepted
    item.return_value = "Mostrador", item_accepted
    presenter = Mock()
    presenter.list_channels.return_value = [{"label": "Mostrador", "value": "POS"}, {"label": "Delivery", "value": "DELIVERY"}]
    presenter.create_assortment.return_value = True, "Hecho"
    page = SimpleNamespace(_presenter=presenter, _refresh_assignments=Mock())

    _class("products.pages.branch_channel_page", "BranchChannelPage")._new_assortment(page)

    text.assert_called_once_with(page, "Nuevo surtido", "Nombre del surtido:")
    if text_accepted and answer.strip():
        item.assert_called_once_with(page, "Canal", "Canal:", ["Mostrador", "Delivery"], 0, False)
    else:
        item.assert_not_called()
    if text_accepted and answer.strip() and item_accepted:
        presenter.create_assortment.assert_called_once_with(name="Nuevo surtido", channel="POS")
        page._refresh_assignments.assert_called_once_with()
    else:
        presenter.create_assortment.assert_not_called()
        page._refresh_assignments.assert_not_called()


@pytest.mark.parametrize("accepted", [False, True])
def test_suggestions_prompt_maps_the_label_to_source_key(prompts, accepted):
    _, item = prompts
    item.return_value = "Reposición", accepted
    presenter = Mock()
    presenter.suggestion_sources.return_value = [("RESTOCK", "Reposición"), ("FORECAST", "Pronóstico")]
    presenter.suggestions.return_value = [], "Sin sugerencias"
    page = SimpleNamespace(_presenter=presenter)

    _class("meat_processing.pages.production_plan_page", "ProductionPlanPage")._on_suggest(page)

    item.assert_called_once_with(page, "Sugerir líneas", "Fuente:", ["Reposición", "Pronóstico"], 0, False)
    if accepted:
        presenter.suggestions.assert_called_once_with("RESTOCK")
    else:
        presenter.suggestions.assert_not_called()


@pytest.mark.parametrize("answer,accepted,expected", [
    (" motivo ", True, ("motivo", True)),
    (" motivo ", False, ("motivo", False)),
    (" ", True, ("", False)),
])
def test_campaign_reason_keeps_blank_and_cancel_semantics(prompts, answer, accepted, expected):
    text, _ = prompts
    text.return_value = answer, accepted
    page = SimpleNamespace()
    result = _class("configuracion.pages.pantalla_cliente_page", "PantallaClientePage")._ask_reason(page)
    assert result == expected
    text.assert_called_once_with(page, "Rechazar campaña", "Motivo:")
