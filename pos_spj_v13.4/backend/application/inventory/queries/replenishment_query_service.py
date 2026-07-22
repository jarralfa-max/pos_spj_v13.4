"""ReplenishmentQueryService — read side for planning UI/BI (§34).

Lists the active rules and the open suggestions the generator produced. Read-only.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.replenishment_repository import (
    ReplenishmentRuleRepository,
    ReplenishmentSuggestionRepository,
)


class ReplenishmentQueryService:
    def __init__(self, connection) -> None:
        self._rules = ReplenishmentRuleRepository(connection)
        self._suggestions = ReplenishmentSuggestionRepository(connection)

    def list_rules(self, *, branch_id: str | None = None) -> list[dict]:
        return self._rules.list_active(branch_id=branch_id)

    def list_open_suggestions(self, *, branch_id: str | None = None) -> list[dict]:
        return self._suggestions.list_open(branch_id=branch_id)
