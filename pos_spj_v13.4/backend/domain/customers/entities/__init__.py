"""Entities for the Customer Master bounded context (CRM-3, §12-15).

``Customer`` is the aggregate root: it owns status transitions and protects
lifecycle invariants (mirrors backend/domain/suppliers/entities.py::Supplier).
Child entities (account, contact, address, tax profile) are separate
structures with their own UUIDv7 identity, never merged into the customer row.
"""
