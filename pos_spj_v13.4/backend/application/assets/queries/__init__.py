"""Read-side of the Assets/EAM bounded context (ASSET-14, §63).

QueryServices depend only on the domain's Protocol repository ports, never on
a concrete SQLite implementation — so they're fully unit-testable today with
fake in-memory port implementations, even though no infrastructure layer
exists yet for Activos. UI consumes DTOs only (§63), never raw entities.
"""

from __future__ import annotations
