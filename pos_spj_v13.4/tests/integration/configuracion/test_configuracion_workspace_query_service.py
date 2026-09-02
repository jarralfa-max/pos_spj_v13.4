"""UI/UX phase — ConfiguracionWorkspaceQueryService against a real
(in-memory) SQLite born-clean schema. The first read path exercised
against all 9 SET-0..23 bounded contexts together.
"""

from __future__ import annotations

import pytest

from backend.application.queries.configuracion.workspace_query_service import (
    ConfiguracionWorkspaceQueryService,
)
from backend.domain.appearance.entities.theme import Theme
from backend.domain.appearance.enums import ThemeMode
from backend.domain.feature_flags.entities.feature_flag import FeatureFlag
from backend.domain.feature_flags.entities.feature_flag_change_request import FeatureFlagChangeRequest
from backend.domain.feature_flags.enums import FeatureFlagScopeType
from backend.domain.offline.entities.cache_expiration_policy import CacheExpirationPolicy
from backend.infrastructure.db.repositories.appearance.theme_repository import SqliteThemeRepository
from backend.infrastructure.db.repositories.feature_flags.feature_flag_change_request_repository import (
    SqliteFeatureFlagChangeRequestRepository,
)
from backend.infrastructure.db.repositories.feature_flags.feature_flag_repository import (
    SqliteFeatureFlagRepository,
)
from backend.infrastructure.db.repositories.offline.cache_expiration_policy_repository import (
    SqliteCacheExpirationPolicyRepository,
)
from tests.integration._born_clean_db import make_db

ALL_PAGE_IDS = (
    "config_general", "config_dispositivos", "config_documentos", "config_pantalla_cliente",
    "config_integraciones", "config_feature_flags", "config_apariencia", "config_notificaciones",
    "config_offline",
)


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


@pytest.fixture
def query_service(conn):
    return ConfiguracionWorkspaceQueryService(conn)


class TestPageDispatch:
    def test_every_nav_page_id_is_a_real_handler(self, query_service):
        for page_id in ALL_PAGE_IDS:
            model = query_service.page(page_id=page_id)
            assert model.columns

    def test_unknown_page_id_raises(self, query_service):
        with pytest.raises(KeyError):
            query_service.page(page_id="config_does_not_exist")

    def test_empty_database_returns_empty_pages_not_errors(self, query_service):
        for page_id in ALL_PAGE_IDS:
            model = query_service.page(page_id=page_id)
            assert model.rows == ()
            assert model.empty_message


class TestGeneralPage:
    """SET-6 follow-up (2026-08-22) — General now lists the full
    workstation lifecycle (not just ACTIVE), same reasoning as
    Dispositivos' `list_all()` switch."""

    def test_lists_workstations_including_non_active(self, conn, query_service):
        from backend.domain.settings.entities.workstation import Workstation
        from backend.domain.settings.enums import WorkstationType
        from backend.infrastructure.db.repositories.settings.workstation_repository import (
            SqliteWorkstationRepository,
        )

        branch_id = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()[0]
        workstation = Workstation.create(
            branch_id=branch_id, code="POS-01", name="Caja 1", workstation_type=WorkstationType.POS,
        )
        workstation.deactivate()
        SqliteWorkstationRepository(conn).save(workstation)
        conn.commit()

        model = query_service.page(page_id="config_general")
        assert len(model.rows) == 1
        assert model.rows[0].cells[3] == "INACTIVE"

    def test_get_workstation(self, conn, query_service):
        from backend.domain.settings.entities.workstation import Workstation
        from backend.domain.settings.enums import WorkstationType
        from backend.infrastructure.db.repositories.settings.workstation_repository import (
            SqliteWorkstationRepository,
        )

        branch_id = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()[0]
        workstation = Workstation.create(
            branch_id=branch_id, code="POS-01", name="Caja 1", workstation_type=WorkstationType.POS,
            device_identifier="SN-001", operating_system="Windows 11",
        )
        SqliteWorkstationRepository(conn).save(workstation)
        conn.commit()

        detail = query_service.get_workstation(workstation.id)
        assert detail is not None
        assert detail.code == "POS-01"
        assert detail.device_identifier == "SN-001"
        assert detail.operating_system == "Windows 11"

    def test_get_workstation_returns_none_for_unknown_id(self, conn, query_service):
        from backend.shared.ids import new_uuid
        assert query_service.get_workstation(new_uuid()) is None

    def test_list_workstation_assignments(self, conn, query_service):
        from backend.domain.device_management.entities.device import Device
        from backend.domain.device_management.entities.device_profile import DeviceProfile
        from backend.domain.device_management.entities.workstation_device_assignment import (
            WorkstationDeviceAssignment,
        )
        from backend.domain.device_management.enums import AssignmentRole, ConnectionType, DeviceType
        from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
        from backend.domain.settings.entities.workstation import Workstation
        from backend.domain.settings.enums import WorkstationType
        from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
            SqliteDeviceProfileRepository,
        )
        from backend.infrastructure.db.repositories.device_management.device_repository import (
            SqliteDeviceRepository,
        )
        from backend.infrastructure.db.repositories.device_management.workstation_device_assignment_repository import (
            SqliteWorkstationDeviceAssignmentRepository,
        )
        from backend.infrastructure.db.repositories.settings.workstation_repository import (
            SqliteWorkstationRepository,
        )

        branch_id = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()[0]
        workstation = Workstation.create(
            branch_id=branch_id, code="POS-01", name="Caja 1", workstation_type=WorkstationType.POS,
        )
        SqliteWorkstationRepository(conn).save(workstation)
        profile = DeviceProfile.create(
            name="Epson TM-T20III", device_type=DeviceType.THERMAL_PRINTER,
            connection_profile=ConnectionProfile.create(ConnectionType.USB),
        )
        SqliteDeviceProfileRepository(conn).save(profile)
        device = Device.create(branch_id=branch_id, profile_id=profile.id, code="PRN-01", name="Impresora 1")
        SqliteDeviceRepository(conn).save(device)
        assignment = WorkstationDeviceAssignment.assign(
            workstation_id=workstation.id, device_id=device.id,
            role=AssignmentRole.PRIMARY_RECEIPT_PRINTER,
        )
        SqliteWorkstationDeviceAssignmentRepository(conn).save(assignment)
        conn.commit()

        rows = query_service.list_workstation_assignments(workstation.id)
        assert len(rows) == 1
        assert rows[0].role == "PRIMARY_RECEIPT_PRINTER"
        assert rows[0].device_code == "PRN-01"
        assert rows[0].device_name == "Impresora 1"


class TestFeatureFlagsPage:
    def test_lists_active_flags(self, conn, query_service):
        flag_repo = SqliteFeatureFlagRepository(conn)
        flag_repo.save(FeatureFlag.create(code="delivery_auto", name="Auto delivery"))
        conn.commit()

        model = query_service.page(page_id="config_feature_flags")
        assert len(model.rows) == 1
        assert model.rows[0].cells[0] == "delivery_auto"

    def test_search_filters_by_any_cell(self, conn, query_service):
        flag_repo = SqliteFeatureFlagRepository(conn)
        flag_repo.save(FeatureFlag.create(code="delivery_auto", name="Auto delivery"))
        flag_repo.save(FeatureFlag.create(code="loyalty_v2", name="Loyalty v2"))
        conn.commit()

        model = query_service.page(page_id="config_feature_flags", search="loyalty")
        assert len(model.rows) == 1
        assert model.rows[0].cells[0] == "loyalty_v2"

    def test_list_pending_change_requests(self, conn, query_service):
        flag_repo = SqliteFeatureFlagRepository(conn)
        flag = FeatureFlag.create(code="delivery_auto", name="Auto delivery")
        flag_repo.save(flag)
        conn.commit()
        request_repo = SqliteFeatureFlagChangeRequestRepository(conn)
        request = FeatureFlagChangeRequest.create(
            flag_id=flag.id, scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None, proposed_enabled=True,
            requested_by_user_id="admin-1",
        )
        request_repo.save(request)
        conn.commit()

        pending = query_service.list_pending_feature_flag_change_requests()
        assert len(pending) == 1
        assert pending[0].flag_code == "delivery_auto"
        assert pending[0].requested_by == "admin-1"

class TestAparienciaPage:
    def test_lists_active_themes_with_default_flag(self, conn, query_service):
        theme_repo = SqliteThemeRepository(conn)
        theme_repo.save(Theme.create(code="claro", name="Claro", mode=ThemeMode.LIGHT, is_default=True))
        theme_repo.save(Theme.create(code="oscuro", name="Oscuro", mode=ThemeMode.DARK))
        conn.commit()

        model = query_service.page(page_id="config_apariencia")
        assert len(model.rows) == 2
        default_row = next(row for row in model.rows if row.cells[0] == "claro")
        assert default_row.cells[-1] == "Sí"

    def test_list_themes_view_model(self, conn, query_service):
        theme_repo = SqliteThemeRepository(conn)
        theme = Theme.create(code="claro", name="Claro", mode=ThemeMode.LIGHT, is_default=True)
        theme_repo.save(theme)
        conn.commit()

        themes = query_service.list_themes()
        assert len(themes) == 1
        assert themes[0].code == "claro"
        assert themes[0].is_default is True

    def test_light_dark_theme_codes(self, query_service):
        light, dark = query_service.list_light_dark_theme_codes()
        assert light == "LIGHT"
        assert dark == "DARK"


class TestOfflinePage:
    def test_lists_active_expiration_policies(self, conn, query_service):
        policy_repo = SqliteCacheExpirationPolicyRepository(conn)
        policy_repo.save(CacheExpirationPolicy.create(entity_type="product", ttl_seconds=3600))
        conn.commit()

        model = query_service.page(page_id="config_offline")
        assert len(model.rows) == 1
        assert model.rows[0].cells == ("product", "3600", "Sí")


class TestDispositivosPageAndDeviceManagementSupport:
    def test_dispositivos_page_lists_devices_in_any_status_not_only_active(self, conn, query_service):
        from backend.domain.device_management.entities.device import Device
        from backend.domain.device_management.entities.device_profile import DeviceProfile
        from backend.domain.device_management.enums import ConnectionType, DeviceType
        from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
        from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
            SqliteDeviceProfileRepository,
        )
        from backend.infrastructure.db.repositories.device_management.device_repository import (
            SqliteDeviceRepository,
        )

        branch_id = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()[0]
        profile = DeviceProfile.create(
            name="Epson TM-T20III", device_type=DeviceType.THERMAL_PRINTER,
            connection_profile=ConnectionProfile.create(ConnectionType.USB),
        )
        SqliteDeviceProfileRepository(conn).save(profile)
        device = Device.create(branch_id=branch_id, profile_id=profile.id, code="PRN-01", name="Impresora 1")
        device.deactivate()
        SqliteDeviceRepository(conn).save(device)
        conn.commit()

        model = query_service.page(page_id="config_dispositivos")
        assert len(model.rows) == 1
        assert model.rows[0].cells[2] == "INACTIVE"

    def test_list_device_profiles(self, conn, query_service):
        from backend.domain.device_management.entities.device_profile import DeviceProfile
        from backend.domain.device_management.enums import ConnectionType, DeviceType
        from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
        from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
            SqliteDeviceProfileRepository,
        )

        profile = DeviceProfile.create(
            name="Bascula Toledo", device_type=DeviceType.SCALE,
            connection_profile=ConnectionProfile.create(ConnectionType.USB),
        )
        SqliteDeviceProfileRepository(conn).save(profile)
        conn.commit()

        options = query_service.list_device_profiles()
        assert len(options) == 1
        assert options[0].name == "Bascula Toledo"
        assert options[0].device_type == "SCALE"

    def test_list_branches(self, conn, query_service):
        branches = query_service.list_branches()
        assert len(branches) >= 1
        assert all(b.name for b in branches)

    def test_get_device(self, conn, query_service):
        from backend.domain.device_management.entities.device import Device
        from backend.domain.device_management.entities.device_profile import DeviceProfile
        from backend.domain.device_management.enums import ConnectionType, DeviceType
        from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
        from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
            SqliteDeviceProfileRepository,
        )
        from backend.infrastructure.db.repositories.device_management.device_repository import (
            SqliteDeviceRepository,
        )

        branch_id = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()[0]
        profile = DeviceProfile.create(
            name="Epson TM-T20III", device_type=DeviceType.THERMAL_PRINTER,
            connection_profile=ConnectionProfile.create(ConnectionType.USB),
        )
        SqliteDeviceProfileRepository(conn).save(profile)
        device = Device.create(
            branch_id=branch_id, profile_id=profile.id, code="PRN-01", name="Impresora 1",
            notes="rollo 80mm",
        )
        SqliteDeviceRepository(conn).save(device)
        conn.commit()

        detail = query_service.get_device(device.id)
        assert detail is not None
        assert detail.code == "PRN-01"
        assert detail.notes == "rollo 80mm"

    def test_get_device_returns_none_for_unknown_id(self, conn, query_service):
        from backend.shared.ids import new_uuid
        assert query_service.get_device(new_uuid()) is None

    def test_list_devices(self, conn, query_service):
        from backend.domain.device_management.entities.device import Device
        from backend.domain.device_management.entities.device_profile import DeviceProfile
        from backend.domain.device_management.enums import ConnectionType, DeviceType
        from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
        from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
            SqliteDeviceProfileRepository,
        )
        from backend.infrastructure.db.repositories.device_management.device_repository import (
            SqliteDeviceRepository,
        )

        branch_id = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()[0]
        profile = DeviceProfile.create(
            name="Epson TM-T20III", device_type=DeviceType.THERMAL_PRINTER,
            connection_profile=ConnectionProfile.create(ConnectionType.USB),
        )
        SqliteDeviceProfileRepository(conn).save(profile)
        device = Device.create(branch_id=branch_id, profile_id=profile.id, code="PRN-01", name="Impresora 1")
        SqliteDeviceRepository(conn).save(device)
        conn.commit()

        options = query_service.list_devices()
        assert len(options) == 1
        assert options[0].code == "PRN-01"
        assert options[0].device_type == "THERMAL_PRINTER"

    def test_list_print_routes(self, conn, query_service):
        from backend.domain.device_management.entities.device import Device
        from backend.domain.device_management.entities.device_profile import DeviceProfile
        from backend.domain.device_management.entities.print_route import PrintRoute
        from backend.domain.device_management.enums import ConnectionType, DeviceType
        from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
        from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
            SqliteDeviceProfileRepository,
        )
        from backend.infrastructure.db.repositories.device_management.device_repository import (
            SqliteDeviceRepository,
        )
        from backend.infrastructure.db.repositories.device_management.print_route_repository import (
            SqlitePrintRouteRepository,
        )

        branch_id = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()[0]
        profile = DeviceProfile.create(
            name="Epson TM-T20III", device_type=DeviceType.THERMAL_PRINTER,
            connection_profile=ConnectionProfile.create(ConnectionType.USB),
        )
        SqliteDeviceProfileRepository(conn).save(profile)
        device = Device.create(branch_id=branch_id, profile_id=profile.id, code="PRN-01", name="Impresora 1")
        SqliteDeviceRepository(conn).save(device)
        route = PrintRoute.create(document_type="SALE_TICKET", primary_device_id=device.id)
        route.deactivate()
        SqlitePrintRouteRepository(conn).save(route)
        conn.commit()

        rows = query_service.list_print_routes()
        assert len(rows) == 1
        assert rows[0].document_type == "SALE_TICKET"
        assert rows[0].primary_device_code == "PRN-01"
        assert rows[0].active is False


class TestDocumentosQuerySupport:
    def test_get_template(self, conn, query_service):
        from backend.application.use_cases.configuracion.document_template_use_cases import (
            CreateDocumentTemplateUseCase,
        )

        template, _version = CreateDocumentTemplateUseCase(conn).execute(
            document_type="SALE_TICKET", name="Ticket de venta", module="ventas",
            content_format="ESC_POS", content="{{items}}",
        )
        detail = query_service.get_template(template.id)
        assert detail is not None
        assert detail.name == "Ticket de venta"
        assert detail.module == "ventas"

    def test_get_template_returns_none_for_unknown_id(self, conn, query_service):
        from backend.shared.ids import new_uuid
        assert query_service.get_template(new_uuid()) is None

    def test_documentos_page_lists_templates_including_inactive(self, conn, query_service):
        # SET-11 follow-up: same list_all() switch as
        # _page_dispositivos/_page_general/list_print_routes — a
        # management page needs to see and act on inactive templates too.
        from backend.application.use_cases.configuracion.document_template_use_cases import (
            ChangeDocumentTemplateStatusUseCase,
            CreateDocumentTemplateUseCase,
            DocumentTemplateStatusAction,
        )

        template, _version = CreateDocumentTemplateUseCase(conn).execute(
            document_type="SALE_TICKET", name="Ticket de venta", module="ventas",
            content_format="ESC_POS", content="{{items}}",
        )
        ChangeDocumentTemplateStatusUseCase(conn).execute(
            template_id=template.id, action=DocumentTemplateStatusAction.DEACTIVATE,
        )

        model = query_service.page(page_id="config_documentos")
        assert len(model.rows) == 1
        assert model.rows[0].cells[-1] == "No"

    def test_list_template_versions(self, conn, query_service):
        from backend.application.use_cases.configuracion.document_template_use_cases import (
            CreateDocumentTemplateUseCase,
            CreateNextTemplateVersionUseCase,
        )

        template, v1 = CreateDocumentTemplateUseCase(conn).execute(
            document_type="SALE_TICKET", name="Ticket de venta", module="ventas",
            content_format="ESC_POS", content="{{items}}",
        )
        CreateNextTemplateVersionUseCase(conn).execute(version_id=v1.id, content="{{items}} v2")

        versions = query_service.list_template_versions(template.id)
        assert len(versions) == 2
        assert {v.version for v in versions} == {1, 2}

    def test_list_template_versions_empty_for_unknown_template(self, conn, query_service):
        from backend.shared.ids import new_uuid
        assert query_service.list_template_versions(new_uuid()) == ()


class TestEmpresaPageAndQuerySupport:
    def test_get_company_profile_returns_none_when_unconfigured(self, conn, query_service):
        assert query_service.get_company_profile() is None

    def test_get_company_profile(self, conn, query_service):
        from backend.application.use_cases.configuracion.company_branch_use_cases import (
            SaveCompanyProfileUseCase,
        )

        SaveCompanyProfileUseCase(conn).execute(
            legal_name="Super Junior de Chihuahua SA de CV", default_currency="MXN",
            default_timezone="America/Chihuahua", default_locale="es-MX",
        )
        detail = query_service.get_company_profile()
        assert detail is not None
        assert detail.legal_name == "Super Junior de Chihuahua SA de CV"
        assert detail.default_currency == "MXN"

    def test_list_unregistered_branches_excludes_branches_with_a_profile(self, conn, query_service):
        from backend.application.use_cases.configuracion.company_branch_use_cases import (
            RegisterBranchProfileUseCase,
        )

        branch_id = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()[0]
        assert len(query_service.list_unregistered_branches()) == 1

        RegisterBranchProfileUseCase(conn).execute(branch_id=branch_id, code="SUC-01", name="Sucursal Test")
        assert query_service.list_unregistered_branches() == ()

    def test_empresa_page_lists_branch_profiles(self, conn, query_service):
        from backend.application.use_cases.configuracion.company_branch_use_cases import (
            RegisterBranchProfileUseCase,
        )

        branch_id = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()[0]
        RegisterBranchProfileUseCase(conn).execute(branch_id=branch_id, code="SUC-01", name="Sucursal Test")

        model = query_service.page(page_id="config_empresa")
        assert len(model.rows) == 1
        assert model.rows[0].cells[0] == "SUC-01"

    def test_get_branch_profile(self, conn, query_service):
        from backend.application.use_cases.configuracion.company_branch_use_cases import (
            RegisterBranchProfileUseCase,
        )

        branch_id = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()[0]
        RegisterBranchProfileUseCase(conn).execute(
            branch_id=branch_id, code="SUC-01", name="Sucursal Test", ticket_header="Bienvenido",
        )
        detail = query_service.get_branch_profile(branch_id)
        assert detail is not None
        assert detail.code == "SUC-01"
        assert detail.ticket_header == "Bienvenido"

    def test_get_branch_profile_returns_none_for_unknown_id(self, conn, query_service):
        from backend.shared.ids import new_uuid
        assert query_service.get_branch_profile(new_uuid()) is None
