"""UI/UX phase — ConfiguracionView/pages/dialogs, mirroring
`tests/unit/test_transfers_ui_workspace.py`'s pattern: offscreen QPA,
fakes standing in for the presenter so no real DB is needed here (the
real-DB path is covered by `tests/integration/configuracion/`).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from backend.application.queries.configuracion.workspace_query_service import (
    AssignmentRowViewModel, BranchOptionViewModel, BranchProfileDetailViewModel, ChangeRequestRowViewModel,
    ConfigColumnDTO, ConfigPageViewModel, ConfigRowViewModel, CompanyProfileDetailViewModel,
    DeviceOptionViewModel, DeviceProfileOptionViewModel, MarketingCampaignRowViewModel,
    PrintRouteRowViewModel, TemplateDetailViewModel,
    TemplateVersionRowViewModel, ThemeRowViewModel, WorkstationDetailViewModel,
)
from frontend.desktop.modules.configuracion.configuracion_presenter import ConfiguracionPresenter
from frontend.desktop.modules.configuracion.configuracion_view import ConfiguracionView
from frontend.desktop.modules.configuracion.dialogs import (
    AssignDeviceDialog,
    BlockDeviceDialog,
    BlockWorkstationDialog,
    BranchProfileCreateDialog,
    BranchProfileEditDialog,
    CompanyProfileDialog,
    DeviceCreateDialog,
    DeviceEditDialog,
    DeviceProfileCreateDialog,
    DocumentTemplateCreateDialog,
    DocumentTemplateEditDialog,
    MarketingCampaignCreateDialog,
    MarketingCampaignEditDialog,
    NewTemplateVersionDialog,
    PrintRouteCreateDialog,
    PrintRouteEditDialog,
    RejectChangeRequestDialog,
    RejectTemplateVersionDialog,
    SetDefaultThemeDialog,
    WorkstationCreateDialog,
    WorkstationEditDialog,
)
from frontend.desktop.modules.configuracion.navigation.configuracion_sidebar import CONFIGURACION_NAV


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class Queries:
    def __init__(
        self, *, rows=(), pending=(), themes=(), device_profiles=(), branches=(), device=None,
        template=None, template_versions=(), company=None, unregistered_branches=(), branch_profile=None,
        workstation=None, devices=(), assignments=(), print_routes=(), marketing_campaigns=(),
        display_content=(), content_campaigns=(), advertising_slots=(), campaign_placements=(),
        integration_definitions=(), integration_instances=(), webhook_endpoints=(),
        integration_health_checks=(),
        notification_accounts=(), notification_templates=(), notification_routes=(),
        feature_flags=(), feature_flag_rules=(),
        design_tokens=(), density_profiles=(), appearance_preferences=(),
        cache_expiration_policies=(), offline_cache_entries=(),
        users=(), roles=(), audit_logs=(), role_names=(), branches_for_selector=(),
        employees_for_selector=(), installation_branch=None,
    ):
        self.calls = []
        self._rows = rows
        self._pending = pending
        self._themes = themes
        self._device_profiles = device_profiles
        self._branches = branches
        self._device = device
        self._template = template
        self._template_versions = template_versions
        self._company = company
        self._unregistered_branches = unregistered_branches
        self._branch_profile = branch_profile
        self._workstation = workstation
        self._devices = devices
        self._assignments = assignments
        self._print_routes = print_routes
        self._marketing_campaigns = marketing_campaigns
        self._display_content = display_content
        self._content_campaigns = content_campaigns
        self._advertising_slots = advertising_slots
        self._campaign_placements = campaign_placements
        self._integration_definitions = integration_definitions
        self._integration_instances = integration_instances
        self._webhook_endpoints = webhook_endpoints
        self._integration_health_checks = integration_health_checks
        self._notification_accounts = notification_accounts
        self._notification_templates = notification_templates
        self._notification_routes = notification_routes
        self._feature_flags = feature_flags
        self._feature_flag_rules = feature_flag_rules
        self._design_tokens = design_tokens
        self._density_profiles = density_profiles
        self._appearance_preferences = appearance_preferences
        self._cache_expiration_policies = cache_expiration_policies
        self._offline_cache_entries = offline_cache_entries
        self._users = users
        self._roles = roles
        self._audit_logs = audit_logs
        self._role_names = role_names
        self._branches_for_selector = branches_for_selector
        self._employees_for_selector = employees_for_selector
        self._installation_branch = installation_branch

    def page(self, *, page_id, search=""):
        self.calls.append((page_id, search))
        return ConfigPageViewModel(
            columns=(ConfigColumnDTO("Código"), ConfigColumnDTO("Nombre")), rows=self._rows,
        )

    def list_pending_feature_flag_change_requests(self):
        return self._pending

    def list_themes(self):
        return self._themes

    def list_device_profiles(self):
        return self._device_profiles

    def list_branches(self):
        return self._branches

    def get_device(self, device_id):
        return self._device

    def get_template(self, template_id):
        return self._template

    def list_template_versions(self, template_id):
        return self._template_versions

    def get_company_profile(self):
        return self._company

    def list_unregistered_branches(self):
        return self._unregistered_branches

    def get_installation_branch(self):
        return self._installation_branch

    def get_branch_profile(self, branch_id):
        return self._branch_profile

    def get_workstation(self, workstation_id):
        return self._workstation

    def list_devices(self):
        return self._devices

    def list_workstation_assignments(self, workstation_id):
        return self._assignments

    def list_print_routes(self):
        return self._print_routes

    def list_marketing_campaigns(self):
        return self._marketing_campaigns

    def list_display_content(self):
        return self._display_content

    def get_display_content(self, content_id):
        return next((c for c in self._display_content if c.entity_id == content_id), None)

    def list_content_campaigns(self):
        return self._content_campaigns

    def list_advertising_slots(self):
        return self._advertising_slots

    def list_campaign_placements(self):
        return self._campaign_placements

    def get_impression_summary(self, placement_id):
        return "Impresiones: 0\nDuración total: 0s\nDuración promedio: 0s"

    def list_integration_definitions(self):
        return self._integration_definitions

    def list_integration_instances(self, definition_id):
        return self._integration_instances

    def list_webhook_endpoints(self, instance_id):
        return self._webhook_endpoints

    def list_integration_health_checks(self, instance_id):
        return self._integration_health_checks

    def get_integration_health_status(self, instance_id):
        return "UNKNOWN"

    def get_credential_status(self, credential_reference):
        return "No configurada"

    def list_notification_accounts(self):
        return self._notification_accounts

    def list_notification_templates(self):
        return self._notification_templates

    def list_notification_routes(self):
        return self._notification_routes

    def list_feature_flags(self):
        return self._feature_flags

    def list_feature_flag_rules(self, flag_id):
        return self._feature_flag_rules

    def list_design_tokens_for_theme(self, theme_id):
        return self._design_tokens

    def list_density_profiles(self):
        return self._density_profiles

    def list_appearance_preferences(self):
        return self._appearance_preferences

    def list_cache_expiration_policies(self):
        return self._cache_expiration_policies

    def list_offline_cache_entries(self):
        return self._offline_cache_entries

    def list_users(self):
        return self._users

    def get_user_form_data(self, user_id):
        return next((u for u in self._users if getattr(u, "id", None) == user_id), None)

    def list_roles(self):
        return self._roles

    def list_role_names(self):
        return self._role_names

    def list_branches_for_user_selector(self):
        return self._branches_for_selector

    def list_employees_for_user_selector(self):
        return self._employees_for_selector

    def audit_log_rows(self, limit=200):
        return self._audit_logs


class TestConfiguracionView:
    def test_workspace_builds_all_permitted_routes_lazily_and_supports_target_sizes(self, app):
        presenter = ConfiguracionPresenter(Queries())
        view = ConfiguracionView(presenter, has_permission=lambda _permission: True)
        assert view.sidebar.count() == len(CONFIGURACION_NAV)
        for entry in CONFIGURACION_NAV:
            view.show_route(entry.page_id)
        assert view.stack.count() == len(CONFIGURACION_NAV)
        view.resize(1366, 768)
        assert view.minimumWidth() <= 1366 and view.minimumHeight() <= 768
        view.resize(960, 600)
        assert view.sidebar.accessibleName() == "Navegación de Configuración"

    def test_sidebar_filters_by_permission(self, app):
        view = ConfiguracionView(
            ConfiguracionPresenter(Queries()),
            has_permission=lambda permission: permission == CONFIGURACION_NAV[0].permission,
        )
        assert view.sidebar.count() == 1

    def test_empty_page_shows_empty_state_not_a_blank_table(self, app):
        presenter = ConfiguracionPresenter(Queries(rows=()))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        page = view._pages[CONFIGURACION_NAV[0].page_id]
        # isVisible() needs a shown top-level window (not done in this offscreen
        # test); isHidden() reflects the explicit setVisible() call regardless.
        assert page.table.isHidden() is True
        assert page.state_widget is not None

    def test_page_with_rows_shows_table_not_empty_state(self, app):
        rows = (ConfigRowViewModel("id1", ("A", "B")),)
        presenter = ConfiguracionPresenter(Queries(rows=rows))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        page = view._pages[CONFIGURACION_NAV[0].page_id]
        assert page.table.isHidden() is False
        assert page.table.rowCount() == 1


class TestGeneralPage:
    def test_action_buttons_present_and_wired(self, app):
        presenter = ConfiguracionPresenter(Queries(rows=()))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_general")
        page = view._pages["config_general"]
        assert page.new_button.text() == "Nueva estación"
        assert page.edit_button.text() == "Editar"
        assert page.activate_button.text() == "Activar"
        assert page.deactivate_button.text() == "Desactivar"
        assert page.maintenance_button.text() == "Mantenimiento"
        assert page.exit_maintenance_button.text() == "Salir de mantenimiento"
        assert page.block_button.text() == "Bloquear"
        assert page.unblock_button.text() == "Desbloquear"
        assert page.retire_button.text() == "Retirar"
        assert page.assign_button.text() == "Asignar dispositivo"
        assert page.unassign_button.text() == "Desasignar"

    def test_actions_without_selection_warn_instead_of_crashing(self, app, monkeypatch):
        presenter = ConfiguracionPresenter(Queries(rows=()))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_general")
        page = view._pages["config_general"]

        warnings = []
        import frontend.desktop.modules.configuracion.pages.estaciones_page as page_module
        monkeypatch.setattr(
            page_module.QMessageBox, "warning", staticmethod(lambda *a: warnings.append(a)),
        )
        page._on_edit()
        page._on_block()
        page._on_change_status("ACTIVATE")
        page._on_assign()
        page._on_unassign()
        assert len(warnings) == 5

    def test_selecting_a_workstation_loads_its_assignments(self, app):
        rows = (ConfigRowViewModel("w1", ("POS-01", "Caja 1")),)
        assignments = (
            AssignmentRowViewModel("a1", "PRIMARY_RECEIPT_PRINTER", "d1", "PRN-01", "Impresora 1"),
        )
        presenter = ConfiguracionPresenter(Queries(rows=rows, assignments=assignments))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_general")
        page = view._pages["config_general"]
        page.table.selectRow(0)
        assert page.assignments_table.rowCount() == 1

    def test_assign_requires_role_and_device(self, app, monkeypatch):
        rows = (ConfigRowViewModel("w1", ("POS-01", "Caja 1")),)
        devices = (DeviceOptionViewModel("d1", "PRN-01", "Impresora 1", "THERMAL_PRINTER"),)
        presenter = ConfiguracionPresenter(Queries(rows=rows, devices=devices))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_general")
        page = view._pages["config_general"]
        page.table.selectRow(0)

        warnings = []
        import frontend.desktop.modules.configuracion.pages.estaciones_page as page_module
        monkeypatch.setattr(
            page_module.QMessageBox, "warning", staticmethod(lambda *a: warnings.append(a)),
        )
        monkeypatch.setattr(
            page_module.AssignDeviceDialog, "exec_", lambda self: page_module.QDialog.Accepted,
        )
        monkeypatch.setattr(
            page_module.AssignDeviceDialog, "values", lambda self: {"role": None, "device_id": None},
        )
        page._on_assign()
        assert len(warnings) == 1

    def test_assign_warns_when_no_devices_exist(self, app, monkeypatch):
        rows = (ConfigRowViewModel("w1", ("POS-01", "Caja 1")),)
        presenter = ConfiguracionPresenter(Queries(rows=rows, devices=()))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_general")
        page = view._pages["config_general"]
        page.table.selectRow(0)

        warnings = []
        import frontend.desktop.modules.configuracion.pages.estaciones_page as page_module
        monkeypatch.setattr(
            page_module.QMessageBox, "warning", staticmethod(lambda *a: warnings.append(a)),
        )
        page._on_assign()
        assert len(warnings) == 1

    def test_new_requires_branch_type_code_and_name(self, app, monkeypatch):
        presenter = ConfiguracionPresenter(Queries(rows=()))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_general")
        page = view._pages["config_general"]

        warnings = []
        import frontend.desktop.modules.configuracion.pages.estaciones_page as page_module
        monkeypatch.setattr(
            page_module.QMessageBox, "warning", staticmethod(lambda *a: warnings.append(a)),
        )
        monkeypatch.setattr(
            page_module.WorkstationCreateDialog, "exec_", lambda self: page_module.QDialog.Accepted,
        )
        monkeypatch.setattr(
            page_module.WorkstationCreateDialog, "values",
            lambda self: {"branch_id": None, "workstation_type": None, "code": "", "name": ""},
        )
        page._on_new()
        assert len(warnings) == 1


class TestWorkstationDialogs:
    def test_create_dialog_exposes_all_fields(self, app):
        branches = (BranchOptionViewModel("b1", "Principal"),)
        dlg = WorkstationCreateDialog(branch_options=branches)
        assert dlg.objectName() == "standardDialog"
        assert dlg.branch.count() == 2  # placeholder + 1 option
        dlg.branch.set_current_id("b1")
        dlg.code.setText("POS-01")
        dlg.name.setText("Caja 1")
        values = dlg.values()
        assert values["branch_id"] == "b1"
        assert values["code"] == "POS-01"
        assert values["workstation_type"] is None  # nothing selected yet — placeholder
        assert values["offline_enabled"] is True  # defaults checked

    def test_edit_dialog_prefills_values(self, app):
        dlg = WorkstationEditDialog(name="Caja 1", device_identifier="SN-001", operating_system="Windows 11")
        assert dlg.name.text() == "Caja 1"
        assert dlg.device_identifier.text() == "SN-001"
        values = dlg.values()
        assert values == {
            "name": "Caja 1", "device_identifier": "SN-001", "operating_system": "Windows 11",
        }

    def test_block_dialog_disables_confirm_until_reason_is_entered(self, app):
        dlg = BlockWorkstationDialog()
        assert dlg.objectName() == "standardDialog"
        assert dlg._ok_button.isEnabled() is False
        dlg.reason.setPlainText("en revisión")
        assert dlg._ok_button.isEnabled() is True
        assert dlg.reason_text() == "en revisión"


class TestDeviceAssignmentDialogs:
    def test_assign_dialog_exposes_role_and_device(self, app):
        devices = (DeviceOptionViewModel("d1", "PRN-01", "Impresora 1", "THERMAL_PRINTER"),)
        dlg = AssignDeviceDialog(device_options=devices)
        assert dlg.objectName() == "standardDialog"
        assert dlg.device.count() == 2  # placeholder + 1 option
        dlg.role.set_current_id("PRIMARY_RECEIPT_PRINTER")
        dlg.device.set_current_id("d1")
        values = dlg.values()
        assert values == {"role": "PRIMARY_RECEIPT_PRINTER", "device_id": "d1"}

    def test_nothing_selected_yields_none_values(self, app):
        dlg = AssignDeviceDialog()
        values = dlg.values()
        assert values == {"role": None, "device_id": None}


class TestFeatureFlagsPage:
    def test_pending_requests_render_and_action_buttons_exist(self, app):
        pending = (ChangeRequestRowViewModel("req1", "delivery_auto", "GLOBAL", "Sí", "admin-1"),)
        presenter = ConfiguracionPresenter(Queries(pending=pending))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_feature_flags")
        page = view._pages["config_feature_flags"]
        assert page.requests_table.rowCount() == 1
        page.requests_table.selectRow(0)
        assert page.requests_table.selected_row_id() == "req1"
        assert page.approve_button.text() == "Aprobar"
        assert page.reject_button.text() == "Rechazar"
        assert page.apply_button.text() == "Aplicar"

    def test_actions_without_selection_warn_instead_of_crashing(self, app, monkeypatch):
        presenter = ConfiguracionPresenter(Queries(pending=()))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_feature_flags")
        page = view._pages["config_feature_flags"]

        warnings = []
        import frontend.desktop.modules.configuracion.pages.feature_flags_page as page_module
        monkeypatch.setattr(
            page_module.QMessageBox, "warning", staticmethod(lambda *a: warnings.append(a)),
        )
        page._on_approve()
        assert len(warnings) == 1


class TestAparienciaPage:
    def test_set_default_button_present_and_wired(self, app):
        themes = (ThemeRowViewModel("t1", "claro", "Claro", "LIGHT", True),)
        presenter = ConfiguracionPresenter(Queries(themes=themes))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_apariencia")
        page = view._pages["config_apariencia"]
        assert page.action_button.text() == "Marcar como predeterminado"
        assert page._theme_names == {"t1": "Claro"}


class TestDispositivosPage:
    def test_action_buttons_present_and_wired(self, app):
        presenter = ConfiguracionPresenter(Queries(rows=()))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_dispositivos")
        page = view._pages["config_dispositivos"]
        assert page.new_profile_button.text() == "Nuevo perfil"
        assert page.new_device_button.text() == "Nuevo dispositivo"
        assert page.edit_button.text() == "Editar"
        assert page.activate_button.text() == "Activar"
        assert page.deactivate_button.text() == "Desactivar"
        assert page.block_button.text() == "Bloquear"
        assert page.unblock_button.text() == "Desbloquear"
        assert page.retire_button.text() == "Retirar"
        assert page.new_route_button.text() == "Nueva ruta"
        assert page.edit_route_button.text() == "Editar ruta"
        assert page.activate_route_button.text() == "Activar ruta"
        assert page.deactivate_route_button.text() == "Desactivar ruta"

    def test_actions_without_selection_warn_instead_of_crashing(self, app, monkeypatch):
        presenter = ConfiguracionPresenter(Queries(rows=()))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_dispositivos")
        page = view._pages["config_dispositivos"]

        warnings = []
        import frontend.desktop.modules.configuracion.pages.dispositivos_page as page_module
        monkeypatch.setattr(
            page_module.QMessageBox, "warning", staticmethod(lambda *a: warnings.append(a)),
        )
        page._on_edit()
        page._on_block()
        page._on_change_status("ACTIVATE")
        page._on_edit_route()
        page._on_change_route_status("ACTIVATE")
        assert len(warnings) == 5

    def test_new_device_warns_when_no_profiles_exist(self, app, monkeypatch):
        presenter = ConfiguracionPresenter(Queries(rows=(), device_profiles=()))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_dispositivos")
        page = view._pages["config_dispositivos"]

        warnings = []
        import frontend.desktop.modules.configuracion.pages.dispositivos_page as page_module
        monkeypatch.setattr(
            page_module.QMessageBox, "warning", staticmethod(lambda *a: warnings.append(a)),
        )
        page._on_new_device()
        assert len(warnings) == 1

    def test_routes_table_loads_from_presenter(self, app):
        routes = (
            PrintRouteRowViewModel("r1", "SALE_TICKET", "d1", "PRN-01", (), None, None, None, True),
        )
        presenter = ConfiguracionPresenter(Queries(rows=(), print_routes=routes))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_dispositivos")
        page = view._pages["config_dispositivos"]
        assert page.routes_table.rowCount() == 1

    def test_new_route_warns_when_no_devices_exist(self, app, monkeypatch):
        presenter = ConfiguracionPresenter(Queries(rows=(), devices=()))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_dispositivos")
        page = view._pages["config_dispositivos"]

        warnings = []
        import frontend.desktop.modules.configuracion.pages.dispositivos_page as page_module
        monkeypatch.setattr(
            page_module.QMessageBox, "warning", staticmethod(lambda *a: warnings.append(a)),
        )
        page._on_new_route()
        assert len(warnings) == 1


class TestDeviceDialogs:
    def test_profile_create_dialog_exposes_all_fields(self, app):
        dlg = DeviceProfileCreateDialog()
        assert dlg.objectName() == "standardDialog"
        dlg.name.setText("Epson TM-T20III")
        values = dlg.values()
        assert values["name"] == "Epson TM-T20III"
        assert values["device_type"] is None  # nothing selected yet — placeholder
        assert "connection_type" in values and "serial_port" in values and "host" in values
        assert values["paper_profile"] == "" and values["protocol"] == ""  # placeholders → ""

    def test_profile_create_dialog_exposes_printer_fields(self, app):
        dlg = DeviceProfileCreateDialog()
        dlg.paper_profile.set_current_id("PAPER_80MM")
        dlg.protocol.set_current_id("ESC_POS")
        dlg.driver_name.setText("epson_generic")
        values = dlg.values()
        assert values["paper_profile"] == "PAPER_80MM"
        assert values["protocol"] == "ESC_POS"
        assert values["driver_name"] == "epson_generic"

    def test_profile_create_dialog_protocol_combo_offers_scale_protocols(self, app):
        # SET-9 follow-up: the shared `protocol` field must offer both
        # printer and scale vocabularies — whichever applies is enforced
        # server-side by the matching policy, not hidden client-side.
        dlg = DeviceProfileCreateDialog()
        dlg.protocol.set_current_id("TOLEDO_STANDARD")
        assert dlg.values()["protocol"] == "TOLEDO_STANDARD"

    def test_profile_create_dialog_payment_capability_checkboxes_default_unchecked(self, app):
        # SET-10 follow-up: payment terminal capabilities are the one
        # capability set this dialog actually asks for (genuine choice,
        # not deterministic from device_type).
        dlg = DeviceProfileCreateDialog()
        assert dlg.values()["payment_capabilities"] == ()
        dlg.payment_capability_checkboxes["CARD_CHIP"].setChecked(True)
        dlg.payment_capability_checkboxes["CARD_CONTACTLESS"].setChecked(True)
        values = dlg.values()
        assert set(values["payment_capabilities"]) == {"CARD_CHIP", "CARD_CONTACTLESS"}

    def test_device_create_dialog_populates_branch_and_profile_options(self, app):
        branches = (BranchOptionViewModel("b1", "Principal"),)
        profiles = (DeviceProfileOptionViewModel("p1", "Epson TM-T20III", "THERMAL_PRINTER", "USB"),)
        dlg = DeviceCreateDialog(branch_options=branches, profile_options=profiles)
        assert dlg.branch.count() == 2  # placeholder + 1 option
        assert dlg.profile.count() == 2
        dlg.branch.set_current_id("b1")
        dlg.profile.set_current_id("p1")
        values = dlg.values()
        assert values["branch_id"] == "b1"
        assert values["profile_id"] == "p1"

    def test_device_edit_dialog_prefills_values(self, app):
        dlg = DeviceEditDialog(name="Impresora 1", notes="rollo 80mm")
        assert dlg.name.text() == "Impresora 1"
        assert dlg.notes.toPlainText() == "rollo 80mm"
        values = dlg.values()
        assert values == {"name": "Impresora 1", "notes": "rollo 80mm"}

    def test_block_device_dialog_disables_confirm_until_reason_is_entered(self, app):
        dlg = BlockDeviceDialog()
        assert dlg.objectName() == "standardDialog"
        assert dlg._ok_button.isEnabled() is False
        dlg.reason.setPlainText("en revisión")
        assert dlg._ok_button.isEnabled() is True
        assert dlg.reason_text() == "en revisión"


class TestPrintRouteDialogs:
    def test_create_dialog_exposes_all_fields(self, app):
        devices = (DeviceOptionViewModel("d1", "PRN-01", "Impresora 1", "THERMAL_PRINTER"),
                   DeviceOptionViewModel("d2", "PRN-02", "Impresora 2", "THERMAL_PRINTER"))
        branches = (BranchOptionViewModel("b1", "Principal"),)
        dlg = PrintRouteCreateDialog(device_options=devices, branch_options=branches)
        assert dlg.objectName() == "standardDialog"
        dlg.document_type.setText("sale_ticket")
        dlg.primary_device.set_current_id("d1")
        dlg.fallback_codes.setText("PRN-02")
        dlg.branch.set_current_id("b1")
        values = dlg.values()
        assert values["document_type"] == "sale_ticket"
        assert values["primary_device_id"] == "d1"
        assert values["fallback_device_ids"] == ("d2",)
        assert values["branch_id"] == "b1"

    def test_create_dialog_ignores_unknown_fallback_codes(self, app):
        devices = (DeviceOptionViewModel("d1", "PRN-01", "Impresora 1", "THERMAL_PRINTER"),)
        dlg = PrintRouteCreateDialog(device_options=devices)
        dlg.fallback_codes.setText("PRN-99, PRN-01")
        assert dlg.values()["fallback_device_ids"] == ("d1",)

    def test_edit_dialog_prefills_primary_and_fallback(self, app):
        devices = (DeviceOptionViewModel("d1", "PRN-01", "Impresora 1", "THERMAL_PRINTER"),
                   DeviceOptionViewModel("d2", "PRN-02", "Impresora 2", "THERMAL_PRINTER"))
        dlg = PrintRouteEditDialog(
            device_options=devices, primary_device_code="PRN-01", fallback_codes="PRN-02",
        )
        assert dlg.primary_device.current_id() == "d1"
        assert dlg.fallback_codes.text() == "PRN-02"
        values = dlg.values()
        assert values["primary_device_id"] == "d1"
        assert values["fallback_device_ids"] == ("d2",)


class TestDocumentosPage:
    def test_new_template_button_present_and_wired(self, app):
        presenter = ConfiguracionPresenter(Queries(rows=()))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_documentos")
        page = view._pages["config_documentos"]
        assert page.new_template_button.text() == "Nueva plantilla"
        assert page.new_version_button.text() == "Nueva versión"
        assert page.submit_button.text() == "Enviar a aprobación"
        assert page.approve_button.text() == "Aprobar"
        assert page.reject_button.text() == "Rechazar"
        assert page.activate_button.text() == "Activar"
        assert page.deactivate_button.text() == "Desactivar"
        assert page.expire_button.text() == "Expirar"
        assert page.archive_button.text() == "Archivar"
        assert page.edit_template_button.text() == "Editar plantilla"
        assert page.activate_template_button.text() == "Activar plantilla"
        assert page.deactivate_template_button.text() == "Desactivar plantilla"
        assert page.new_campaign_button.text() == "Nueva campaña"
        assert page.edit_campaign_button.text() == "Editar campaña"
        assert page.activate_campaign_button.text() == "Activar campaña"
        assert page.deactivate_campaign_button.text() == "Desactivar campaña"

    def test_campaigns_table_loads_from_presenter(self, app):
        campaigns = (
            MarketingCampaignRowViewModel("c1", "goal_near", "FOMO", "Te faltan {n} compras.", 90, False, (), True),
        )
        presenter = ConfiguracionPresenter(Queries(rows=(), marketing_campaigns=campaigns))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_documentos")
        page = view._pages["config_documentos"]
        assert page.campaigns_table.rowCount() == 1

    def test_selecting_a_template_loads_its_versions(self, app):
        rows = (ConfigRowViewModel("tpl1", ("SALE_TICKET", "Ticket de venta")),)
        versions = (
            TemplateVersionRowViewModel("v1", "tpl1", 1, "ACTIVE", "{{items}}", None, "admin-1"),
        )
        presenter = ConfiguracionPresenter(Queries(rows=rows, template_versions=versions))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_documentos")
        page = view._pages["config_documentos"]
        page.table.selectRow(0)
        assert page._selected_template_id == "tpl1"
        assert page.versions_table.rowCount() == 1

    def test_actions_without_selection_warn_instead_of_crashing(self, app, monkeypatch):
        presenter = ConfiguracionPresenter(Queries(rows=()))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_documentos")
        page = view._pages["config_documentos"]

        warnings = []
        import frontend.desktop.modules.configuracion.pages.documentos_page as page_module
        monkeypatch.setattr(
            page_module.QMessageBox, "warning", staticmethod(lambda *a: warnings.append(a)),
        )
        page._on_reject()
        page._on_change_status("APPROVE")
        page._on_edit_template()
        page._on_change_template_status("ACTIVATE")
        page._on_edit_campaign()
        page._on_change_campaign_status("ACTIVATE")
        assert len(warnings) == 6

    def test_edit_template_prefills_from_get_template(self, app, monkeypatch):
        rows = (ConfigRowViewModel("tpl1", ("SALE_TICKET", "Ticket de venta")),)
        template = TemplateDetailViewModel("tpl1", "SALE_TICKET", "Ticket de venta", "ventas", "desc")
        presenter = ConfiguracionPresenter(Queries(rows=rows, template=template))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_documentos")
        page = view._pages["config_documentos"]
        page.table.selectRow(0)

        import frontend.desktop.modules.configuracion.pages.documentos_page as page_module
        captured = {}

        def _fake_exec(self):
            captured["name"] = self.name.text()
            captured["module"] = self.module.text()
            return page_module.QDialog.Rejected

        monkeypatch.setattr(page_module.DocumentTemplateEditDialog, "exec_", _fake_exec)
        page._on_edit_template()
        assert captured == {"name": "Ticket de venta", "module": "ventas"}

    def test_edit_campaign_prefills_from_selection(self, app, monkeypatch):
        campaigns = (
            MarketingCampaignRowViewModel(
                "c1", "goal_near", "FOMO", "Te faltan {n} compras.", 90, True, (), True,
            ),
        )
        presenter = ConfiguracionPresenter(Queries(rows=(), marketing_campaigns=campaigns))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_documentos")
        page = view._pages["config_documentos"]
        page.campaigns_table.selectRow(0)

        import frontend.desktop.modules.configuracion.pages.documentos_page as page_module
        captured = {}

        def _fake_exec(self):
            captured["message_template"] = self.message_template.text()
            captured["priority"] = self.priority.text()
            captured["requires_customer"] = self.requires_customer.isChecked()
            return page_module.QDialog.Rejected

        monkeypatch.setattr(page_module.MarketingCampaignEditDialog, "exec_", _fake_exec)
        page._on_edit_campaign()
        assert captured == {
            "message_template": "Te faltan {n} compras.", "priority": "90", "requires_customer": True,
        }


class TestDocumentTemplateDialogs:
    def test_create_dialog_exposes_all_fields(self, app):
        dlg = DocumentTemplateCreateDialog()
        assert dlg.objectName() == "standardDialog"
        dlg.name.setText("Ticket de venta")
        dlg.module.setText("ventas")
        dlg.content.setPlainText("{{items}}")
        values = dlg.values()
        assert values["name"] == "Ticket de venta"
        assert values["module"] == "ventas"
        assert values["content"] == "{{items}}"
        assert values["document_type"] is None  # nothing selected yet — placeholder

    def test_edit_dialog_prefills_values(self, app):
        dlg = DocumentTemplateEditDialog(name="Ticket de venta", module="ventas", description="desc")
        assert dlg.name.text() == "Ticket de venta"
        assert dlg.module.text() == "ventas"
        assert dlg.description.text() == "desc"
        values = dlg.values()
        assert values == {"name": "Ticket de venta", "module": "ventas", "description": "desc"}

    def test_new_version_dialog_prefills_previous_content(self, app):
        dlg = NewTemplateVersionDialog(previous_content="{{items}}")
        assert dlg.content.toPlainText() == "{{items}}"
        dlg.content.setPlainText("{{items}} v2")
        assert dlg.content_text() == "{{items}} v2"

    def test_reject_version_dialog_disables_confirm_until_reason_is_entered(self, app):
        dlg = RejectTemplateVersionDialog()
        assert dlg.objectName() == "standardDialog"
        assert dlg._ok_button.isEnabled() is False
        dlg.reason.setPlainText("Falta el logo")
        assert dlg._ok_button.isEnabled() is True
        assert dlg.reason_text() == "Falta el logo"


class TestMarketingCampaignDialogs:
    def test_create_dialog_exposes_all_fields(self, app):
        dlg = MarketingCampaignCreateDialog()
        assert dlg.objectName() == "standardDialog"
        dlg.code.setText("goal_near")
        dlg.category.set_current_id("FOMO")
        dlg.message_template.setText("Te faltan {n} compras.")
        dlg.priority.setText("90")
        dlg.requires_customer.setChecked(True)
        dlg.rules.setText("points_balance<=50, subtotal>=100")
        values = dlg.values()
        assert values["code"] == "goal_near"
        assert values["category"] == "FOMO"
        assert values["message_template"] == "Te faltan {n} compras."
        assert values["priority"] == 90
        assert values["requires_customer"] is True
        assert len(values["rules"]) == 2
        assert values["rules"][0].metric == "points_balance"
        assert values["rules"][1].metric == "subtotal"

    def test_create_dialog_ignores_malformed_rule_entries(self, app):
        dlg = MarketingCampaignCreateDialog()
        dlg.rules.setText("not_a_valid_rule, points_balance<=50")
        values = dlg.values()
        assert len(values["rules"]) == 1
        assert values["rules"][0].metric == "points_balance"

    def test_create_dialog_defaults_priority_to_zero_on_blank_input(self, app):
        dlg = MarketingCampaignCreateDialog()
        dlg.priority.setText("")
        assert dlg.values()["priority"] == 0

    def test_edit_dialog_prefills_values(self, app):
        dlg = MarketingCampaignEditDialog(
            message_template="Te faltan {n} compras.", priority=90, requires_customer=True,
            rules_text="points_balance<=50",
        )
        assert dlg.message_template.text() == "Te faltan {n} compras."
        assert dlg.priority.text() == "90"
        assert dlg.requires_customer.isChecked() is True
        assert dlg.rules.text() == "points_balance<=50"
        values = dlg.values()
        assert values["message_template"] == "Te faltan {n} compras."
        assert len(values["rules"]) == 1


class TestEmpresaPage:
    def test_shows_unconfigured_message_when_no_company_exists(self, app):
        presenter = ConfiguracionPresenter(Queries(rows=(), company=None))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_empresa")
        page = view._pages["config_empresa"]
        assert "no configurada" in page.company_summary_label.text().lower()

    def test_shows_company_summary_when_configured(self, app):
        company = CompanyProfileDetailViewModel(
            entity_id="c1", legal_name="Super Junior de Chihuahua SA de CV", commercial_name="SJC",
            tax_id="", business_name="", default_currency="MXN", default_timezone="America/Chihuahua",
            default_locale="es-MX", fiscal_regime_reference=None, address="", phone=None, email=None,
            website=None, logo_asset_id=None,
        )
        presenter = ConfiguracionPresenter(Queries(rows=(), company=company))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_empresa")
        page = view._pages["config_empresa"]
        assert "Super Junior de Chihuahua SA de CV" in page.company_summary_label.text()
        assert "SJC" in page.company_summary_label.text()

    def test_action_buttons_present_and_wired(self, app):
        presenter = ConfiguracionPresenter(Queries(rows=()))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_empresa")
        page = view._pages["config_empresa"]
        assert page.edit_company_button.text() == "Editar empresa"
        assert page.new_branch_button.text() == "Nueva sucursal"
        assert page.edit_branch_button.text() == "Editar sucursal"

    def test_new_branch_warns_when_no_unregistered_branches_exist(self, app, monkeypatch):
        presenter = ConfiguracionPresenter(Queries(rows=(), unregistered_branches=()))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_empresa")
        page = view._pages["config_empresa"]

        warnings = []
        import frontend.desktop.modules.configuracion.pages.empresa_page as page_module
        monkeypatch.setattr(
            page_module.QMessageBox, "warning", staticmethod(lambda *a: warnings.append(a)),
        )
        page._on_new_branch()
        assert len(warnings) == 1

    def test_edit_branch_without_selection_warns_instead_of_crashing(self, app, monkeypatch):
        presenter = ConfiguracionPresenter(Queries(rows=()))
        view = ConfiguracionView(presenter, has_permission=lambda _p: True)
        view.show_route("config_empresa")
        page = view._pages["config_empresa"]

        warnings = []
        import frontend.desktop.modules.configuracion.pages.empresa_page as page_module
        monkeypatch.setattr(
            page_module.QMessageBox, "warning", staticmethod(lambda *a: warnings.append(a)),
        )
        page._on_edit_branch()
        assert len(warnings) == 1


class TestCompanyBranchDialogs:
    def test_company_dialog_prefills_from_existing_profile(self, app):
        company = CompanyProfileDetailViewModel(
            entity_id="c1", legal_name="Super Junior de Chihuahua SA de CV", commercial_name="SJC",
            tax_id="ABC123", business_name="", default_currency="MXN",
            default_timezone="America/Chihuahua", default_locale="es-MX", fiscal_regime_reference="601",
            address="Av. Siempre Viva 123", phone="+5216141234567", email="ventas@sjc.mx",
            website="https://sjc.mx", logo_asset_id=None,
        )
        dlg = CompanyProfileDialog(profile=company)
        assert dlg.legal_name.text() == "Super Junior de Chihuahua SA de CV"
        assert dlg.tax_id.text() == "ABC123"
        values = dlg.values()
        assert values["legal_name"] == "Super Junior de Chihuahua SA de CV"
        assert values["default_currency"] == "MXN"

    def test_branch_create_dialog_populates_branch_options_and_hours(self, app):
        branches = (BranchOptionViewModel("b1", "Principal"),)
        dlg = BranchProfileCreateDialog(branch_options=branches)
        assert dlg.branch.count() == 2  # placeholder + 1 option
        dlg.branch.set_current_id("b1")
        dlg.code.setText("SUC-01")
        dlg.name.setText("Sucursal San Bartolo")
        values = dlg.values()
        assert values["branch_id"] == "b1"
        assert values["code"] == "SUC-01"
        assert values["opening_time"] is None  # "Definir horario" not checked

    def test_branch_edit_dialog_prefills_hours_when_set(self, app):
        profile = BranchProfileDetailViewModel(
            entity_id="b1", branch_id="b1", code="SUC-01", name="Sucursal San Bartolo", address="",
            phone=None, timezone="America/Chihuahua", locale="es-MX", opening_time="09:00:00",
            closing_time="20:00:00", operation_days=("MON", "TUE"), ticket_header="Bienvenido",
            ticket_footer="Gracias",
        )
        dlg = BranchProfileEditDialog(profile=profile)
        assert dlg.name.text() == "Sucursal San Bartolo"
        assert dlg.define_hours.isChecked() is True
        assert dlg.day_checkboxes["MON"].isChecked() is True
        assert dlg.ticket_header.toPlainText() == "Bienvenido"
        values = dlg.values()
        assert values["opening_time"] is not None
        assert values["operation_days"] == ("MON", "TUE")

    def test_branch_edit_dialog_leaves_hours_unset_when_none_prefilled(self, app):
        profile = BranchProfileDetailViewModel(
            entity_id="b1", branch_id="b1", code="SUC-01", name="Sucursal San Bartolo", address="",
            phone=None, timezone="", locale="", opening_time=None, closing_time=None,
            operation_days=(), ticket_header="", ticket_footer="",
        )
        dlg = BranchProfileEditDialog(profile=profile)
        assert dlg.define_hours.isChecked() is False


class TestDialogs:
    def test_reject_dialog_disables_confirm_until_reason_is_entered(self, app):
        dlg = RejectChangeRequestDialog()
        assert dlg.objectName() == "standardDialog"
        assert dlg._ok_button.isEnabled() is False
        dlg.reason.setPlainText("No autorizado")
        assert dlg._ok_button.isEnabled() is True
        assert dlg.reason_text() == "No autorizado"

    def test_set_default_theme_dialog_shows_theme_name(self, app):
        from PyQt5.QtWidgets import QLabel

        dlg = SetDefaultThemeDialog(theme_name="Oscuro")
        assert dlg.objectName() == "standardDialog"
        labels = [w.text() for w in dlg.findChildren(QLabel)]
        assert any("Oscuro" in text for text in labels)
