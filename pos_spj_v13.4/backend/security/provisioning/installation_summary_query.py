"""InstallationSummaryQueryService — SHELL-7.

Read-only, display-only data for `LoginWindow` — the company/branch name to
show above the login form. Deliberately not `InstallationStatusQuery`
(SHELL-2): that answers "what state is the installation in," this answers
"what should the screen say." Reads `configuraciones` (where
`ProvisionInstallationUseCase` wrote `empresa_nombre`) and `sucursales`
directly — no new table, nothing to migrate.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstallationSummary:
    company_name: str
    branch_name: str


class InstallationSummaryQueryService:
    def __init__(self, conn) -> None:
        self._conn = conn

    def get_summary(self) -> InstallationSummary:
        company_row = self._conn.execute(
            "SELECT valor FROM configuraciones WHERE clave = 'empresa_nombre'"
        ).fetchone()
        company_name = (company_row[0] if company_row else "") or ""

        installation_row = self._conn.execute(
            "SELECT initial_branch_id FROM installation LIMIT 1"
        ).fetchone()
        branch_name = ""
        if installation_row and installation_row["initial_branch_id"]:
            branch_row = self._conn.execute(
                "SELECT nombre FROM sucursales WHERE id = ?",
                (installation_row["initial_branch_id"],),
            ).fetchone()
            branch_name = (branch_row[0] if branch_row else "") or ""

        return InstallationSummary(company_name=company_name, branch_name=branch_name)
