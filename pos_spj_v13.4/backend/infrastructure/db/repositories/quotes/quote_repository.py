"""QuoteRepository — guarda la cotización con sus partidas (reemplazo completo
de las partidas en cada guardado; nunca hace commit, lo hace la unidad de trabajo)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.domain.quotes.entities import Quote, QuoteLine
from backend.domain.quotes.enums import QuoteStatus
from backend.shared.ids import new_uuid

_COLS = (
    "id, quote_number, revision, parent_quote_id, customer_id, opportunity_id, branch_id,"
    " status, valid_until, currency, notes, internal_notes, list_subtotal, discount_total,"
    " total, requires_approval, created_by_user_id, submitted_at, approved_by_user_id,"
    " approved_at, approval_note, sent_at, accepted_at, rejected_at, reject_reason,"
    " cancelled_at, cancel_reason, expired_at, converted_order_id, converted_at, version,"
    " operation_id, created_at, updated_at"
)
_LINE_COLS = (
    "id, quote_id, line_number, product_id, product_code, description, unit_code, weighed,"
    " quantity, list_price, unit_price, min_price, line_total, notes"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _Base:
    def __init__(self, connection) -> None:
        self._conn = connection

    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = self._conn.execute(sql, params)
        names = [c[0] for c in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]


class QuoteRepository(_Base):
    def next_number(self) -> str:
        # Las versiones llevan sufijo («COT-000003/2»): CAST toma sólo el número.
        row = self._conn.execute(
            "SELECT MAX(CAST(SUBSTR(quote_number, 5) AS INTEGER)) FROM quotes"
            " WHERE quote_number LIKE 'COT-%'").fetchone()
        last = int(row[0]) if row and row[0] is not None else 0
        return f"COT-{last + 1:06d}"

    def save(self, quote: Quote) -> None:
        params = self._params(quote)
        placeholders = ",".join("?" for _ in params)
        # Upsert, no INSERT OR REPLACE: REPLACE borra la fila y, con llaves
        # foráneas activas, rompería la referencia de las versiones posteriores.
        updates = ", ".join(f"{c.strip()}=excluded.{c.strip()}"
                            for c in _COLS.split(",")[1:])
        self._conn.execute(
            f"INSERT INTO quotes ({_COLS}) VALUES ({placeholders})"
            f" ON CONFLICT(id) DO UPDATE SET {updates}", params)
        self._conn.execute("DELETE FROM quote_lines WHERE quote_id=?", (quote.id,))
        for line in quote.lines:
            self._conn.execute(
                f"INSERT INTO quote_lines ({_LINE_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (line.id, quote.id, line.line_number, line.product_id, line.product_code,
                 line.description, line.unit_code, int(line.weighed), str(line.quantity),
                 str(line.list_price), str(line.unit_price),
                 None if line.min_price is None else str(line.min_price),
                 str(line.line_total), line.notes))

    def get(self, quote_id: str) -> Quote | None:
        rows = self._rows(f"SELECT {_COLS} FROM quotes WHERE id=?", (quote_id,))
        return self._hydrate(rows[0]) if rows else None

    def get_by_operation_id(self, operation_id: str) -> Quote | None:
        rows = self._rows(f"SELECT {_COLS} FROM quotes WHERE operation_id=?", (operation_id,))
        return self._hydrate(rows[0]) if rows else None

    def list_in_scope(self, scope, *, statuses: tuple[str, ...] = (),
                      customer_id: str | None = None, opportunity_id: str | None = None,
                      limit: int) -> list[dict]:
        """Encabezados (sin partidas) dentro del alcance resuelto: propias = las que
        hizo el usuario; sucursal = las de su sucursal; empresa = todas."""
        from backend.infrastructure.db.repositories.crm.scope_sql import scope_where
        where, params = scope_where(scope, responsible_col="created_by_user_id",
                                    creator_col="created_by_user_id", branch_col="branch_id")
        if statuses:
            where += f" AND status IN ({','.join('?' for _ in statuses)})"
            params += tuple(statuses)
        if customer_id:
            where += " AND customer_id=?"
            params += (customer_id,)
        if opportunity_id:
            where += " AND opportunity_id=?"
            params += (opportunity_id,)
        return self._rows(
            f"SELECT {_COLS}, (SELECT COUNT(*) FROM quote_lines l WHERE l.quote_id=quotes.id)"
            f" AS line_count FROM quotes WHERE {where} ORDER BY created_at DESC LIMIT ?",
            (*params, limit))

    def list_expirable(self, today: date, *, limit: int) -> list[Quote]:
        rows = self._rows(
            f"SELECT {_COLS} FROM quotes WHERE status IN ('PENDING_APPROVAL','APPROVED','SENT')"
            " AND valid_until < ? ORDER BY valid_until LIMIT ?", (today.isoformat(), limit))
        return [self._hydrate(r) for r in rows]

    # helpers -------------------------------------------------------------------
    @staticmethod
    def _params(q: Quote) -> tuple:
        return (
            q.id, q.quote_number, q.revision, q.parent_quote_id, q.customer_id, q.opportunity_id,
            q.branch_id, q.status.value, q.valid_until.isoformat(), q.currency, q.notes,
            q.internal_notes, str(q.list_subtotal), str(q.discount_total), str(q.total),
            int(q.requires_approval), q.created_by_user_id, q.submitted_at,
            q.approved_by_user_id, q.approved_at, q.approval_note, q.sent_at, q.accepted_at,
            q.rejected_at, q.reject_reason, q.cancelled_at, q.cancel_reason, q.expired_at,
            q.converted_order_id, q.converted_at, q.version, q.operation_id, q.created_at,
            q.updated_at,
        )

    def _hydrate(self, row: dict) -> Quote:
        lines = [
            QuoteLine(
                id=r["id"], quote_id=r["quote_id"], line_number=int(r["line_number"]),
                product_id=r["product_id"], product_code=r["product_code"] or "",
                description=r["description"], unit_code=r["unit_code"] or "",
                weighed=bool(r["weighed"]), quantity=Decimal(r["quantity"]),
                list_price=Decimal(r["list_price"]), unit_price=Decimal(r["unit_price"]),
                min_price=None if r["min_price"] is None else Decimal(r["min_price"]),
                notes=r["notes"] or "")
            for r in self._rows(f"SELECT {_LINE_COLS} FROM quote_lines WHERE quote_id=?"
                                " ORDER BY line_number", (row["id"],))
        ]
        return Quote(
            id=row["id"], quote_number=row["quote_number"], revision=int(row["revision"]),
            parent_quote_id=row["parent_quote_id"], customer_id=row["customer_id"],
            opportunity_id=row["opportunity_id"], branch_id=row["branch_id"],
            status=QuoteStatus(row["status"]),
            valid_until=date.fromisoformat(str(row["valid_until"])[:10]),
            currency=row["currency"] or "MXN", notes=row["notes"] or "",
            internal_notes=row["internal_notes"] or "",
            created_by_user_id=row["created_by_user_id"], submitted_at=row["submitted_at"],
            approved_by_user_id=row["approved_by_user_id"], approved_at=row["approved_at"],
            approval_note=row["approval_note"] or "", sent_at=row["sent_at"],
            accepted_at=row["accepted_at"], rejected_at=row["rejected_at"],
            reject_reason=row["reject_reason"] or "", cancelled_at=row["cancelled_at"],
            cancel_reason=row["cancel_reason"] or "", expired_at=row["expired_at"],
            converted_order_id=row["converted_order_id"], converted_at=row["converted_at"],
            lines=lines, version=int(row["version"]), operation_id=row["operation_id"],
            created_at=row["created_at"], updated_at=row["updated_at"])


class QuoteAuditRepository(_Base):
    def record(self, *, quote_id: str, action: str, actor_user_id: str | None,
               detail: str = "", operation_id: str | None = None) -> None:
        self._conn.execute(
            "INSERT INTO quote_audit_log (id, quote_id, action, actor_user_id, detail,"
            " operation_id, created_at) VALUES (?,?,?,?,?,?,?)",
            (new_uuid(), quote_id, action, actor_user_id, detail, operation_id, _now()))

    def list_for_quote(self, quote_id: str) -> list[dict]:
        return self._rows(
            "SELECT action, actor_user_id, detail, created_at FROM quote_audit_log"
            " WHERE quote_id=? ORDER BY created_at, rowid", (quote_id,))


class QuoteOutboxRepository(_Base):
    def enqueue(self, event_name: str, payload: dict, operation_id: str | None) -> None:
        self._conn.execute(
            "INSERT INTO quote_outbox (id, event_name, payload_json, operation_id, created_at)"
            " VALUES (?,?,?,?,?)",
            (new_uuid(), event_name, json.dumps(payload, ensure_ascii=False, default=str),
             operation_id, _now()))
