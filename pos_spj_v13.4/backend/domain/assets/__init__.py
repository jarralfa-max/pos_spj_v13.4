"""Assets / Enterprise Asset Management (EAM) domain — bounded context.

Owns the physical asset lifecycle: registry, classification, location,
custody, condition, maintenance, work orders, inspections, warranties,
meters, transfers, physical inventory, tagging/QR and operational disposal.

Does NOT own accounting value, financial depreciation, journal entries,
CAPEX/OPEX posting or disposal gain/loss — those belong to
``backend/domain/finance`` (see ``docs/refactor/assets_finance_boundary_map.md``).
The existing ``backend.domain.finance.entities.fixed_asset.FixedAsset`` is a
distinct entity correlated by id/events, never merged with ``Asset`` here.
"""

from __future__ import annotations
