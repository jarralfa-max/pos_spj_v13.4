"""LoyaltyCardSheetProfileRepository / LoyaltyCardImpositionProfileRepository
— persist/reconstruct sheet + imposition profiles (LOY-20, §38-40)."""

from __future__ import annotations

from decimal import Decimal

from backend.domain.loyalty_cards.entities.loyalty_card_imposition_profile import (
    LoyaltyCardImpositionProfile,
)
from backend.domain.loyalty_cards.entities.loyalty_card_sheet_profile import (
    LoyaltyCardSheetProfile,
)
from backend.domain.loyalty_cards.enums import SheetOrientation
from backend.infrastructure.db.repositories.loyalty_cards.base import LoyaltyCardsRepositoryBase


def _dec(value) -> Decimal:
    return Decimal(str(value))


def _bool(value) -> bool:
    return bool(value)


class LoyaltyCardSheetProfileRepository(LoyaltyCardsRepositoryBase):
    def save(self, profile: LoyaltyCardSheetProfile) -> None:
        self._execute(
            """
            INSERT INTO loyalty_card_sheet_profiles (
                id, code, name, width_mm, height_mm, orientation, margin_top_mm,
                margin_bottom_mm, margin_left_mm, margin_right_mm, active, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                active=excluded.active,
                updated_at=excluded.updated_at
            """,
            (
                profile.id, profile.code, profile.name, str(profile.width_mm),
                str(profile.height_mm), profile.orientation.value, str(profile.margin_top_mm),
                str(profile.margin_bottom_mm), str(profile.margin_left_mm),
                str(profile.margin_right_mm), int(profile.active), profile.created_at,
                profile.updated_at,
            ),
        )

    def get(self, profile_id: str) -> LoyaltyCardSheetProfile | None:
        row = self._query_one(
            "SELECT * FROM loyalty_card_sheet_profiles WHERE id=?", (profile_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> LoyaltyCardSheetProfile | None:
        row = self._query_one(
            "SELECT * FROM loyalty_card_sheet_profiles WHERE code=?", (code,))
        return self._hydrate(row) if row else None

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyCardSheetProfile:
        return LoyaltyCardSheetProfile(
            id=row["id"], code=row["code"], name=row["name"], width_mm=_dec(row["width_mm"]),
            height_mm=_dec(row["height_mm"]), orientation=SheetOrientation(row["orientation"]),
            margin_top_mm=_dec(row["margin_top_mm"]), margin_bottom_mm=_dec(row["margin_bottom_mm"]),
            margin_left_mm=_dec(row["margin_left_mm"]), margin_right_mm=_dec(row["margin_right_mm"]),
            active=_bool(row["active"]), created_at=row["created_at"], updated_at=row["updated_at"],
        )


class LoyaltyCardImpositionProfileRepository(LoyaltyCardsRepositoryBase):
    def save(self, profile: LoyaltyCardImpositionProfile) -> None:
        self._execute(
            """
            INSERT INTO loyalty_card_imposition_profiles (
                id, sheet_profile_id, card_width_mm, card_height_mm, columns, rows, bleed_mm,
                safe_area_mm, gutter_horizontal_mm, gutter_vertical_mm, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                profile.id, profile.sheet_profile_id, str(profile.card_width_mm),
                str(profile.card_height_mm), profile.columns, profile.rows,
                str(profile.bleed_mm), str(profile.safe_area_mm),
                str(profile.gutter_horizontal_mm), str(profile.gutter_vertical_mm),
                profile.created_at,
            ),
        )

    def get(self, profile_id: str) -> LoyaltyCardImpositionProfile | None:
        row = self._query_one(
            "SELECT * FROM loyalty_card_imposition_profiles WHERE id=?", (profile_id,))
        return self._hydrate(row) if row else None

    def list_for_sheet(self, sheet_profile_id: str) -> list[LoyaltyCardImpositionProfile]:
        rows = self._query(
            "SELECT * FROM loyalty_card_imposition_profiles WHERE sheet_profile_id=?"
            " ORDER BY created_at", (sheet_profile_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyCardImpositionProfile:
        return LoyaltyCardImpositionProfile(
            id=row["id"], sheet_profile_id=row["sheet_profile_id"],
            card_width_mm=_dec(row["card_width_mm"]), card_height_mm=_dec(row["card_height_mm"]),
            columns=row["columns"], rows=row["rows"], bleed_mm=_dec(row["bleed_mm"]),
            safe_area_mm=_dec(row["safe_area_mm"]),
            gutter_horizontal_mm=_dec(row["gutter_horizontal_mm"]),
            gutter_vertical_mm=_dec(row["gutter_vertical_mm"]), created_at=row["created_at"],
        )
