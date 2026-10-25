"""Lotes físicos de cupones y vales: lote, piezas y reglas por vale (migración 349).

Los repositorios nunca confirman: `CommercialInstrumentsUnitOfWork` es dueño de
la transacción.
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.domain.commercial_instruments.entities.instrument_batch import (
    BatchStatus,
    InstrumentBatch,
    InstrumentKind,
)
from backend.domain.commercial_instruments.value_objects.redemption_rules import (
    FundingSource,
    LeftoverPolicy,
    PercentBase,
    RedemptionMode,
    RedemptionRules,
)
from backend.infrastructure.db.repositories.commercial_instruments.base import (
    CommercialInstrumentsRepositoryBase,
    now_iso,
)
from backend.shared.ids import new_uuid


def _dec_or_none(value) -> Decimal | None:
    return None if value in (None, "") else Decimal(str(value))


class InstrumentBatchRepository(CommercialInstrumentsRepositoryBase):
    _COLUMNS = (
        "id", "kind", "definition_id", "name", "quantity", "unit_value", "funding_source",
        "status", "valid_from", "valid_to", "branch_ids_json", "redemption_mode",
        "max_redemptions", "max_percent_per_sale", "percent_base", "leftover_policy",
        "created_by_user_id", "approved_by_user_id", "approved_at", "printed_count",
        "activated_at", "cancelled_reason", "created_at", "updated_at",
    )

    def save(self, batch: InstrumentBatch) -> None:
        valores = (
            batch.id, batch.kind.value, batch.definition_id, batch.name, int(batch.quantity),
            str(batch.unit_value), batch.funding_source.value, batch.status.value,
            batch.valid_from, batch.valid_to, batch.branch_ids_json, batch.redemption_mode.value,
            batch.max_redemptions,
            None if batch.max_percent_per_sale is None else str(batch.max_percent_per_sale),
            batch.percent_base.value, batch.leftover_policy.value, batch.created_by_user_id,
            batch.approved_by_user_id, batch.approved_at, batch.printed_count,
            batch.activated_at, batch.cancelled_reason, batch.created_at, batch.updated_at)
        columnas = ", ".join(self._COLUMNS)
        marcas = ", ".join("?" for _ in self._COLUMNS)
        cambios = ", ".join(f"{c}=excluded.{c}" for c in self._COLUMNS if c != "id")
        self._conn.execute(
            f"INSERT INTO instrument_batches ({columnas}) VALUES ({marcas})"
            f" ON CONFLICT(id) DO UPDATE SET {cambios}", valores)

    def get(self, batch_id: str) -> InstrumentBatch | None:
        fila = self._query_one("SELECT * FROM instrument_batches WHERE id=?", (batch_id,))
        return None if fila is None else self._hydrate(fila)

    def list_recent(self, limit: int = 200) -> list[InstrumentBatch]:
        return [self._hydrate(f) for f in self._query(
            "SELECT * FROM instrument_batches ORDER BY created_at DESC, id DESC LIMIT ?",
            (int(limit),))]

    @staticmethod
    def _hydrate(fila: dict) -> InstrumentBatch:
        lote = InstrumentBatch.__new__(InstrumentBatch)
        # Sin __post_init__: un lote guardado ya se validó al crearse, y uno de
        # un prepago antiguo (si existiera) no debe dejar de poder leerse.
        valores = dict(
            id=fila["id"], kind=InstrumentKind(fila["kind"]), definition_id=fila["definition_id"],
            name=fila["name"], quantity=int(fila["quantity"]),
            unit_value=Decimal(str(fila["unit_value"])),
            funding_source=FundingSource(fila["funding_source"]),
            created_by_user_id=fila["created_by_user_id"], status=BatchStatus(fila["status"]),
            valid_from=fila["valid_from"], valid_to=fila["valid_to"],
            branch_ids=tuple(json.loads(fila["branch_ids_json"] or "[]")),
            redemption_mode=RedemptionMode(fila["redemption_mode"]),
            max_redemptions=fila["max_redemptions"],
            max_percent_per_sale=_dec_or_none(fila["max_percent_per_sale"]),
            percent_base=PercentBase(fila["percent_base"]),
            leftover_policy=LeftoverPolicy(fila["leftover_policy"]),
            approved_by_user_id=fila["approved_by_user_id"], approved_at=fila["approved_at"],
            printed_count=int(fila["printed_count"] or 0), activated_at=fila["activated_at"],
            cancelled_reason=fila["cancelled_reason"], created_at=fila["created_at"],
            updated_at=fila["updated_at"])
        for nombre, valor in valores.items():
            object.__setattr__(lote, nombre, valor)
        return lote


class InstrumentBatchItemRepository(CommercialInstrumentsRepositoryBase):
    def add(self, *, batch_id: str, sequence_no: int, folio: str, instance_kind: str,
            instance_id: str, token_hash: str, token_prefix: str, item_id: str | None = None,
            token_version: int = 1) -> str:
        item_id = item_id or new_uuid()
        self._conn.execute(
            "INSERT INTO instrument_batch_items (id, batch_id, sequence_no, folio, instance_kind,"
            " instance_id, token_hash, token_prefix, token_version, status, print_count,"
            " created_at) VALUES (?,?,?,?,?,?,?,?,?,'ISSUED',0,?)",
            (item_id, batch_id, int(sequence_no), folio, instance_kind, instance_id, token_hash,
             token_prefix, int(token_version), now_iso()))
        return item_id

    def list_for_batch(self, batch_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM instrument_batch_items WHERE batch_id=? ORDER BY sequence_no",
            (batch_id,))

    def get_by_token_hash(self, token_hash: str) -> dict | None:
        return self._query_one(
            "SELECT * FROM instrument_batch_items WHERE token_hash=?", (token_hash,))

    def get(self, item_id: str) -> dict | None:
        return self._query_one("SELECT * FROM instrument_batch_items WHERE id=?", (item_id,))

    def get_for_instance(self, instance_id: str) -> dict | None:
        return self._query_one(
            "SELECT * FROM instrument_batch_items WHERE instance_id=?", (instance_id,))

    def set_status(self, batch_id: str, status: str, *, only_from: tuple[str, ...]) -> None:
        marcas = ",".join("?" for _ in only_from)
        self._conn.execute(
            f"UPDATE instrument_batch_items SET status=? WHERE batch_id=? AND status IN ({marcas})",
            (status, batch_id, *only_from))

    def mark_printed(self, batch_id: str) -> None:
        self._conn.execute(
            "UPDATE instrument_batch_items SET print_count = print_count + 1"
            " WHERE batch_id=? AND status <> 'REVOKED'", (batch_id,))

    def rotate_token(self, item_id: str, *, token_hash: str, token_prefix: str,
                     token_version: int) -> None:
        self._conn.execute(
            "UPDATE instrument_batch_items SET token_hash=?, token_prefix=?, token_version=?"
            " WHERE id=?", (token_hash, token_prefix, int(token_version), item_id))

    def revoke(self, item_id: str, reason: str) -> None:
        self._conn.execute(
            "UPDATE instrument_batch_items SET status='REVOKED', revoked_reason=? WHERE id=?",
            (reason, item_id))

    def counts(self, batch_id: str) -> dict[str, int]:
        return {f["status"]: int(f["n"]) for f in self._query(
            "SELECT status, COUNT(*) AS n FROM instrument_batch_items WHERE batch_id=?"
            " GROUP BY status", (batch_id,))}


class VoucherRulesRepository(CommercialInstrumentsRepositoryBase):
    def save(self, *, voucher_instance_id: str, batch: InstrumentBatch) -> None:
        reglas = batch.rules()
        self._conn.execute(
            "INSERT OR IGNORE INTO voucher_instance_rules (voucher_instance_id, batch_id,"
            " redemption_mode, max_redemptions, max_percent_per_sale, percent_base,"
            " leftover_policy, funding_source, branch_ids_json, valid_from, valid_to, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (voucher_instance_id, batch.id, reglas.mode.value, reglas.effective_max_redemptions,
             None if reglas.max_percent_per_sale is None else str(reglas.max_percent_per_sale),
             reglas.percent_base.value, reglas.leftover_policy.value,
             reglas.funding_source.value, batch.branch_ids_json, batch.valid_from,
             batch.valid_to, now_iso()))

    def get(self, voucher_instance_id: str) -> dict | None:
        """`{"rules": RedemptionRules, "branch_ids", "valid_from", "valid_to", "batch_id"}`
        o `None` si el vale no se emitió por lote."""
        if self._scalar("SELECT 1 FROM sqlite_master WHERE type='table'"
                        " AND name='voucher_instance_rules'") is None:
            return None  # base anterior a la 349
        fila = self._query_one("SELECT * FROM voucher_instance_rules WHERE voucher_instance_id=?",
                               (voucher_instance_id,))
        if fila is None:
            return None
        return {
            "rules": RedemptionRules(
                mode=RedemptionMode(fila["redemption_mode"]),
                max_redemptions=fila["max_redemptions"],
                max_percent_per_sale=_dec_or_none(fila["max_percent_per_sale"]),
                percent_base=PercentBase(fila["percent_base"]),
                leftover_policy=LeftoverPolicy(fila["leftover_policy"]),
                funding_source=FundingSource(fila["funding_source"])),
            "branch_ids": tuple(json.loads(fila["branch_ids_json"] or "[]")),
            "valid_from": fila["valid_from"], "valid_to": fila["valid_to"],
            "batch_id": fila["batch_id"],
        }


__all__ = ["InstrumentBatchItemRepository", "InstrumentBatchRepository",
           "VoucherRulesRepository"]
