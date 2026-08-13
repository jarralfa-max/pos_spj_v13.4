"""CustomerCommunicationPreferenceRepository — persists the 1:1
communication preference record per customer."""

from __future__ import annotations

from backend.domain.customer_privacy.entities.customer_communication_preference import (
    CustomerCommunicationPreference,
)
from backend.domain.customer_privacy.enums import PreferredChannel
from backend.infrastructure.db.repositories.customer_privacy.base import (
    CustomerPrivacyRepositoryBase,
)

_PREFERENCE_COLS = (
    "id, customer_id, preferred_channel, preferred_language, contact_hours_start,"
    " contact_hours_end, allow_transactional, allow_operational, allow_marketing,"
    " allow_promotions, allow_reminders, updated_by_user_id, created_at, updated_at"
)


class CustomerCommunicationPreferenceRepository(CustomerPrivacyRepositoryBase):
    def save(self, preference: CustomerCommunicationPreference) -> None:
        self._execute(
            f"INSERT INTO customer_communication_preferences ({_PREFERENCE_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(preference))

    def update(self, preference: CustomerCommunicationPreference) -> None:
        self._execute(
            "UPDATE customer_communication_preferences SET preferred_channel=?,"
            " preferred_language=?, contact_hours_start=?, contact_hours_end=?,"
            " allow_operational=?, allow_marketing=?, allow_promotions=?, allow_reminders=?,"
            " updated_by_user_id=?, updated_at=? WHERE id=?",
            (preference.preferred_channel.value, preference.preferred_language,
             preference.contact_hours_start, preference.contact_hours_end,
             int(preference.allow_operational), int(preference.allow_marketing),
             int(preference.allow_promotions), int(preference.allow_reminders),
             preference.updated_by_user_id, preference.updated_at, preference.id))

    def get_by_customer_id(self, customer_id: str) -> CustomerCommunicationPreference | None:
        row = self._query_one(
            f"SELECT {_PREFERENCE_COLS} FROM customer_communication_preferences"
            " WHERE customer_id=?", (customer_id,))
        return self._hydrate(row) if row else None

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(preference: CustomerCommunicationPreference) -> tuple:
        return (
            preference.id, preference.customer_id, preference.preferred_channel.value,
            preference.preferred_language, preference.contact_hours_start,
            preference.contact_hours_end, int(preference.allow_transactional),
            int(preference.allow_operational), int(preference.allow_marketing),
            int(preference.allow_promotions), int(preference.allow_reminders),
            preference.updated_by_user_id, preference.created_at, preference.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerCommunicationPreference:
        return CustomerCommunicationPreference(
            id=row["id"], customer_id=row["customer_id"],
            preferred_channel=PreferredChannel(row["preferred_channel"]),
            preferred_language=row["preferred_language"],
            contact_hours_start=row["contact_hours_start"],
            contact_hours_end=row["contact_hours_end"],
            allow_transactional=bool(row["allow_transactional"]),
            allow_operational=bool(row["allow_operational"]),
            allow_marketing=bool(row["allow_marketing"]),
            allow_promotions=bool(row["allow_promotions"]),
            allow_reminders=bool(row["allow_reminders"]),
            updated_by_user_id=row["updated_by_user_id"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
