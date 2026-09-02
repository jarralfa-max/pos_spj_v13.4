"""EntryRepository / TicketRepository — persist/reconstruct
SweepstakesEntry (append-only) and SweepstakesTicket (LOY-15, §27-28)."""

from __future__ import annotations

from backend.domain.sweepstakes.entities.sweepstakes_entry import SweepstakesEntry
from backend.domain.sweepstakes.entities.sweepstakes_ticket import SweepstakesTicket
from backend.domain.sweepstakes.enums import SweepstakesEntryMethod, SweepstakesTicketStatus
from backend.infrastructure.db.repositories.sweepstakes.base import SweepstakesRepositoryBase


class SweepstakesEntryRepository(SweepstakesRepositoryBase):
    def add(self, entry: SweepstakesEntry) -> None:
        self._execute(
            """
            INSERT INTO sweepstakes_entries (
                id, campaign_id, customer_id, entry_method, chances_granted, source_sale_id,
                notes, granted_by_user_id, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                entry.id, entry.campaign_id, entry.customer_id, entry.entry_method.value,
                entry.chances_granted, entry.source_sale_id, entry.notes,
                entry.granted_by_user_id, entry.created_at,
            ),
        )

    def get(self, entry_id: str) -> SweepstakesEntry | None:
        row = self._query_one("SELECT * FROM sweepstakes_entries WHERE id=?", (entry_id,))
        return self._hydrate(row) if row else None

    def list_for_customer(self, campaign_id: str, customer_id: str) -> list[SweepstakesEntry]:
        rows = self._query(
            "SELECT * FROM sweepstakes_entries WHERE campaign_id=? AND customer_id=?"
            " ORDER BY created_at", (campaign_id, customer_id))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> SweepstakesEntry:
        return SweepstakesEntry(
            id=row["id"], campaign_id=row["campaign_id"], customer_id=row["customer_id"],
            entry_method=SweepstakesEntryMethod(row["entry_method"]),
            chances_granted=row["chances_granted"], source_sale_id=row["source_sale_id"],
            notes=row["notes"], granted_by_user_id=row["granted_by_user_id"],
            created_at=row["created_at"],
        )


class SweepstakesTicketRepository(SweepstakesRepositoryBase):
    def save(self, ticket: SweepstakesTicket) -> None:
        self._execute(
            """
            INSERT INTO sweepstakes_tickets (
                id, campaign_id, entry_id, customer_id, ticket_number, status, print_count,
                first_printed_at, last_printed_at, void_reason, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                print_count=excluded.print_count,
                first_printed_at=excluded.first_printed_at,
                last_printed_at=excluded.last_printed_at,
                void_reason=excluded.void_reason
            """,
            (
                ticket.id, ticket.campaign_id, ticket.entry_id, ticket.customer_id,
                ticket.ticket_number, ticket.status.value, ticket.print_count,
                ticket.first_printed_at, ticket.last_printed_at, ticket.void_reason,
                ticket.created_at,
            ),
        )

    def get(self, ticket_id: str) -> SweepstakesTicket | None:
        row = self._query_one("SELECT * FROM sweepstakes_tickets WHERE id=?", (ticket_id,))
        return self._hydrate(row) if row else None

    def get_by_number(self, campaign_id: str, ticket_number: str) -> SweepstakesTicket | None:
        row = self._query_one(
            "SELECT * FROM sweepstakes_tickets WHERE campaign_id=? AND ticket_number=?",
            (campaign_id, ticket_number))
        return self._hydrate(row) if row else None

    def count_for_entry(self, entry_id: str) -> int:
        return self._scalar(
            "SELECT COUNT(*) FROM sweepstakes_tickets WHERE entry_id=?", (entry_id,), default=0)

    def count_for_campaign(self, campaign_id: str) -> int:
        return self._scalar(
            "SELECT COUNT(*) FROM sweepstakes_tickets WHERE campaign_id=?",
            (campaign_id,), default=0)

    def count_for_customer(self, campaign_id: str, customer_id: str) -> int:
        return self._scalar(
            "SELECT COUNT(*) FROM sweepstakes_tickets WHERE campaign_id=? AND customer_id=?"
            " AND status != 'VOID'", (campaign_id, customer_id), default=0)

    def list_eligible_for_campaign(self, campaign_id: str) -> list[SweepstakesTicket]:
        rows = self._query(
            "SELECT * FROM sweepstakes_tickets WHERE campaign_id=? AND status IN"
            " ('ISSUED','PRINTED')", (campaign_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> SweepstakesTicket:
        return SweepstakesTicket(
            id=row["id"], campaign_id=row["campaign_id"], entry_id=row["entry_id"],
            customer_id=row["customer_id"], ticket_number=row["ticket_number"],
            status=SweepstakesTicketStatus(row["status"]), print_count=row["print_count"],
            first_printed_at=row["first_printed_at"], last_printed_at=row["last_printed_at"],
            void_reason=row["void_reason"], created_at=row["created_at"],
        )
