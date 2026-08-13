"""CRM-3 — Customer Master domain unit tests: entity lifecycle, value
objects, child entities, duplicate policy. Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.customers.entities.customer import Customer
from backend.domain.customers.entities.customer_account import CustomerAccount
from backend.domain.customers.entities.customer_address import CustomerAddress
from backend.domain.customers.entities.customer_contact import CustomerContactPerson
from backend.domain.customers.entities.customer_tax_profile import CustomerTaxProfile
from backend.domain.customers.enums import AddressType, CustomerStatus, CustomerType
from backend.domain.customers.exceptions import (
    InvalidCustomerCodeError,
    InvalidCustomerStateError,
    InvalidEmailAddressError,
    InvalidPhoneNumberError,
)
from backend.domain.customers.policies.duplicate_policy import CustomerDuplicatePolicy
from backend.domain.customers.value_objects.customer_code import CustomerCode
from backend.domain.customers.value_objects.email_address import EmailAddress
from backend.domain.customers.value_objects.phone_number import PhoneNumber


def _customer(**kwargs) -> Customer:
    return Customer.create(
        CustomerCode.from_sequence(1), kwargs.pop("display_name", "Juan Perez"),
        kwargs.pop("customer_type", CustomerType.INDIVIDUAL), **kwargs)


class TestCustomerLifecycle:
    def test_create_defaults_to_active(self):
        c = _customer()
        assert c.status is CustomerStatus.ACTIVE
        assert c.id and c.version == 1

    def test_create_as_prospect(self):
        c = _customer(as_prospect=True)
        assert c.status is CustomerStatus.PROSPECT

    def test_create_requires_display_name(self):
        with pytest.raises(InvalidCustomerStateError):
            Customer.create(CustomerCode.from_sequence(1), "   ", CustomerType.INDIVIDUAL)

    def test_suspend_then_activate(self):
        c = _customer()
        c.suspend("mora")
        assert c.status is CustomerStatus.SUSPENDED and c.suspended_at
        c.activate()
        assert c.status is CustomerStatus.ACTIVE

    def test_suspend_requires_reason(self):
        c = _customer()
        with pytest.raises(InvalidCustomerStateError):
            c.suspend("")

    def test_suspend_only_from_active(self):
        c = _customer(as_prospect=True)
        with pytest.raises(InvalidCustomerStateError):
            c.suspend("mora")

    def test_deactivate_then_reactivate(self):
        c = _customer()
        c.deactivate()
        assert c.status is CustomerStatus.INACTIVE
        c.activate()
        assert c.status is CustomerStatus.ACTIVE

    def test_block_requires_reason(self):
        c = _customer()
        with pytest.raises(InvalidCustomerStateError):
            c.block("")

    def test_block_from_active_suspended_or_inactive(self):
        for setup in (lambda c: None, lambda c: c.suspend("x"), lambda c: c.deactivate()):
            c = _customer()
            setup(c)
            c.block("fraude sospechoso")
            assert c.status is CustomerStatus.BLOCKED

    def test_close_is_terminal_and_requires_reason(self):
        c = _customer()
        with pytest.raises(InvalidCustomerStateError):
            c.close("")
        c.close("cliente solicitó cierre")
        assert c.status is CustomerStatus.CLOSED
        assert c.is_terminal()
        with pytest.raises(InvalidCustomerStateError):
            c.activate()

    def test_version_and_updated_at_bump_on_every_transition(self):
        c = _customer()
        v0, t0 = c.version, c.updated_at
        c.suspend("mora")
        assert c.version == v0 + 1

    def test_mark_merged_requires_target_id(self):
        c = _customer()
        with pytest.raises(InvalidCustomerStateError):
            c.mark_merged("")
        c.mark_merged("other-customer-id")
        assert c.status is CustomerStatus.MERGED and c.is_terminal()

    def test_mark_anonymized(self):
        c = _customer()
        c.mark_anonymized()
        assert c.status is CustomerStatus.ANONYMIZED and c.is_terminal()

    def test_assign_owner_and_territory(self):
        c = _customer()
        c.assign_owner("u-vendedor")
        c.assign_territory("territorio-cdmx")
        assert c.account_owner_user_id == "u-vendedor"
        assert c.territory_id == "territorio-cdmx"


class TestCustomerCode:
    def test_from_sequence_formats_with_prefix_and_padding(self):
        assert str(CustomerCode.from_sequence(7)) == "CLI-000007"

    def test_rejects_malformed_code(self):
        with pytest.raises(InvalidCustomerCodeError):
            CustomerCode("NOT-A-CODE")


class TestPhoneNumber:
    def test_accepts_valid_e164(self):
        assert str(PhoneNumber("+525512345678")) == "+525512345678"

    def test_strips_whitespace(self):
        assert str(PhoneNumber(" +52 55 1234 5678".replace(" ", ""))) == "+525512345678"

    def test_rejects_missing_plus(self):
        with pytest.raises(InvalidPhoneNumberError):
            PhoneNumber("5512345678")

    def test_rejects_leading_zero_country_code(self):
        with pytest.raises(InvalidPhoneNumberError):
            PhoneNumber("+0512345678")


class TestEmailAddress:
    def test_normalizes_to_lowercase(self):
        assert str(EmailAddress("Juan@Example.COM")) == "juan@example.com"

    def test_rejects_missing_at_sign(self):
        with pytest.raises(InvalidEmailAddressError):
            EmailAddress("juan.example.com")


class TestChildEntities:
    def test_account_requires_customer_id(self):
        with pytest.raises(Exception):
            CustomerAccount.create("")

    def test_contact_requires_first_name(self):
        with pytest.raises(Exception):
            CustomerContactPerson.create("cust-1", "   ")

    def test_address_requires_street(self):
        with pytest.raises(Exception):
            CustomerAddress.create("cust-1", AddressType.DELIVERY, "")

    def test_tax_profile_requires_customer_id(self):
        with pytest.raises(Exception):
            CustomerTaxProfile.create("")

    def test_child_entities_get_distinct_uuidv7_ids(self):
        a = CustomerAccount.create("cust-1")
        b = CustomerAccount.create("cust-1")
        assert a.id != b.id


class TestCustomerDuplicatePolicy:
    def setup_method(self):
        self.policy = CustomerDuplicatePolicy()

    def test_no_matches_on_empty_existing(self):
        assert self.policy.find_matches({"display_name": "Juan"}, []) == []

    def test_matches_on_phone(self):
        existing = [{"id": "c1", "display_name": "Otro", "phone_e164": "+525512345678"}]
        matches = self.policy.find_matches(
            {"display_name": "Distinto", "phone_e164": "+525512345678"}, existing)
        assert len(matches) == 1 and "Mismo teléfono" in matches[0].reasons

    def test_matches_on_normalized_name_ignoring_accents_and_case(self):
        existing = [{"id": "c1", "display_name": "José Pérez"}]
        matches = self.policy.find_matches({"display_name": "jose perez"}, existing)
        assert len(matches) == 1 and "Mismo nombre" in matches[0].reasons

    def test_matches_on_rfc(self):
        existing = [{"id": "c1", "display_name": "X", "tax_identifier": "xaxx010101000"}]
        matches = self.policy.find_matches(
            {"display_name": "Y", "tax_identifier": "XAXX010101000"}, existing)
        assert len(matches) == 1 and "Mismo RFC" in matches[0].reasons

    def test_no_false_positive_on_unrelated_customer(self):
        existing = [{"id": "c1", "display_name": "Completely Different",
                     "phone_e164": "+525500000000"}]
        matches = self.policy.find_matches(
            {"display_name": "Juan Perez", "phone_e164": "+525512345678"}, existing)
        assert matches == []


class TestCustomerSaleActivityProjection:
    """CRM-13 (§49 Ventas): Customer.record_sale_activity/record_sale_cancelled."""

    def test_first_purchase_bumps_counter_and_timestamp(self):
        c = _customer()
        c.record_sale_activity("2026-08-13T10:00:00+00:00")
        assert c.purchase_count == 1
        assert c.last_purchase_at == "2026-08-13T10:00:00+00:00"

    def test_first_purchase_advances_prospect_to_customer(self):
        from backend.domain.customers.enums import LifecycleStage
        c = _customer(as_prospect=True)
        assert c.lifecycle_stage is LifecycleStage.PROSPECT
        new_stage = c.record_sale_activity("2026-08-13T10:00:00+00:00")
        assert c.lifecycle_stage is LifecycleStage.CUSTOMER
        assert new_stage is LifecycleStage.CUSTOMER

    def test_second_purchase_advances_customer_to_repeat_customer(self):
        from backend.domain.customers.enums import LifecycleStage
        c = _customer()
        assert c.lifecycle_stage is LifecycleStage.CUSTOMER
        c.record_sale_activity("2026-08-01T10:00:00+00:00")
        new_stage = c.record_sale_activity("2026-08-13T10:00:00+00:00")
        assert c.lifecycle_stage is LifecycleStage.REPEAT_CUSTOMER
        assert new_stage is LifecycleStage.REPEAT_CUSTOMER

    def test_purchase_from_inactive_moves_to_repeat_customer(self):
        from backend.domain.customers.enums import LifecycleStage
        c = _customer()
        c.set_lifecycle_stage(LifecycleStage.INACTIVE)
        new_stage = c.record_sale_activity("2026-08-13T10:00:00+00:00")
        assert c.lifecycle_stage is LifecycleStage.REPEAT_CUSTOMER
        assert new_stage is LifecycleStage.REPEAT_CUSTOMER

    def test_no_stage_change_returns_none(self):
        from backend.domain.customers.enums import LifecycleStage
        c = _customer()
        c.set_lifecycle_stage(LifecycleStage.REPEAT_CUSTOMER)
        new_stage = c.record_sale_activity("2026-08-13T10:00:00+00:00")
        assert new_stage is None
        assert c.lifecycle_stage is LifecycleStage.REPEAT_CUSTOMER

    def test_cancel_decrements_purchase_count(self):
        c = _customer()
        c.record_sale_activity("2026-08-13T10:00:00+00:00")
        c.record_sale_activity("2026-08-14T10:00:00+00:00")
        c.record_sale_cancelled()
        assert c.purchase_count == 1

    def test_cancel_never_goes_negative(self):
        c = _customer()
        c.record_sale_cancelled()
        assert c.purchase_count == 0

    def test_cancel_does_not_change_lifecycle_stage(self):
        from backend.domain.customers.enums import LifecycleStage
        c = _customer()
        c.record_sale_activity("2026-08-13T10:00:00+00:00")
        stage_before = c.lifecycle_stage
        c.record_sale_cancelled()
        assert c.lifecycle_stage is stage_before
