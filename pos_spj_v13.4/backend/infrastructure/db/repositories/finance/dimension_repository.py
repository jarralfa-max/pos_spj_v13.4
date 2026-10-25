"""Projects and departments repository (§23)."""

from __future__ import annotations

from backend.domain.finance.entities.dimension import Department, Project
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase


def _project(row: dict) -> Project:
    return Project(id=row["id"], code=row["code"], name=row["name"],
                   branch_id=row["branch_id"], is_capex=bool(row["is_capex"]),
                   active=bool(row["active"]), created_at=row["created_at"])


def _department(row: dict) -> Department:
    return Department(id=row["id"], code=row["code"], name=row["name"],
                      active=bool(row["active"]), created_at=row["created_at"])


class DimensionRepository(FinanceRepositoryBase):
    def save_project(self, project: Project) -> None:
        self._insert("projects", {
            "id": project.id, "code": project.code, "name": project.name,
            "branch_id": project.branch_id, "is_capex": int(project.is_capex),
            "active": int(project.active), "created_at": project.created_at})

    def get_project(self, project_id: str) -> Project | None:
        row = self._query_one("SELECT * FROM projects WHERE id=?", (project_id,))
        return _project(row) if row else None

    def get_project_by_code(self, code: str) -> Project | None:
        row = self._query_one("SELECT * FROM projects WHERE code=?", (code,))
        return _project(row) if row else None

    def list_projects(self) -> list[Project]:
        return [_project(r) for r in
                self._query("SELECT * FROM projects WHERE active=1 ORDER BY code")]

    def save_department(self, department: Department) -> None:
        self._insert("departments", {
            "id": department.id, "code": department.code, "name": department.name,
            "active": int(department.active), "created_at": department.created_at})

    def get_department(self, department_id: str) -> Department | None:
        row = self._query_one("SELECT * FROM departments WHERE id=?", (department_id,))
        return _department(row) if row else None

    def get_department_by_code(self, code: str) -> Department | None:
        row = self._query_one("SELECT * FROM departments WHERE code=?", (code,))
        return _department(row) if row else None

    def list_departments(self) -> list[Department]:
        return [_department(r) for r in
                self._query("SELECT * FROM departments WHERE active=1 ORDER BY code")]
