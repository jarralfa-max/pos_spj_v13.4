"""Inventory bounded context — domain layer.

Canonical home for warehouses, locations, the inventory movement ledger,
balances, lots, reservations, transfers, counts, adjustments, quarantine,
traceability and cold chain. Ledger-based, UUIDv7-only, Decimal-only.

INV-1 seeds the security foundation (permissions live in the application layer;
limits, segregation of duties and hot-authorization records live here).
"""
