"""SalesFiscalClient — Sales' integration point onto Customer Master's real
fiscal master data (POS-18/§15/§46: "Fiscal administra CFDI; Clientes
administra datos maestros; Ventas conserva snapshots históricos").

Research for this phase confirmed `backend/domain/customers/entities/
customer_tax_profile.py::CustomerTaxProfile` (RFC/legal name/tax
regime/default CFDI use, backed by a real, tested `customer_tax_profiles`
table from an earlier CRM phase) already exists and is exactly the master
data §15 names — but nothing in Sales ever reads it; the legacy invoice
dialog (`modulos/ventas.py::_generar_factura`) only accepts freehand RFC
entry every time, never looking a customer's saved profile up. This client
is the missing read side — mirrors `sales_pricing_client.py`'s shape
(thin, delegates entirely to the real owning bounded context).

No real PAC (Facturama/SW Sapien/Finkok/etc.) integration exists anywhere
in this repository (confirmed by research) — this client does not
fabricate one; it only resolves the fiscal data a request needs before
Sales records it as a `SaleInvoiceRequest` snapshot.
"""

from __future__ import annotations


class SalesFiscalClient:
    def __init__(self, connection) -> None:
        self._connection = connection

    def resolve_tax_profile(self, customer_id: str) -> dict | None:
        """Returns `{"tax_identifier", "legal_name", "cfdi_use"}` from the
        customer's real `CustomerTaxProfile`, or `None` if the customer has
        none saved (or `customer_id` is `None` — a walk-in sale with no
        assigned customer)."""
        if not customer_id:
            return None
        from backend.infrastructure.db.repositories.customers.customer_child_repositories import (
            CustomerTaxProfileRepository,
        )

        profile = CustomerTaxProfileRepository(self._connection).get_for_customer(customer_id)
        if profile is None or not profile.tax_identifier:
            return None
        return {
            "tax_identifier": profile.tax_identifier,
            "legal_name": profile.legal_name or "PUBLICO EN GENERAL",
            "cfdi_use": profile.default_cfdi_use or "S01",
        }
