"""CRM-43 — piezas de UI del módulo: formulario declarativo, Kanban, barra
de pestañas que se reacomoda, etiquetas en español y formato de fechas."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, datetime, timezone

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from tests.unit._crm_fake_presenter import CrmFakePresenter, FakeResult


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class TestForms:
    def _dialog(self, fields, on_submit=None):
        from frontend.desktop.modules.customers_crm.forms import CrmFormDialog
        return CrmFormDialog(None, title="Prueba", fields=fields, on_submit=on_submit)

    def test_datetime_is_sent_in_utc_with_zone(self, app):
        """El dominio compara instantes en UTC: la hora local sin zona marcaba
        vencidas las actividades horas antes."""
        from frontend.desktop.modules.customers_crm.forms import FieldSpec
        dialog = self._dialog((FieldSpec("when", "Cuándo", "datetime",
                                         default=datetime(2026, 10, 9, 15, 30)),))
        value = dialog.values()["when"]
        assert value.endswith("+00:00")
        assert datetime.fromisoformat(value) == datetime(2026, 10, 9, 15, 30).astimezone(
            timezone.utc)

    def test_date_is_a_date_object(self, app):
        """``create_opportunity_from_lead`` llamaba ``.isoformat()`` sobre un texto
        y la conversión ya hecha dejaba el formulario abierto."""
        from frontend.desktop.modules.customers_crm.forms import FieldSpec
        dialog = self._dialog((FieldSpec("d", "Fecha", "date", default=date(2026, 10, 30)),))
        assert dialog.values()["d"] == date(2026, 10, 30)

    def test_required_field_blocks_submit_and_keeps_the_dialog_open(self, app):
        from frontend.desktop.modules.customers_crm.forms import FieldSpec
        called = []
        dialog = self._dialog((FieldSpec("name", "Nombre", required=True),),
                              on_submit=lambda v: called.append(v))
        dialog._submit()
        assert called == [] and dialog.result() == 0
        assert dialog._error.text()

    def test_rejected_use_case_keeps_the_form_with_its_message(self, app):
        from frontend.desktop.modules.customers_crm.forms import FieldSpec
        dialog = self._dialog((FieldSpec("name", "Nombre", default="X"),),
                              on_submit=lambda v: FakeResult(False, "Duplicado"))
        dialog._submit()
        assert dialog.result() == 0 and dialog._error.text() == "Duplicado"


class TestKanban:
    def test_drop_only_requests_the_move_never_moves_the_card(self, app):
        from frontend.desktop.modules.customers_crm.pages._kanban import (
            KanbanBoard,
            KanbanCard,
            KanbanColumn,
        )
        board = KanbanBoard()
        board.set_columns([
            KanbanColumn("s1", "Prospección", "1", (KanbanCard("o1", "Opp", ("x",)),)),
            KanbanColumn("s2", "Propuesta", "0", ())])
        requested = []
        board.move_requested.connect(lambda card, stage: requested.append((card, stage)))
        source, target = board._lists
        source.setCurrentRow(0)

        class _Event:
            def source(self):
                return source

            def ignore(self):
                self.ignored = True

        event = _Event()
        target.dropEvent(event)
        assert requested == [("o1", "s2")]
        assert event.ignored and source.count() == 1


class TestPillTabBar:
    def test_wraps_instead_of_overflowing(self, app):
        from frontend.desktop.modules.customers_crm.pages._pill_tab_bar import PillTabBar
        bar = PillTabBar()
        for index in range(12):
            bar.add_tab(f"k{index}", f"Pestaña larga {index}")
        bar._relayout(400)
        assert len(bar._rows_signature) > 1
        assert sum(bar._rows_signature) == 12


class TestLabels:
    def test_domain_codes_become_spanish(self):
        from frontend.desktop.modules.customers_crm.labels import event_label, label
        assert label("customer_type", "PUBLIC_CUSTOMER") == "Público en general"
        assert label("credit_status", "NOT_CONFIGURED") == "Sin crédito"
        assert event_label("CRM_OPPORTUNITY_WON") == "Oportunidad: ganada"
        assert event_label("CUSTOMER_CREDIT_LIMIT_UPDATED") == "Crédito: cambio de límite"

    def test_every_status_enum_value_has_a_label(self):
        import importlib
        from frontend.desktop.modules.customers_crm.labels import _LABELS
        pairs = {
            "customer_status": ("customers", "CustomerStatus"),
            "lead_status": ("crm", "LeadStatus"),
            "opportunity_status": ("crm", "OpportunityStatus"),
            "case_status": ("customer_service", "ServiceCaseStatus"),
            "case_type": ("customer_service", "ServiceCaseType"),
            "credit_status": ("customer_credit", "CreditProfileStatus"),
            "consent_type": ("customer_privacy", "ConsentType"),
            "privacy_type": ("customer_privacy", "PrivacyRequestType"),
            "activity_type": ("crm", "CRMActivityType"),
            "sla_status": ("customer_service", "SLABreachStatus"),
        }
        for kind, (package, enum_name) in pairs.items():
            enum = getattr(importlib.import_module(f"backend.domain.{package}.enums"), enum_name)
            missing = [m.value for m in enum if m.value not in _LABELS[kind]]
            assert missing == [], (kind, missing)


class TestWorkItemsPanel:
    def test_buttons_follow_permissions(self, app):
        from backend.application.crm.permissions import CRMPermissions
        from frontend.desktop.modules.customers_crm.pages._work_items import WorkItemsPanel
        panel = WorkItemsPanel(CrmFakePresenter(permissions={CRMPermissions.NOTES_CREATE}))
        assert set(panel._buttons) == {"note", "complete", "reschedule", "cancel"}
