"""ProcessGenealogyQueryService (PROC-18, §38). Read-only traversal of the
genealogy graph recorded by ProcessGenealogyLink — "qué lotes se
consumieron", "qué orden los generó", upstream/downstream, and recall (given
a lot, find everything downstream of it). A pure read path (CLAUDE.md §13:
"Toda lectura para UI debe pasar por QueryService") — no authorization gate
here; that belongs to the caller/route layer, same as this codebase's other
read-only query services.
"""

from __future__ import annotations

from typing import Any

from backend.domain.meat_processing.entities.process_genealogy_link import ProcessGenealogyLink
from backend.infrastructure.db.repositories.meat_processing.process_genealogy_link_repository import (
    ProcessGenealogyLinkRepository,
)

_DEFAULT_MAX_DEPTH = 10


class ProcessGenealogyQueryService:
    def __init__(self, connection: Any) -> None:
        self._repo = ProcessGenealogyLinkRepository(connection)

    def get_upstream_links(self, entity_type: str, entity_id: str) -> list[ProcessGenealogyLink]:
        """Direct upstream neighbors only (one hop) — what fed this entity."""
        return self._repo.list_by_downstream(entity_type, entity_id)

    def get_downstream_links(self, entity_type: str, entity_id: str
                              ) -> list[ProcessGenealogyLink]:
        """Direct downstream neighbors only (one hop) — what this entity fed."""
        return self._repo.list_by_upstream(entity_type, entity_id)

    def trace_downstream(self, entity_type: str, entity_id: str, *,
                          max_depth: int = _DEFAULT_MAX_DEPTH) -> list[ProcessGenealogyLink]:
        """Every link reachable forward from this entity, however many hops."""
        return self._breadth_first(
            [(entity_type, entity_id)],
            expand=lambda etype, eid: self._repo.list_by_upstream(etype, eid),
            next_node=lambda link: (link.downstream_entity_type, link.downstream_entity_id),
            max_depth=max_depth)

    def trace_upstream(self, entity_type: str, entity_id: str, *,
                        max_depth: int = _DEFAULT_MAX_DEPTH) -> list[ProcessGenealogyLink]:
        """Every link reachable backward from this entity, however many hops."""
        return self._breadth_first(
            [(entity_type, entity_id)],
            expand=lambda etype, eid: self._repo.list_by_downstream(etype, eid),
            next_node=lambda link: (link.upstream_entity_type, link.upstream_entity_id),
            max_depth=max_depth)

    def trace_lot_downstream(self, lot_id: str, *,
                              max_depth: int = _DEFAULT_MAX_DEPTH) -> list[ProcessGenealogyLink]:
        """§38 "recall": every link downstream of anything that touched this lot."""
        seeds = self._repo.list_by_lot(lot_id)
        frontier = [(link.downstream_entity_type, link.downstream_entity_id) for link in seeds]
        rest = self._breadth_first(
            frontier,
            expand=lambda etype, eid: self._repo.list_by_upstream(etype, eid),
            next_node=lambda link: (link.downstream_entity_type, link.downstream_entity_id),
            max_depth=max_depth, seen_link_ids={link.id for link in seeds})
        return seeds + rest

    @staticmethod
    def _breadth_first(frontier, *, expand, next_node, max_depth, seen_link_ids=None):
        seen_link_ids = set() if seen_link_ids is None else set(seen_link_ids)
        collected: list[ProcessGenealogyLink] = []
        for _ in range(max_depth):
            if not frontier:
                break
            next_frontier = []
            for entity_type, entity_id in frontier:
                for link in expand(entity_type, entity_id):
                    if link.id in seen_link_ids:
                        continue
                    seen_link_ids.add(link.id)
                    collected.append(link)
                    next_frontier.append(next_node(link))
            frontier = next_frontier
        return collected
