"""Public display settings reuse governed resolution and official branding."""
from backend.application.settings.catalog import SETTINGS_CATALOG
from backend.application.settings.configuration_reader import ConfigurationReader
from backend.application.queries.document_output.ticket_design_query_service import TicketDesignQueryService
from backend.domain.settings.enums import ScopeType


class DisplayPreferencesQuery:
    def __init__(self, connection):
        self._reader = ConfigurationReader(connection)
        self._branding = TicketDesignQueryService(connection)

    def resolve(self, *, branch_id=None, company_id=None, workstation_id=None):
        context = {}
        if company_id:
            context[ScopeType.COMPANY] = company_id
        if branch_id:
            context[ScopeType.BRANCH] = branch_id
        if workstation_id:
            context[ScopeType.WORKSTATION] = workstation_id
        values = {spec.key.split(".", 1)[1]: self._reader.get(spec.key, context=context)
                  for spec in SETTINGS_CATALOG if spec.key.startswith("customer_display.")}
        branding = self._branding.branding(branch_id)
        values["branding"] = {"name": branding.header.get("company_name", ""),
                              "tagline": branding.header.get("header_text", ""),
                              "logo_path": branding.logo_path}
        return values
