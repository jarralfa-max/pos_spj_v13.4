"""InstallationSummaryQueryService — SHELL-7.

Read-only, display-only data for `LoginWindow` — the company/branch name to
show above the login form. Deliberately not `InstallationStatusQuery`
(SHELL-2): that answers "what state is the installation in," this answers
"what should the screen say." Reads the company name from the canonical
`company_profiles` record `installation.company_id` points at, and the branch
name from `sucursales`. It used to read a `configuraciones.empresa_nombre`
copy that provisioning wrote alongside the real profile; that copy is gone,
so renaming the company in Configuración now shows up here instead of leaving
the login screen on a stale name forever.
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
        installation_row = self._conn.execute(
            "SELECT company_id, initial_branch_id FROM installation LIMIT 1"
        ).fetchone()

        company_name = ""
        if installation_row and installation_row["company_id"]:
            company_row = self._conn.execute(
                "SELECT legal_name FROM company_profiles WHERE id = ?",
                (installation_row["company_id"],),
            ).fetchone()
            company_name = (company_row[0] if company_row else "") or ""

        branch_name = ""
        if installation_row and installation_row["initial_branch_id"]:
            branch_row = self._conn.execute(
                "SELECT nombre FROM sucursales WHERE id = ?",
                (installation_row["initial_branch_id"],),
            ).fetchone()
            branch_name = (branch_row[0] if branch_row else "") or ""

        return InstallationSummary(company_name=company_name, branch_name=branch_name)
