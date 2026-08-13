"""CRMBIExportQueryService (§55, §49-55): "CRM expone leads/conversiones/
pipeline/actividad/oportunidades/casos/SLA/segmentos/retención/recencia/
frecuencia/crédito/calidad; BI calcula CLV/churn/cohortes/propensión/
forecast avanzado/ROI." This service is the export surface — it only counts
and sums what this bounded context already owns, never the advanced metrics
listed as BI's own job.

Company-wide, not scoped by OWN/TEAM/BRANCH/TERRITORY/PORTFOLIO (unlike
every other CRM query service) — an export is inherently a full-company
snapshot for another module to consume, gated by its own dedicated
``BI_EXPORT_VIEW`` permission (§73: "exportar datos sensibles deja
evidencia") rather than by ``CustomerDataScopeResolver``/
``CRMDataScopeResolver``.

Reads only tables the overall Clientes/CRM module already owns across its
five CRM_SUBCONTEXTS (leads/opportunities/segments live in ``crm``,
``customer_data_quality_issues`` lives in ``customers``) — the same
"compose freely across our own five sub-contexts" latitude
``Customer360QueryService`` already exercises, never reaching into a
genuinely external module (Ventas/Finanzas/WhatsApp/Fidelidad, this
phase's other summaries). So unlike every other summary CRM-13 builds,
there is no cross-context identity gap here — every id involved is already
this module's own UUIDv7.

``sla_breach_count`` is a SIMPLIFIED proxy (``resolution_due_at`` passed,
not resolved, not paused) for BI aggregate purposes only — it deliberately
does not reimplement ``SLAQueryService``'s full canonical breach-status
computation (paused-time accounting, at-risk threshold); that service
remains the source of truth for any single case's real SLA status.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions


@dataclass(frozen=True)
class CRMBIExportSnapshot:
    leads_total: int
    leads_converted: int
    lead_conversion_rate: float
    opportunities_open: int
    opportunities_won: int
    opportunities_lost: int
    open_cases: int
    sla_breach_count: int
    active_segment_memberships: int
    open_data_quality_issues: int


class CRMBIExportQueryService:
    def __init__(self, connection, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._auth = authorization or CRMAuthorizationPolicy()

    def get_snapshot(self, *, actor_user_id: str) -> CRMBIExportSnapshot:
        self._auth.require(actor_user_id, CRMPermissions.BI_EXPORT_VIEW)

        leads_total = self._count("SELECT COUNT(*) FROM leads")
        leads_converted = self._count(
            "SELECT COUNT(*) FROM leads WHERE status='CONVERTED'")
        conversion_rate = (leads_converted / leads_total) if leads_total else 0.0

        opportunities_open = self._count(
            "SELECT COUNT(*) FROM opportunities WHERE status IN ('OPEN','ON_HOLD')")
        opportunities_won = self._count(
            "SELECT COUNT(*) FROM opportunities WHERE status='WON'")
        opportunities_lost = self._count(
            "SELECT COUNT(*) FROM opportunities WHERE status='LOST'")

        open_cases = self._count(
            "SELECT COUNT(*) FROM service_cases WHERE status NOT IN"
            " ('RESOLVED','CLOSED','CANCELLED')")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        sla_breach_count = self._count(
            "SELECT COUNT(*) FROM sla_instances WHERE resolved_at IS NULL"
            " AND paused=0 AND resolution_due_at < ?", (now,))

        active_segments = self._count(
            "SELECT COUNT(*) FROM customer_segment_memberships WHERE removed_at IS NULL")
        open_quality_issues = self._count(
            "SELECT COUNT(*) FROM customer_data_quality_issues WHERE status='OPEN'")

        return CRMBIExportSnapshot(
            leads_total=leads_total, leads_converted=leads_converted,
            lead_conversion_rate=conversion_rate, opportunities_open=opportunities_open,
            opportunities_won=opportunities_won, opportunities_lost=opportunities_lost,
            open_cases=open_cases, sla_breach_count=sla_breach_count,
            active_segment_memberships=active_segments,
            open_data_quality_issues=open_quality_issues)

    def _count(self, sql: str, params: tuple = ()) -> int:
        row = self._conn.execute(sql, params).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
