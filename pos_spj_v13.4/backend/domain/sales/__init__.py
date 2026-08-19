"""Sales/POS bounded context — domain layer.

SALES-3 builds the `Sale`/`SaleLine` aggregate (`entities.py`), `SaleTotals`
(`value_objects/sale_totals.py`, produced only by
`services/sale_totals_service.py`), the lifecycle/line/discount/suspension/
resumption/checkout/customer-assignment policies (`policies/`), and the
canonical `SaleEvents` catalog (`events.py` — not yet wired to the real
EventBus, see that module's own docstring). SALES-2 seeded the security
foundation (permission-denial/segregation-of-duties exceptions, the
AuthorizationGrant/SalesAuditEntry value objects) this phase builds on top
of without duplicating.
"""
