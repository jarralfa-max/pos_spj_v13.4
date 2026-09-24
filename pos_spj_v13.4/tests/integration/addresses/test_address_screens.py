"""El estándar de direcciones llega de verdad a cada pantalla.

Una prueba por pantalla, de extremo a extremo: el diálogo produce la dirección
con `AddressInput`, el caso de uso REAL la guarda y se lee la fila. Lo que se
comprueba en todas es lo mismo: que las coordenadas de un proveedor de mapas
lleguen a la base, y que una dirección capturada a mano llegue SIN ellas.

Delivery tiene su propia prueba en `tests/integration/orders_delivery/
test_new_order_page.py` (`test_a_geocoded_address_reaches_the_order...`).
"""

import sqlite3

import pytest
from PyQt5.QtWidgets import QApplication

from backend.application.addresses import AddressSource, StructuredAddress
from frontend.desktop.components.address_input import AddressInput, SyncRunner


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


_GEO = StructuredAddress(
    street="Avenida Juárez", exterior_number="120", neighborhood="Centro",
    municipality="Cuauhtémoc", state="Ciudad de México", postal_code="06050",
    latitude=19.4351, longitude=-99.1478, source=AddressSource.MAPBOX)


class _TodoPermitido:
    is_active = True
    user_id = "user-1"
    active_branch_id = "branch-1"

    def tiene_permiso(self, _code: str) -> bool:
        return True


# ── Proveedores ──────────────────────────────────────────────────────────────

@pytest.fixture
def supplier_presenter():
    from backend.infrastructure.db.schema.supplier_schema import create_supplier_schema
    from frontend.desktop.modules.finance.suppliers.supplier_routes import (
        build_supplier_presenter,
    )
    conn = sqlite3.connect(":memory:")
    create_supplier_schema(conn)
    presenter = build_supplier_presenter(conn, _TodoPermitido())
    ok, msg, _ = presenter.create_supplier(
        legal_name="Distribuidora del Valle SA de CV", tax_identifier="DVA010203XY1",
        trade_name="Distribuidora del Valle")
    assert ok, msg
    yield presenter, conn
    conn.close()


class TestSuppliers:
    def _dialog(self):
        from frontend.desktop.modules.finance.suppliers.dialogs.supplier_dialogs import (
            SupplierAddressDialog,
        )
        return SupplierAddressDialog(runner=SyncRunner())

    def test_the_dialog_uses_the_standard_component(self, app):
        assert isinstance(self._dialog()._address, AddressInput)

    def test_a_geocoded_address_is_saved_with_its_coordinates(self, app, supplier_presenter):
        """Las columnas `latitude`/`longitude`/`geocoding_source`/
        `validation_state` existían desde el esquema original y NUNCA se
        llenaban."""
        presenter, conn = supplier_presenter
        sid = presenter.suppliers().row_ids[0]
        dialogo = self._dialog()
        dialogo._type.set_current_id("FISCAL")
        dialogo._address.set_value(_GEO)
        ok, msg, _ = presenter.add_address(supplier_id=sid, **dialogo.values())
        assert ok, msg
        fila = conn.execute(
            "SELECT line, city, postal_code, latitude, longitude, geocoding_source,"
            " validation_state FROM supplier_addresses WHERE supplier_id=?", (sid,)).fetchone()
        assert tuple(fila) == ("Avenida Juárez 120, Col. Centro", "Cuauhtémoc", "06050",
                               19.4351, -99.1478, "MAPBOX", "GEOCODED")

    def test_a_manual_address_is_saved_without_coordinates(self, app, supplier_presenter):
        presenter, conn = supplier_presenter
        sid = presenter.suppliers().row_ids[0]
        dialogo = self._dialog()
        dialogo._type.set_current_id("FISCAL")
        dialogo._address.field("street").setText("Calle Uno")
        dialogo._address.field("exterior_number").setText("5")
        ok, msg, _ = presenter.add_address(supplier_id=sid, **dialogo.values())
        assert ok, msg
        fila = conn.execute("SELECT latitude, validation_state FROM supplier_addresses"
                            " WHERE supplier_id=?", (sid,)).fetchone()
        assert tuple(fila) == (None, "MANUAL")

    def test_the_presenter_hands_out_the_search_service(self, supplier_presenter):
        presenter, _conn = supplier_presenter
        servicio = presenter.address_search_service()
        # Base sin integraciones: queda el respaldo, que no necesita nada.
        assert [p.code for p in servicio.providers] == ["NOMINATIM"]


# ── Clientes ─────────────────────────────────────────────────────────────────

@pytest.fixture
def crm():
    from backend.infrastructure.db.schema.customers_crm_schema import (
        create_customers_crm_schema,
    )
    from frontend.desktop.modules.customers_crm.composition import (
        build_customers_crm_presenter,
    )
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_customers_crm_schema(conn)
    presenter = build_customers_crm_presenter(conn, _TodoPermitido())
    creado = presenter.create_customer(display_name="Ana López", customer_type="INDIVIDUAL")
    assert creado.success, creado.message
    yield presenter, conn, creado.entity_id
    conn.close()


class TestCustomers:
    def test_the_use_case_finally_has_a_caller(self, app, crm):
        """`AddCustomerAddressUseCase` estaba completo y sin ningún llamador."""
        from frontend.desktop.modules.customers_crm.dialogs import CustomerAddressDialog

        presenter, conn, customer_id = crm
        dialogo = CustomerAddressDialog(runner=SyncRunner())
        dialogo.address.set_value(_GEO.with_changes(references="Portón verde"))
        resultado = presenter.add_customer_address(customer_id, **dialogo.values())
        assert resultado.success, resultado.message
        fila = conn.execute(
            "SELECT address_type, street, external_number, neighborhood, municipality,"
            " postal_code, address_references, latitude, longitude FROM customer_addresses"
            " WHERE customer_id=?", (customer_id,)).fetchone()
        assert tuple(fila) == ("DELIVERY", "Avenida Juárez", "120", "Centro", "Cuauhtémoc",
                               "06050", "Portón verde", 19.4351, -99.1478)

    def test_a_manual_address_is_saved_without_coordinates(self, app, crm):
        from frontend.desktop.modules.customers_crm.dialogs import CustomerAddressDialog

        presenter, conn, customer_id = crm
        dialogo = CustomerAddressDialog(runner=SyncRunner())
        dialogo.address.field("street").setText("Calle Uno")
        resultado = presenter.add_customer_address(customer_id, **dialogo.values())
        assert resultado.success, resultado.message
        lat = conn.execute("SELECT latitude FROM customer_addresses WHERE customer_id=?",
                           (customer_id,)).fetchone()[0]
        assert lat is None

    def test_the_dialog_refuses_an_address_without_street(self, app):
        from frontend.desktop.modules.customers_crm.dialogs import CustomerAddressDialog

        assert CustomerAddressDialog(runner=SyncRunner()).error() == "La calle es obligatoria."

    def test_the_profile_tab_has_the_add_button(self, app, crm):
        from frontend.desktop.modules.customers_crm.pages.customer_profile_page import (
            CustomerProfilePage,
        )
        presenter, _conn, _cid = crm
        pagina = CustomerProfilePage(presenter)
        pagina._build_table_tab("direcciones")
        assert pagina.add_address_button.isEnabled()

    def test_without_permission_the_button_is_disabled(self, app, crm):
        from frontend.desktop.modules.customers_crm.pages.customer_profile_page import (
            CustomerProfilePage,
        )
        presenter, _conn, _cid = crm

        class _SinPermiso(_TodoPermitido):
            def tiene_permiso(self, code):
                return code != "CLIENTES.direccion.crear"

        presenter._session = _SinPermiso()
        pagina = CustomerProfilePage(presenter)
        pagina._build_table_tab("direcciones")
        assert not pagina.add_address_button.isEnabled()


# ── Configuración ────────────────────────────────────────────────────────────

class TestConfiguracion:
    def test_the_three_dialogs_use_the_component_and_keep_one_line(self, app):
        from frontend.desktop.modules.configuracion.dialogs.company_branch_dialogs import (
            BranchProfileCreateDialog, BranchProfileEditDialog, CompanyProfileDialog,
        )
        for dialogo in (CompanyProfileDialog(), BranchProfileCreateDialog(),
                        BranchProfileEditDialog()):
            assert isinstance(dialogo.address, AddressInput)
            dialogo.address.set_value(_GEO)
            assert dialogo.address.value().one_line() == (
                "Avenida Juárez 120, Col. Centro, Cuauhtémoc, Ciudad de México, C.P. 06050")

    def test_editing_an_old_single_line_address_round_trips_unchanged(self, app):
        """Una dirección guardada antes del cambio (texto libre) no se reparte
        adivinando: se muestra y se guarda tal cual si nadie la toca."""
        from frontend.desktop.modules.configuracion.dialogs.company_branch_dialogs import (
            BranchProfileEditDialog,
        )
        dialogo = BranchProfileEditDialog()
        dialogo.address.set_value("Blvd. Díaz Ordaz 3500, Local 12, Monterrey")
        assert dialogo.address.value().one_line() == "Blvd. Díaz Ordaz 3500, Local 12, Monterrey"

