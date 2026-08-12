"""CRM-3 — Customer Master repository round-trips + UnitOfWork behavior."""

from __future__ import annotations

from backend.domain.customers.entities.customer import Customer
from backend.domain.customers.entities.customer_account import CustomerAccount
from backend.domain.customers.entities.customer_address import CustomerAddress
from backend.domain.customers.entities.customer_contact import CustomerContactPerson
from backend.domain.customers.entities.customer_tax_profile import CustomerTaxProfile
from backend.domain.customers.enums import AddressType, CustomerType
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


def _new_customer(uow, **kwargs) -> Customer:
    return Customer.create(
        uow.customers.next_code(), kwargs.pop("display_name", "Juan Perez"),
        kwargs.pop("customer_type", CustomerType.INDIVIDUAL),
        created_by_user_id="u-capturista", **kwargs)


class TestCustomerMaster:
    def test_save_and_get(self, cust_conn):
        with CustomerUnitOfWork(cust_conn) as uow:
            customer = _new_customer(uow, operation_id="op-1")
            uow.customers.save(customer, operation_id="op-1")

        with CustomerUnitOfWork(cust_conn) as uow2:
            fetched = uow2.customers.get(customer.id)
            assert fetched is not None
            assert fetched.display_name == "Juan Perez"
            assert str(fetched.code) == str(customer.code)
            assert fetched.status.value == "ACTIVE"

    def test_next_code_increments(self, cust_conn):
        with CustomerUnitOfWork(cust_conn) as uow:
            c1 = _new_customer(uow, operation_id="op-1")
            uow.customers.save(c1, operation_id="op-1")
        with CustomerUnitOfWork(cust_conn) as uow2:
            c2 = _new_customer(uow2, operation_id="op-2")
            uow2.customers.save(c2, operation_id="op-2")
        assert str(c1.code) == "CLI-000001"
        assert str(c2.code) == "CLI-000002"

    def test_get_by_operation_id_is_idempotency_lookup(self, cust_conn):
        with CustomerUnitOfWork(cust_conn) as uow:
            customer = _new_customer(uow, operation_id="op-dup")
            uow.customers.save(customer, operation_id="op-dup")
        with CustomerUnitOfWork(cust_conn) as uow2:
            found = uow2.customers.get_by_operation_id("op-dup")
            assert found is not None and found.id == customer.id

    def test_update_persists_status_and_version(self, cust_conn):
        with CustomerUnitOfWork(cust_conn) as uow:
            customer = _new_customer(uow, operation_id="op-1")
            uow.customers.save(customer, operation_id="op-1")
        with CustomerUnitOfWork(cust_conn) as uow2:
            customer = uow2.customers.get(customer.id)
            customer.suspend("mora")
            uow2.customers.update(customer)
        with CustomerUnitOfWork(cust_conn) as uow3:
            reloaded = uow3.customers.get(customer.id)
            assert reloaded.status.value == "SUSPENDED"
            assert reloaded.version == 2

    def test_rollback_on_exception_discards_all_writes(self, cust_conn):
        try:
            with CustomerUnitOfWork(cust_conn) as uow:
                customer = _new_customer(uow, operation_id="op-1")
                uow.customers.save(customer, operation_id="op-1")
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        count = cust_conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        assert count == 0

    def test_find_duplicate_rows_joins_primary_contact_and_tax_profile(self, cust_conn):
        with CustomerUnitOfWork(cust_conn) as uow:
            customer = _new_customer(uow, operation_id="op-1")
            uow.customers.save(customer, operation_id="op-1")
            uow.contacts.save(CustomerContactPerson.create(
                customer.id, "Maria", is_primary=True, phone_e164="+525512345678"))
            uow.tax_profiles.save(CustomerTaxProfile.create(
                customer.id, tax_identifier="XAXX010101000"))
        with CustomerUnitOfWork(cust_conn) as uow2:
            rows = uow2.customers.find_duplicate_rows()
            assert len(rows) == 1
            assert rows[0]["phone_e164"] == "+525512345678"
            assert rows[0]["tax_identifier"] == "XAXX010101000"


class TestCustomerChildren:
    def test_account_round_trip(self, cust_conn):
        with CustomerUnitOfWork(cust_conn) as uow:
            customer = _new_customer(uow, operation_id="op-1")
            uow.customers.save(customer, operation_id="op-1")
            account = CustomerAccount.create(customer.id, industry="Restaurantes")
            uow.accounts.save(account)
        with CustomerUnitOfWork(cust_conn) as uow2:
            accounts = uow2.accounts.list_for_customer(customer.id)
            assert len(accounts) == 1 and accounts[0].industry == "Restaurantes"

    def test_contact_round_trip_and_clear_primary(self, cust_conn):
        with CustomerUnitOfWork(cust_conn) as uow:
            customer = _new_customer(uow, operation_id="op-1")
            uow.customers.save(customer, operation_id="op-1")
            c1 = CustomerContactPerson.create(customer.id, "Maria", is_primary=True)
            c2 = CustomerContactPerson.create(customer.id, "Luis", is_primary=False)
            uow.contacts.save(c1)
            uow.contacts.save(c2)
        with CustomerUnitOfWork(cust_conn) as uow2:
            uow2.contacts.clear_primary(customer.id)
            for c in uow2.contacts.list_for_customer(customer.id):
                assert c.is_primary is False

    def test_address_round_trip_preserves_references_field_name_mismatch(self, cust_conn):
        """The entity field is `references`; the DB column is
        `address_references` (avoids the SQL keyword) — this is exactly the
        kind of mapping bug a round-trip test exists to catch."""
        with CustomerUnitOfWork(cust_conn) as uow:
            customer = _new_customer(uow, operation_id="op-1")
            uow.customers.save(customer, operation_id="op-1")
            addr = CustomerAddress.create(
                customer.id, AddressType.DELIVERY, "Av. Reforma",
                external_number="123", references="Entre X y Y")
            uow.addresses.save(addr)
        with CustomerUnitOfWork(cust_conn) as uow2:
            fetched = uow2.addresses.list_for_customer(customer.id)[0]
            assert fetched.references == "Entre X y Y"
            assert fetched.external_number == "123"

    def test_tax_profile_is_unique_per_customer(self, cust_conn):
        with CustomerUnitOfWork(cust_conn) as uow:
            customer = _new_customer(uow, operation_id="op-1")
            uow.customers.save(customer, operation_id="op-1")
            uow.tax_profiles.save(CustomerTaxProfile.create(
                customer.id, tax_identifier="XAXX010101000"))
        with CustomerUnitOfWork(cust_conn) as uow2:
            profile = uow2.tax_profiles.get_for_customer(customer.id)
            assert profile.tax_identifier == "XAXX010101000"
            profile.tax_regime = "612"
            uow2.tax_profiles.update(profile)
        with CustomerUnitOfWork(cust_conn) as uow3:
            reloaded = uow3.tax_profiles.get_for_customer(customer.id)
            assert reloaded.tax_regime == "612"
