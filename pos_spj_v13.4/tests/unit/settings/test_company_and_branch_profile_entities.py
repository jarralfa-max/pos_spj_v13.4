"""SET-5 — CompanyProfile / BranchProfile entities + AssetReference /
MapReference value objects (§15-16). Pure domain — no DB.
"""

from __future__ import annotations

from datetime import time
from decimal import Decimal

import pytest

from backend.domain.settings.entities.branch_profile import BranchProfile
from backend.domain.settings.entities.company_profile import CompanyProfile
from backend.domain.settings.exceptions import ConfigurationInvalidValueError
from backend.domain.settings.value_objects.asset_reference import AssetReference
from backend.domain.settings.value_objects.map_reference import MapReference
from backend.shared.ids import is_uuidv7, new_uuid


def _company(**overrides) -> CompanyProfile:
    kwargs = dict(
        legal_name="Super Junior de Chihuahua SA de CV", default_currency="MXN",
        default_timezone="America/Chihuahua", default_locale="es-MX",
    )
    kwargs.update(overrides)
    return CompanyProfile.create(**kwargs)


def _branch(**overrides) -> BranchProfile:
    kwargs = dict(branch_id=new_uuid(), code="SUC-01", name="Sucursal San Bartolo")
    kwargs.update(overrides)
    return BranchProfile.create(**kwargs)


class TestAssetReference:
    def test_requires_uuidv7(self):
        with pytest.raises(ValueError):
            AssetReference.create("not-a-uuid")

    def test_accepts_uuidv7(self):
        asset_id = new_uuid()
        assert AssetReference.create(asset_id).asset_id == asset_id


class TestMapReference:
    def test_defaults_to_unset(self):
        ref = MapReference()
        assert ref.is_set() is False

    def test_lat_and_lng_must_be_specified_together(self):
        with pytest.raises(ConfigurationInvalidValueError):
            MapReference.create(latitude=Decimal("28.6"))
        with pytest.raises(ConfigurationInvalidValueError):
            MapReference.create(longitude=Decimal("-106.1"))

    def test_rejects_float(self):
        with pytest.raises(ConfigurationInvalidValueError):
            MapReference.create(latitude=28.6, longitude=-106.1)

    def test_rejects_out_of_range(self):
        with pytest.raises(ConfigurationInvalidValueError):
            MapReference.create(latitude=Decimal("95"), longitude=Decimal("0"))
        with pytest.raises(ConfigurationInvalidValueError):
            MapReference.create(latitude=Decimal("0"), longitude=Decimal("185"))

    def test_accepts_valid_coordinates_and_place_id(self):
        ref = MapReference.create(latitude=Decimal("28.6"), longitude=Decimal("-106.1"), place_id="ChIJxyz")
        assert ref.is_set() is True

    def test_place_id_alone_counts_as_set(self):
        assert MapReference.create(place_id="ChIJxyz").is_set() is True


class TestCompanyProfileCreate:
    def test_mints_uuidv7(self):
        assert is_uuidv7(_company().id)

    def test_requires_legal_name(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _company(legal_name="   ")

    def test_normalizes_currency_case(self):
        assert _company(default_currency="mxn").default_currency == "MXN"

    def test_rejects_invalid_currency_code(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _company(default_currency="PESOS")

    def test_rejects_invalid_locale(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _company(default_locale="spanish")

    def test_requires_timezone(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _company(default_timezone="   ")

    def test_rejects_invalid_email(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _company(email="not-an-email")

    def test_accepts_valid_email(self):
        assert _company(email="ventas@sjc.mx").email == "ventas@sjc.mx"

    def test_rejects_website_without_scheme(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _company(website="sjc.mx")

    def test_accepts_https_website(self):
        assert _company(website="https://sjc.mx").website == "https://sjc.mx"


class TestCompanyProfileBehavior:
    def test_update_identity(self):
        company = _company()
        company.update_identity(
            legal_name="Nuevo Nombre SA de CV", default_currency="usd",
            default_timezone="America/Denver", default_locale="en-US", commercial_name="Nuevo Nombre",
            tax_id="ABC123", business_name="Nuevo Nombre Comercial", fiscal_regime_reference="601",
        )
        assert company.legal_name == "Nuevo Nombre SA de CV"
        assert company.default_currency == "USD"
        assert company.default_timezone == "America/Denver"
        assert company.default_locale == "en-US"
        assert company.commercial_name == "Nuevo Nombre"
        assert company.fiscal_regime_reference == "601"

    def test_update_identity_rejects_blank_legal_name(self):
        company = _company()
        with pytest.raises(ConfigurationInvalidValueError):
            company.update_identity(
                legal_name="   ", default_currency="MXN", default_timezone="America/Chihuahua",
                default_locale="es-MX",
            )

    def test_update_identity_rejects_invalid_currency(self):
        company = _company()
        with pytest.raises(ConfigurationInvalidValueError):
            company.update_identity(
                legal_name="X", default_currency="PESOS", default_timezone="America/Chihuahua",
                default_locale="es-MX",
            )

    def test_update_identity_rejects_invalid_locale(self):
        company = _company()
        with pytest.raises(ConfigurationInvalidValueError):
            company.update_identity(
                legal_name="X", default_currency="MXN", default_timezone="America/Chihuahua",
                default_locale="spanish",
            )

    def test_update_contact_info(self):
        company = _company()
        company.update_contact_info(address="Av. Siempre Viva 123", phone="+5216141234567")
        assert company.address == "Av. Siempre Viva 123"
        assert company.phone == "+5216141234567"

    def test_update_contact_info_rejects_invalid_email(self):
        company = _company()
        with pytest.raises(ConfigurationInvalidValueError):
            company.update_contact_info(email="bad")

    def test_replace_logo(self):
        company = _company()
        asset = AssetReference.create(new_uuid())
        company.replace_logo(asset)
        assert company.logo_asset is asset
        company.replace_logo(None)
        assert company.logo_asset is None

    def test_set_social_network(self):
        company = _company()
        company.set_social_network("Facebook", "https://facebook.com/sjc")
        assert company.social_networks["facebook"] == "https://facebook.com/sjc"

    def test_activate_deactivate(self):
        company = _company()
        company.deactivate()
        assert company.active is False
        company.activate()
        assert company.active is True


class TestBranchProfileCreate:
    def test_id_equals_branch_id(self):
        branch_id = new_uuid()
        branch = _branch(branch_id=branch_id)
        assert branch.id == branch_id == branch.branch_id

    def test_requires_valid_branch_id(self):
        with pytest.raises(ValueError):
            _branch(branch_id="not-a-uuid")

    def test_requires_code_and_name(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _branch(code="   ")
        with pytest.raises(ConfigurationInvalidValueError):
            _branch(name="")

    def test_opening_and_closing_time_required_together(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _branch(opening_time=time(8, 0))

    def test_closing_time_must_be_after_opening_time(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _branch(opening_time=time(20, 0), closing_time=time(8, 0))

    def test_normalizes_operation_days(self):
        branch = _branch(operation_days=("mon", "TUE", "Wed", "mon"))
        assert branch.operation_days == ("MON", "TUE", "WED")

    def test_rejects_invalid_operation_day(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _branch(operation_days=("mon", "funday"))

    def test_validates_warehouse_ids_as_uuidv7(self):
        with pytest.raises(ValueError):
            _branch(warehouse_ids=("not-a-uuid",))
        warehouse_id = new_uuid()
        assert _branch(warehouse_ids=(warehouse_id,)).warehouse_ids == (warehouse_id,)

    def test_validates_default_workstation_profile_id(self):
        with pytest.raises(ValueError):
            _branch(default_workstation_profile_id="not-a-uuid")


class TestBranchProfileBehavior:
    def test_update_profile(self):
        branch = _branch()
        branch.update_profile(name="Nueva Sucursal", timezone="America/Mexico_City")
        assert branch.name == "Nueva Sucursal"
        assert branch.timezone == "America/Mexico_City"

    def test_update_profile_rejects_blank_name(self):
        branch = _branch()
        with pytest.raises(ConfigurationInvalidValueError):
            branch.update_profile(name="   ")

    def test_set_operating_hours(self):
        branch = _branch()
        branch.set_operating_hours(time(9, 0), time(18, 0), ("mon", "tue"))
        assert branch.opening_time == time(9, 0)
        assert branch.operation_days == ("MON", "TUE")

    def test_set_operating_hours_validates_order(self):
        branch = _branch()
        with pytest.raises(ConfigurationInvalidValueError):
            branch.set_operating_hours(time(18, 0), time(9, 0))

    def test_set_ticket_texts(self):
        branch = _branch()
        branch.set_ticket_texts(header="Bienvenido", footer="Gracias por su compra")
        assert branch.ticket_header == "Bienvenido"
        assert branch.ticket_footer == "Gracias por su compra"

    def test_set_social_link(self):
        branch = _branch()
        branch.set_social_link("Instagram", "https://instagram.com/sjc")
        assert branch.social_links["instagram"] == "https://instagram.com/sjc"

    def test_set_map_reference(self):
        branch = _branch()
        ref = MapReference.create(latitude=Decimal("28.6"), longitude=Decimal("-106.1"))
        branch.set_map_reference(ref)
        assert branch.map_reference is ref

    def test_assign_warehouses_deduplicates(self):
        branch = _branch()
        warehouse_id = new_uuid()
        branch.assign_warehouses((warehouse_id, warehouse_id))
        assert branch.warehouse_ids == (warehouse_id,)

    def test_set_default_workstation_profile(self):
        branch = _branch()
        workstation_profile_id = new_uuid()
        branch.set_default_workstation_profile(workstation_profile_id)
        assert branch.default_workstation_profile_id == workstation_profile_id
        branch.set_default_workstation_profile(None)
        assert branch.default_workstation_profile_id is None

    def test_activate_deactivate(self):
        branch = _branch()
        branch.deactivate()
        assert branch.active is False
        branch.activate()
        assert branch.active is True
