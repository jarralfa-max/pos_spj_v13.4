"""Child-entity repositories for the Customer Master aggregate: accounts,
contacts, addresses, tax profiles. Mirrors
backend/infrastructure/db/repositories/suppliers/supplier_child_repositories.py.
"""

from __future__ import annotations

from backend.domain.customers.entities.customer_account import CustomerAccount
from backend.domain.customers.entities.customer_address import CustomerAddress
from backend.domain.customers.entities.customer_contact import CustomerContactPerson
from backend.domain.customers.entities.customer_tax_profile import CustomerTaxProfile
from backend.domain.customers.enums import AddressType, ContactDecisionRole, ValidationStatus
from backend.infrastructure.db.repositories.customers.base import CustomerRepositoryBase

_ACCOUNT_COLS = (
    "id, customer_id, account_type, industry, company_size, website,"
    " parent_account_id, account_owner_user_id, territory_id, status"
)
_CONTACT_COLS = (
    "id, customer_id, customer_account_id, first_name, last_name, job_title,"
    " department, phone_e164, email, decision_role, is_primary, status"
)
_ADDRESS_COLS = (
    "id, customer_id, address_type, street, external_number, internal_number,"
    " neighborhood, postal_code, locality, municipality, state, country,"
    " address_references, latitude, longitude, validation_status, is_default"
)
_TAX_COLS = (
    "id, customer_id, tax_identifier, legal_name, tax_regime, fiscal_postal_code,"
    " default_cfdi_use, billing_email, validation_status, validated_at"
)


class CustomerAccountRepository(CustomerRepositoryBase):
    def save(self, account: CustomerAccount) -> None:
        self._execute(
            f"INSERT INTO customer_accounts ({_ACCOUNT_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (account.id, account.customer_id, account.account_type, account.industry,
             account.company_size, account.website, account.parent_account_id,
             account.account_owner_user_id, account.territory_id, account.status))

    def get(self, account_id: str) -> CustomerAccount | None:
        row = self._query_one(
            f"SELECT {_ACCOUNT_COLS} FROM customer_accounts WHERE id=?", (account_id,))
        return self._hydrate(row) if row else None

    def list_for_customer(self, customer_id: str) -> list[CustomerAccount]:
        rows = self._query(
            f"SELECT {_ACCOUNT_COLS} FROM customer_accounts WHERE customer_id=?",
            (customer_id,))
        return [self._hydrate(r) for r in rows]

    def reassign_customer_id(self, old_customer_id: str, new_customer_id: str) -> None:
        """CRM-11 merge support: move every account from a merged customer to
        the surviving master. No uniqueness constraint blocks this (a
        customer can have several accounts)."""
        self._execute(
            "UPDATE customer_accounts SET customer_id=? WHERE customer_id=?",
            (new_customer_id, old_customer_id))

    @staticmethod
    def _hydrate(row: dict) -> CustomerAccount:
        return CustomerAccount(
            id=row["id"], customer_id=row["customer_id"], account_type=row["account_type"],
            industry=row["industry"] or "", company_size=row["company_size"] or "",
            website=row["website"] or "", parent_account_id=row["parent_account_id"],
            account_owner_user_id=row["account_owner_user_id"],
            territory_id=row["territory_id"], status=row["status"])


class CustomerContactRepository(CustomerRepositoryBase):
    def save(self, contact: CustomerContactPerson) -> None:
        self._execute(
            f"INSERT INTO customer_contacts ({_CONTACT_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(contact))

    def update(self, contact: CustomerContactPerson) -> None:
        self._execute(
            "UPDATE customer_contacts SET customer_account_id=?, first_name=?, last_name=?,"
            " job_title=?, department=?, phone_e164=?, email=?, decision_role=?,"
            " is_primary=?, status=? WHERE id=?",
            (contact.customer_account_id, contact.first_name, contact.last_name,
             contact.job_title, contact.department, contact.phone_e164, contact.email,
             contact.decision_role.value, int(contact.is_primary), contact.status,
             contact.id))

    def remove(self, contact_id: str) -> None:
        self._execute("DELETE FROM customer_contacts WHERE id=?", (contact_id,))

    def get(self, contact_id: str) -> CustomerContactPerson | None:
        row = self._query_one(
            f"SELECT {_CONTACT_COLS} FROM customer_contacts WHERE id=?", (contact_id,))
        return self._hydrate(row) if row else None

    def list_for_customer(self, customer_id: str) -> list[CustomerContactPerson]:
        rows = self._query(
            f"SELECT {_CONTACT_COLS} FROM customer_contacts WHERE customer_id=?",
            (customer_id,))
        return [self._hydrate(r) for r in rows]

    def clear_primary(self, customer_id: str) -> None:
        self._execute(
            "UPDATE customer_contacts SET is_primary=0 WHERE customer_id=?", (customer_id,))

    def reassign_customer_id(self, old_customer_id: str, new_customer_id: str) -> None:
        """CRM-11 merge support: move every contact from a merged customer to
        the surviving master. Reassigned contacts keep ``is_primary`` as-is;
        the caller is responsible for calling ``clear_primary``/re-marking a
        primary contact afterward if that matters for the merge."""
        self._execute(
            "UPDATE customer_contacts SET customer_id=? WHERE customer_id=?",
            (new_customer_id, old_customer_id))

    @staticmethod
    def _params(contact: CustomerContactPerson) -> tuple:
        return (
            contact.id, contact.customer_id, contact.customer_account_id,
            contact.first_name, contact.last_name, contact.job_title, contact.department,
            contact.phone_e164, contact.email, contact.decision_role.value,
            int(contact.is_primary), contact.status,
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerContactPerson:
        return CustomerContactPerson(
            id=row["id"], customer_id=row["customer_id"],
            customer_account_id=row["customer_account_id"], first_name=row["first_name"],
            last_name=row["last_name"] or "", job_title=row["job_title"] or "",
            department=row["department"] or "", phone_e164=row["phone_e164"],
            email=row["email"], decision_role=ContactDecisionRole(row["decision_role"]),
            is_primary=bool(row["is_primary"]), status=row["status"])


class CustomerAddressRepository(CustomerRepositoryBase):
    def save(self, address: CustomerAddress) -> None:
        self._execute(
            f"INSERT INTO customer_addresses ({_ADDRESS_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(address))

    def update(self, address: CustomerAddress) -> None:
        self._execute(
            "UPDATE customer_addresses SET address_type=?, street=?, external_number=?,"
            " internal_number=?, neighborhood=?, postal_code=?, locality=?, municipality=?,"
            " state=?, country=?, address_references=?, latitude=?, longitude=?,"
            " validation_status=?, is_default=? WHERE id=?",
            (address.address_type.value, address.street, address.external_number,
             address.internal_number, address.neighborhood, address.postal_code,
             address.locality, address.municipality, address.state, address.country,
             address.references, address.latitude, address.longitude,
             address.validation_status.value, int(address.is_default), address.id))

    def remove(self, address_id: str) -> None:
        self._execute("DELETE FROM customer_addresses WHERE id=?", (address_id,))

    def get(self, address_id: str) -> CustomerAddress | None:
        row = self._query_one(
            f"SELECT {_ADDRESS_COLS} FROM customer_addresses WHERE id=?", (address_id,))
        return self._hydrate(row) if row else None

    def list_for_customer(self, customer_id: str) -> list[CustomerAddress]:
        rows = self._query(
            f"SELECT {_ADDRESS_COLS} FROM customer_addresses WHERE customer_id=?",
            (customer_id,))
        return [self._hydrate(r) for r in rows]

    def clear_default(self, customer_id: str, address_type: str) -> None:
        self._execute(
            "UPDATE customer_addresses SET is_default=0"
            " WHERE customer_id=? AND address_type=?", (customer_id, address_type))

    def reassign_customer_id(self, old_customer_id: str, new_customer_id: str) -> None:
        """CRM-11 merge support: move every address from a merged customer to
        the surviving master."""
        self._execute(
            "UPDATE customer_addresses SET customer_id=? WHERE customer_id=?",
            (new_customer_id, old_customer_id))

    @staticmethod
    def _params(address: CustomerAddress) -> tuple:
        return (
            address.id, address.customer_id, address.address_type.value, address.street,
            address.external_number, address.internal_number, address.neighborhood,
            address.postal_code, address.locality, address.municipality, address.state,
            address.country, address.references, address.latitude, address.longitude,
            address.validation_status.value, int(address.is_default),
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerAddress:
        return CustomerAddress(
            id=row["id"], customer_id=row["customer_id"],
            address_type=AddressType(row["address_type"]), street=row["street"],
            external_number=row["external_number"] or "",
            internal_number=row["internal_number"] or "",
            neighborhood=row["neighborhood"] or "", postal_code=row["postal_code"] or "",
            locality=row["locality"] or "", municipality=row["municipality"] or "",
            state=row["state"] or "", country=row["country"] or "MX",
            references=row["address_references"] or "", latitude=row["latitude"],
            longitude=row["longitude"],
            validation_status=ValidationStatus(row["validation_status"]),
            is_default=bool(row["is_default"]))


class CustomerTaxProfileRepository(CustomerRepositoryBase):
    def save(self, profile: CustomerTaxProfile) -> None:
        self._execute(
            f"INSERT INTO customer_tax_profiles ({_TAX_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?)",
            self._params(profile))

    def update(self, profile: CustomerTaxProfile) -> None:
        self._execute(
            "UPDATE customer_tax_profiles SET tax_identifier=?, legal_name=?, tax_regime=?,"
            " fiscal_postal_code=?, default_cfdi_use=?, billing_email=?, validation_status=?,"
            " validated_at=? WHERE id=?",
            (profile.tax_identifier, profile.legal_name, profile.tax_regime,
             profile.fiscal_postal_code, profile.default_cfdi_use, profile.billing_email,
             profile.validation_status.value, profile.validated_at, profile.id))

    def get_for_customer(self, customer_id: str) -> CustomerTaxProfile | None:
        row = self._query_one(
            f"SELECT {_TAX_COLS} FROM customer_tax_profiles WHERE customer_id=?",
            (customer_id,))
        return self._hydrate(row) if row else None

    def reassign_customer_id(self, old_customer_id: str, new_customer_id: str) -> None:
        """CRM-11 merge support: move a merged customer's tax profile to the
        surviving master. Caller must first confirm the master has none —
        ``customer_tax_profiles`` is UNIQUE(customer_id), so reassigning
        onto a master that already has a profile would violate it."""
        self._execute(
            "UPDATE customer_tax_profiles SET customer_id=? WHERE customer_id=?",
            (new_customer_id, old_customer_id))

    def delete_for_customer(self, customer_id: str) -> None:
        """CRM-11 merge support: drop a merged customer's redundant tax
        profile when the master already has its own (see
        ExecuteCustomerMergeUseCase — the master's profile always wins)."""
        self._execute("DELETE FROM customer_tax_profiles WHERE customer_id=?", (customer_id,))

    @staticmethod
    def _params(profile: CustomerTaxProfile) -> tuple:
        return (
            profile.id, profile.customer_id, profile.tax_identifier, profile.legal_name,
            profile.tax_regime, profile.fiscal_postal_code, profile.default_cfdi_use,
            profile.billing_email, profile.validation_status.value, profile.validated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerTaxProfile:
        return CustomerTaxProfile(
            id=row["id"], customer_id=row["customer_id"],
            tax_identifier=row["tax_identifier"] or "", legal_name=row["legal_name"] or "",
            tax_regime=row["tax_regime"] or "",
            fiscal_postal_code=row["fiscal_postal_code"] or "",
            default_cfdi_use=row["default_cfdi_use"] or "",
            billing_email=row["billing_email"],
            validation_status=ValidationStatus(row["validation_status"]),
            validated_at=row["validated_at"])
