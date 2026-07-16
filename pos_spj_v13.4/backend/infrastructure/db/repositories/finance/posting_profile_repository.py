"""PostingProfile repository — configurable account mappings with effectivity."""

from __future__ import annotations

import json
from datetime import date

from backend.domain.finance.entities.posting_profile import PostingProfile
from backend.domain.finance.enums import CommercialInstrumentType
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_COLUMNS = ("id, profile_key, description, accounts_json, effective_from, effective_to,"
            " instrument_type, program_id, campaign_id, branch_id, customer_type,"
            " currency_code, funding_party, active, created_at, updated_at")


def _to_entity(row: dict) -> PostingProfile:
    return PostingProfile(
        id=row["id"], profile_key=row["profile_key"], description=row["description"],
        accounts=json.loads(row["accounts_json"]),
        effective_from=date.fromisoformat(row["effective_from"]),
        effective_to=date.fromisoformat(row["effective_to"]) if row["effective_to"] else None,
        instrument_type=(CommercialInstrumentType(row["instrument_type"])
                         if row["instrument_type"] else None),
        program_id=row["program_id"], campaign_id=row["campaign_id"],
        branch_id=row["branch_id"], customer_type=row["customer_type"],
        currency_code=row["currency_code"], funding_party=row["funding_party"],
        active=bool(row["active"]),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


class PostingProfileRepository(FinanceRepositoryBase):
    def save(self, profile: PostingProfile) -> None:
        self._execute(
            f"INSERT INTO posting_profiles ({_COLUMNS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (profile.id, profile.profile_key, profile.description,
             json.dumps(profile.accounts), profile.effective_from.isoformat(),
             profile.effective_to.isoformat() if profile.effective_to else None,
             profile.instrument_type.value if profile.instrument_type else None,
             profile.program_id, profile.campaign_id, profile.branch_id,
             profile.customer_type, profile.currency_code, profile.funding_party,
             int(profile.active), profile.created_at, profile.updated_at),
        )

    def update(self, profile: PostingProfile) -> None:
        # Profiles are effectivity-versioned: past postings are never restated.
        self._execute(
            "UPDATE posting_profiles SET description=?, accounts_json=?, effective_to=?,"
            " active=?, updated_at=? WHERE id=?",
            (profile.description, json.dumps(profile.accounts),
             profile.effective_to.isoformat() if profile.effective_to else None,
             int(profile.active), profile.updated_at, profile.id),
        )

    def get(self, profile_id: str) -> PostingProfile | None:
        row = self._query_one(f"SELECT {_COLUMNS} FROM posting_profiles WHERE id=?", (profile_id,))
        return _to_entity(row) if row else None

    def find_effective(
        self,
        profile_key: str,
        on_date: date,
        *,
        instrument_type: CommercialInstrumentType | None = None,
        program_id: str | None = None,
        campaign_id: str | None = None,
        branch_id: str | None = None,
        currency_code: str | None = None,
        funding_party: str | None = None,
    ) -> PostingProfile | None:
        """Most specific active profile effective on ``on_date``.

        Specificity: campaign > program > branch > funding_party > generic.
        Candidate criteria must be NULL (generic) or equal to the requested value.
        """
        rows = self._query(
            f"SELECT {_COLUMNS} FROM posting_profiles WHERE profile_key=? AND active=1"
            " AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?)",
            (profile_key, on_date.isoformat(), on_date.isoformat()),
        )
        candidates = []
        requested = {
            "instrument_type": instrument_type.value if instrument_type else None,
            "program_id": program_id,
            "campaign_id": campaign_id,
            "branch_id": branch_id,
            "currency_code": currency_code,
            "funding_party": funding_party,
        }
        for row in rows:
            score = 0
            matches = True
            weights = {"campaign_id": 16, "program_id": 8, "branch_id": 4,
                       "funding_party": 2, "instrument_type": 1, "currency_code": 1}
            for criterion, requested_value in requested.items():
                row_value = row[criterion]
                if row_value is None:
                    continue
                if row_value != requested_value:
                    matches = False
                    break
                score += weights[criterion]
            if matches:
                candidates.append((score, row))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return _to_entity(candidates[0][1])

    def list_all(self) -> list[PostingProfile]:
        rows = self._query(f"SELECT {_COLUMNS} FROM posting_profiles ORDER BY profile_key, effective_from")
        return [_to_entity(row) for row in rows]
