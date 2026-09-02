"""LoyaltyProgramRepository — persists/reconstructs `LoyaltyProgram` against
`loyalty_program_definitions` (backend/infrastructure/db/schema/loyalty_schema.py).

Named after the table, NOT "loyalty_programs" — see loyalty_schema.py's own
docstring for the real naming collision with the legacy Growth Engine table
this phase found and worked around.

Concrete class, no `Protocol` port — mirrors the Sales/Inventory family's
convention (this bounded context's schema explicitly follows sales_schema.py's
conventions). Never commits — LoyaltyUnitOfWork owns the transaction boundary.
"""

from __future__ import annotations

from backend.domain.loyalty.entities.loyalty_program import LoyaltyProgram
from backend.domain.loyalty.enums import ProgramStatus
from backend.infrastructure.db.repositories.loyalty.base import (
    LoyaltyRepositoryBase,
    bool_to_int,
    int_to_bool,
)


class LoyaltyProgramRepository(LoyaltyRepositoryBase):
    def save(self, program: LoyaltyProgram) -> None:
        self._execute(
            """
            INSERT INTO loyalty_program_definitions (
                id, code, name, currency_name, description, currency_symbol,
                status, enrollment_mode, earning_enabled, redemption_enabled,
                tiering_enabled, expiration_enabled, branch_scope, channel_scope,
                effective_from, effective_to, created_by_user_id,
                approved_by_user_id, approved_at, activated_at, suspended_at,
                closed_at, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                currency_name=excluded.currency_name,
                description=excluded.description,
                currency_symbol=excluded.currency_symbol,
                status=excluded.status,
                enrollment_mode=excluded.enrollment_mode,
                earning_enabled=excluded.earning_enabled,
                redemption_enabled=excluded.redemption_enabled,
                tiering_enabled=excluded.tiering_enabled,
                expiration_enabled=excluded.expiration_enabled,
                branch_scope=excluded.branch_scope,
                channel_scope=excluded.channel_scope,
                effective_from=excluded.effective_from,
                effective_to=excluded.effective_to,
                approved_by_user_id=excluded.approved_by_user_id,
                approved_at=excluded.approved_at,
                activated_at=excluded.activated_at,
                suspended_at=excluded.suspended_at,
                closed_at=excluded.closed_at,
                updated_at=excluded.updated_at
            """,
            (
                program.id, program.code, program.name, program.currency_name,
                program.description, program.currency_symbol,
                program.status.value, program.enrollment_mode,
                bool_to_int(program.earning_enabled),
                bool_to_int(program.redemption_enabled),
                bool_to_int(program.tiering_enabled),
                bool_to_int(program.expiration_enabled),
                program.branch_scope, program.channel_scope,
                program.effective_from, program.effective_to,
                program.created_by_user_id, program.approved_by_user_id,
                program.approved_at, program.activated_at, program.suspended_at,
                program.closed_at, program.created_at, program.updated_at,
            ),
        )

    def get(self, program_id: str) -> LoyaltyProgram | None:
        row = self._query_one(
            "SELECT * FROM loyalty_program_definitions WHERE id=?", (program_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> LoyaltyProgram | None:
        row = self._query_one(
            "SELECT * FROM loyalty_program_definitions WHERE code=?", (code,))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[LoyaltyProgram]:
        rows = self._query(
            "SELECT * FROM loyalty_program_definitions WHERE status=? ORDER BY name",
            (ProgramStatus.ACTIVE.value,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyProgram:
        return LoyaltyProgram(
            id=row["id"], code=row["code"], name=row["name"],
            currency_name=row["currency_name"], description=row["description"],
            currency_symbol=row["currency_symbol"],
            status=ProgramStatus(row["status"]), enrollment_mode=row["enrollment_mode"],
            earning_enabled=int_to_bool(row["earning_enabled"]),
            redemption_enabled=int_to_bool(row["redemption_enabled"]),
            tiering_enabled=int_to_bool(row["tiering_enabled"]),
            expiration_enabled=int_to_bool(row["expiration_enabled"]),
            branch_scope=row["branch_scope"], channel_scope=row["channel_scope"],
            effective_from=row["effective_from"], effective_to=row["effective_to"],
            created_by_user_id=row["created_by_user_id"],
            approved_by_user_id=row["approved_by_user_id"],
            approved_at=row["approved_at"], activated_at=row["activated_at"],
            suspended_at=row["suspended_at"], closed_at=row["closed_at"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
