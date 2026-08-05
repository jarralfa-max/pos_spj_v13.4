"""Read-only query service for the LOSS-16 desktop page."""

class LossRootCauseQueryService:
    def __init__(self, repository): self._repository=repository
    def search_catalog(self, query): return self._repository.search_catalog(query)
    def search_open_investigations(self, branch_id, query):
        return self._repository.search_open_investigations(branch_id,query)
