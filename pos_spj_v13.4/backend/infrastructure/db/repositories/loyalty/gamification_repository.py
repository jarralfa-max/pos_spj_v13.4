"""Gamification repositories (LOY-9, §16): challenge definitions, per-
member progress, streaks, badges. Mirrors the rest of this package's
conventions exactly."""

from __future__ import annotations

from backend.domain.loyalty.entities.challenge_progress import ChallengeProgress
from backend.domain.loyalty.entities.loyalty_badge import LoyaltyBadge
from backend.domain.loyalty.entities.loyalty_challenge import LoyaltyChallenge
from backend.domain.loyalty.entities.loyalty_streak import LoyaltyStreak
from backend.domain.loyalty.enums import ChallengeCriteriaType, ChallengeMode, ChallengeStatus
from backend.infrastructure.db.repositories.loyalty.base import (
    LoyaltyRepositoryBase,
    bool_to_int,
    dec_str,
    int_to_bool,
    to_decimal,
)


class LoyaltyChallengeRepository(LoyaltyRepositoryBase):
    def save(self, challenge: LoyaltyChallenge) -> None:
        self._execute(
            """
            INSERT INTO loyalty_challenge_definitions (
                id, program_id, code, name, criteria_type, target_value, points_reward,
                mode, description, status, start_date, end_date, branch_scope,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                target_value=excluded.target_value,
                points_reward=excluded.points_reward,
                description=excluded.description,
                status=excluded.status,
                start_date=excluded.start_date,
                end_date=excluded.end_date,
                branch_scope=excluded.branch_scope,
                updated_at=excluded.updated_at
            """,
            (
                challenge.id, challenge.program_id, challenge.code, challenge.name,
                challenge.criteria_type.value, dec_str(challenge.target_value),
                dec_str(challenge.points_reward), challenge.mode.value,
                challenge.description, challenge.status.value, challenge.start_date,
                challenge.end_date, challenge.branch_scope, challenge.created_at,
                challenge.updated_at,
            ),
        )

    def get(self, challenge_id: str) -> LoyaltyChallenge | None:
        row = self._query_one(
            "SELECT * FROM loyalty_challenge_definitions WHERE id=?", (challenge_id,))
        return self._hydrate(row) if row else None

    def list_active_for_program(self, program_id: str) -> list[LoyaltyChallenge]:
        rows = self._query(
            "SELECT * FROM loyalty_challenge_definitions WHERE program_id=? AND status='ACTIVE'"
            " ORDER BY name", (program_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyChallenge:
        return LoyaltyChallenge(
            id=row["id"], program_id=row["program_id"], code=row["code"], name=row["name"],
            criteria_type=ChallengeCriteriaType(row["criteria_type"]),
            target_value=to_decimal(row["target_value"]),
            points_reward=to_decimal(row["points_reward"]), mode=ChallengeMode(row["mode"]),
            description=row["description"], status=ChallengeStatus(row["status"]),
            start_date=row["start_date"], end_date=row["end_date"],
            branch_scope=row["branch_scope"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class ChallengeProgressRepository(LoyaltyRepositoryBase):
    def save(self, progress: ChallengeProgress) -> None:
        self._execute(
            """
            INSERT INTO loyalty_challenge_member_progress (
                id, challenge_id, membership_id, current_value, completed, completed_at,
                points_awarded, updated_at
            ) VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                current_value=excluded.current_value,
                completed=excluded.completed,
                completed_at=excluded.completed_at,
                points_awarded=excluded.points_awarded,
                updated_at=excluded.updated_at
            """,
            (
                progress.id, progress.challenge_id, progress.membership_id,
                dec_str(progress.current_value), bool_to_int(progress.completed),
                progress.completed_at, dec_str(progress.points_awarded), progress.updated_at,
            ),
        )

    def get(self, progress_id: str) -> ChallengeProgress | None:
        row = self._query_one(
            "SELECT * FROM loyalty_challenge_member_progress WHERE id=?", (progress_id,))
        return self._hydrate(row) if row else None

    def get_by_challenge_and_membership(
        self, challenge_id: str, membership_id: str,
    ) -> ChallengeProgress | None:
        row = self._query_one(
            "SELECT * FROM loyalty_challenge_member_progress"
            " WHERE challenge_id=? AND membership_id=?", (challenge_id, membership_id))
        return self._hydrate(row) if row else None

    @staticmethod
    def _hydrate(row: dict) -> ChallengeProgress:
        return ChallengeProgress(
            id=row["id"], challenge_id=row["challenge_id"], membership_id=row["membership_id"],
            current_value=to_decimal(row["current_value"]),
            completed=int_to_bool(row["completed"]), completed_at=row["completed_at"],
            points_awarded=to_decimal(row["points_awarded"]), updated_at=row["updated_at"],
        )


class LoyaltyStreakRepository(LoyaltyRepositoryBase):
    def save(self, streak: LoyaltyStreak) -> None:
        self._execute(
            """
            INSERT INTO loyalty_streaks (
                id, membership_id, streak_type, current_count, longest_count, last_period,
                updated_at
            ) VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                current_count=excluded.current_count,
                longest_count=excluded.longest_count,
                last_period=excluded.last_period,
                updated_at=excluded.updated_at
            """,
            (
                streak.id, streak.membership_id, streak.streak_type, streak.current_count,
                streak.longest_count, streak.last_period, streak.updated_at,
            ),
        )

    def get_by_membership_and_type(
        self, membership_id: str, streak_type: str,
    ) -> LoyaltyStreak | None:
        row = self._query_one(
            "SELECT * FROM loyalty_streaks WHERE membership_id=? AND streak_type=?",
            (membership_id, streak_type))
        return self._hydrate(row) if row else None

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyStreak:
        return LoyaltyStreak(
            id=row["id"], membership_id=row["membership_id"], streak_type=row["streak_type"],
            current_count=row["current_count"], longest_count=row["longest_count"],
            last_period=row["last_period"], updated_at=row["updated_at"],
        )


class LoyaltyBadgeRepository(LoyaltyRepositoryBase):
    def add(self, badge: LoyaltyBadge) -> None:
        self._execute(
            """
            INSERT INTO loyalty_badges (
                id, membership_id, badge_code, source_challenge_id, earned_at
            ) VALUES (?,?,?,?,?)
            """,
            (badge.id, badge.membership_id, badge.badge_code, badge.source_challenge_id,
             badge.earned_at),
        )

    def list_for_membership(self, membership_id: str) -> list[LoyaltyBadge]:
        rows = self._query(
            "SELECT * FROM loyalty_badges WHERE membership_id=? ORDER BY earned_at",
            (membership_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyBadge:
        return LoyaltyBadge(
            id=row["id"], membership_id=row["membership_id"], badge_code=row["badge_code"],
            source_challenge_id=row["source_challenge_id"], earned_at=row["earned_at"],
        )
