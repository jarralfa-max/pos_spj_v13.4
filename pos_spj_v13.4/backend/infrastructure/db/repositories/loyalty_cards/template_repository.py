"""LoyaltyCardTemplateRepository / LoyaltyCardTemplateVersionRepository —
persist/reconstruct LoyaltyCardTemplate and LoyaltyCardTemplateVersion
(LOY-17, §33-34)."""

from __future__ import annotations

from backend.domain.loyalty_cards.entities.loyalty_card_template import LoyaltyCardTemplate
from backend.domain.loyalty_cards.entities.loyalty_card_template_version import (
    LoyaltyCardTemplateVersion,
)
from backend.domain.loyalty_cards.enums import (
    LoyaltyCardTemplateStatus,
    LoyaltyCardTemplateTargetType,
    LoyaltyCardTemplateVersionStatus,
)
from backend.infrastructure.db.repositories.loyalty_cards.base import LoyaltyCardsRepositoryBase


class LoyaltyCardTemplateRepository(LoyaltyCardsRepositoryBase):
    def save(self, template: LoyaltyCardTemplate) -> None:
        self._execute(
            """
            INSERT INTO loyalty_card_templates (
                id, code, name, description, target_type, status, active_version_id,
                created_by_user_id, approved_by_user_id, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                status=excluded.status,
                active_version_id=excluded.active_version_id,
                approved_by_user_id=excluded.approved_by_user_id,
                updated_at=excluded.updated_at
            """,
            (
                template.id, template.code, template.name, template.description,
                template.target_type.value, template.status.value, template.active_version_id,
                template.created_by_user_id, template.approved_by_user_id,
                template.created_at, template.updated_at,
            ),
        )

    def get(self, template_id: str) -> LoyaltyCardTemplate | None:
        row = self._query_one("SELECT * FROM loyalty_card_templates WHERE id=?", (template_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> LoyaltyCardTemplate | None:
        row = self._query_one("SELECT * FROM loyalty_card_templates WHERE code=?", (code,))
        return self._hydrate(row) if row else None

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyCardTemplate:
        return LoyaltyCardTemplate(
            id=row["id"], code=row["code"], name=row["name"], description=row["description"],
            target_type=LoyaltyCardTemplateTargetType(row["target_type"]),
            status=LoyaltyCardTemplateStatus(row["status"]),
            active_version_id=row["active_version_id"],
            created_by_user_id=row["created_by_user_id"],
            approved_by_user_id=row["approved_by_user_id"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class LoyaltyCardTemplateVersionRepository(LoyaltyCardsRepositoryBase):
    def save(self, version: LoyaltyCardTemplateVersion) -> None:
        self._execute(
            """
            INSERT INTO loyalty_card_template_versions (
                id, template_id, version_number, design_schema_json, status,
                created_by_user_id, approved_by_user_id, activated_at, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                approved_by_user_id=excluded.approved_by_user_id,
                activated_at=excluded.activated_at
            """,
            (
                version.id, version.template_id, version.version_number,
                version.design_schema_json, version.status.value, version.created_by_user_id,
                version.approved_by_user_id, version.activated_at, version.created_at,
            ),
        )

    def get(self, version_id: str) -> LoyaltyCardTemplateVersion | None:
        row = self._query_one(
            "SELECT * FROM loyalty_card_template_versions WHERE id=?", (version_id,))
        return self._hydrate(row) if row else None

    def list_for_template(self, template_id: str) -> list[LoyaltyCardTemplateVersion]:
        rows = self._query(
            "SELECT * FROM loyalty_card_template_versions WHERE template_id=?"
            " ORDER BY version_number", (template_id,))
        return [self._hydrate(row) for row in rows]

    def count_for_template(self, template_id: str) -> int:
        return self._scalar(
            "SELECT COUNT(*) FROM loyalty_card_template_versions WHERE template_id=?",
            (template_id,), default=0)

    def get_active_for_template(self, template_id: str) -> LoyaltyCardTemplateVersion | None:
        row = self._query_one(
            "SELECT * FROM loyalty_card_template_versions WHERE template_id=? AND status='ACTIVE'",
            (template_id,))
        return self._hydrate(row) if row else None

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyCardTemplateVersion:
        return LoyaltyCardTemplateVersion(
            id=row["id"], template_id=row["template_id"], version_number=row["version_number"],
            design_schema_json=row["design_schema_json"],
            status=LoyaltyCardTemplateVersionStatus(row["status"]),
            created_by_user_id=row["created_by_user_id"],
            approved_by_user_id=row["approved_by_user_id"], activated_at=row["activated_at"],
            created_at=row["created_at"],
        )
