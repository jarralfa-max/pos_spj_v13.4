"""CASH-19 ordered offline-first synchronization over the canonical outbox."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol, Sequence

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.application.cash_register.shift_use_cases import _record
from backend.domain.cash_register.events import CashEvents
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork
from backend.shared.ids import new_uuid, validate_uuidv7


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def retry_at(now: datetime, attempt_count: int) -> datetime:
    """Exponential retry capped at fifteen minutes; deterministic and testable."""
    seconds = min(15 * 60, 2 ** max(0, min(attempt_count, 10)))
    return now + timedelta(seconds=seconds)


@dataclass(frozen=True, slots=True)
class SyncEnvelope:
    envelope_id: str
    sequence_no: int
    aggregate_version: int
    event_name: str
    operation_id: str
    entity_id: str
    payload: dict


@dataclass(frozen=True, slots=True)
class SyncAcknowledgement:
    envelope_id: str
    outcome: str
    remote_revision: str = ""
    error_code: str = ""
    conflict: dict | None = None


@dataclass(frozen=True, slots=True)
class SyncCycleResult:
    status: str
    staged: int
    sent: int
    synced: int
    retries: int
    conflicts: int


class CashSyncTransport(Protocol):
    def push(self, *, device_id: str, branch_id: str,
             envelopes: Sequence[SyncEnvelope]) -> Sequence[SyncAcknowledgement]: ...


class CashOfflineSyncService:
    def __init__(self, transport: CashSyncTransport, *, batch_size: int = 50) -> None:
        if not 1 <= batch_size <= 500:
            raise ValueError("Sync batch size must be between 1 and 500")
        self._transport, self._batch_size = transport, batch_size

    def synchronize(self, connection, *, device_id: str, branch_id: str,
                    now: datetime | None = None) -> SyncCycleResult:
        validate_uuidv7(device_id); validate_uuidv7(branch_id)
        instant = now or _now()
        timestamp = _iso(instant)
        with CashRegisterUnitOfWork(connection) as uow:
            device = uow.sync.get_device(device_id)
            if device is None or device["branch_id"] != branch_id:
                raise LookupError("Sync device outside branch scope")
            if device["connectivity"] == "OFFLINE":
                state = uow.sync.state(device_id)
                return SyncCycleResult("OFFLINE", 0, 0, 0, 0, state["conflict_count"])
            staged = uow.sync.stage_pending(device_id=device_id, branch_id=branch_id,
                                            now=timestamp, limit=self._batch_size)
            ready = uow.sync.list_ready(device_id=device_id, now=timestamp,
                                        limit=self._batch_size)
            if not ready:
                state = uow.sync.state(device_id)
                final = "CONFLICT" if state["conflict_count"] else "IDLE"
                uow.sync.finish_cycle(device_id=device_id, status=final, now=timestamp)
                return SyncCycleResult(final, staged, 0, 0, 0, state["conflict_count"])
            uow.sync.mark_in_flight([row["id"] for row in ready])
        envelopes = [SyncEnvelope(
            row["id"], row["sequence_no"], row["aggregate_version"],
            row["event_name"], row["operation_id"], row["entity_id"],
            json.loads(row["payload_json"]),
        ) for row in ready]
        try:
            responses = {ack.envelope_id: ack for ack in self._transport.push(
                device_id=device_id, branch_id=branch_id, envelopes=envelopes)}
        except Exception:
            responses = {}
        synced = retries = conflicts = 0
        with CashRegisterUnitOfWork(connection) as uow:
            for row in ready:
                ack = responses.get(row["id"])
                if ack is not None and ack.outcome == "ACCEPTED":
                    uow.sync.mark_synced(envelope_id=row["id"], device_id=device_id,
                                         sequence_no=row["sequence_no"],
                                         remote_revision=ack.remote_revision, now=timestamp)
                    synced += 1
                elif ack is not None and ack.outcome == "CONFLICT":
                    uow.sync.mark_conflict(envelope_id=row["id"],
                                           remote_revision=ack.remote_revision,
                                           conflict=ack.conflict or {})
                    conflicts += 1
                else:
                    error = ack.error_code if ack and ack.error_code else "TRANSPORT_UNAVAILABLE"
                    uow.sync.mark_retry(envelope_id=row["id"],
                                        next_attempt_at=_iso(retry_at(instant, row["attempt_count"] + 1)),
                                        error=error)
                    retries += 1
            final = "CONFLICT" if conflicts else ("RETRYING" if retries else "IDLE")
            uow.sync.finish_cycle(device_id=device_id, status=final, now=timestamp,
                                  error="SYNC_RETRY_PENDING" if retries else None)
        return SyncCycleResult(final, staged, len(ready), synced, retries, conflicts)


class CashSyncStateQueryService:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._authorization = authorization

    def get(self, connection, *, device_id: str, branch_id: str,
            actor_user_id: str) -> dict:
        self._authorization.require(user_id=actor_user_id,
                                    permission_code=CashPermissions.SYNC_VIEW,
                                    branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            state = uow.sync.state(device_id)
        if state["branch_id"] != branch_id:
            raise LookupError("Sync device outside branch scope")
        return state


class RegisterCashSyncDeviceUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._authorization = authorization

    def execute(self, connection, *, device_id: str, branch_id: str,
                actor_user_id: str, online: bool = True) -> None:
        self._authorization.require(user_id=actor_user_id,
                                    permission_code=CashPermissions.SYNC_MANAGE,
                                    branch_id=branch_id)
        validate_uuidv7(device_id); validate_uuidv7(branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            uow.sync.register_device(device_id=device_id, branch_id=branch_id,
                                     now=_iso(_now()), online=online)


class SetCashSyncConnectivityUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._authorization = authorization

    def execute(self, connection, *, device_id: str, branch_id: str,
                actor_user_id: str, online: bool) -> None:
        self._authorization.require(user_id=actor_user_id,
                                    permission_code=CashPermissions.SYNC_MANAGE,
                                    branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            device = uow.sync.get_device(device_id)
            if device is None or device["branch_id"] != branch_id:
                raise LookupError("Sync device outside branch scope")
            uow.sync.set_connectivity(device_id=device_id, online=online, now=_iso(_now()))


class ResolveCashSyncConflictUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._authorization = authorization

    def execute(self, connection, *, envelope_id: str, strategy: str,
                reason: str, branch_id: str, actor_user_id: str,
                operation_id: str) -> None:
        self._authorization.require(user_id=actor_user_id,
                                    permission_code=CashPermissions.SYNC_MANAGE,
                                    branch_id=branch_id)
        if not reason.strip():
            raise ValueError("Conflict resolution requires a reason")
        for value in (envelope_id, branch_id, actor_user_id, operation_id):
            validate_uuidv7(value)
        timestamp = _iso(_now())
        with CashRegisterUnitOfWork(connection) as uow:
            envelope = uow.sync.get_envelope(envelope_id)
            if envelope is None:
                raise LookupError("Sync conflict not found")
            device = uow.sync.get_device(envelope["device_id"])
            if device is None or device["branch_id"] != branch_id:
                raise LookupError("Sync conflict outside branch scope")
            uow.sync.resolve_conflict(envelope_id=envelope_id, strategy=strategy, now=timestamp)
            _record(uow, CashEvents.SYNC_CONFLICT_RESOLVED,
                    operation_id=operation_id, entity_id=envelope_id,
                    branch_id=branch_id, actor_user_id=actor_user_id,
                    reason=reason, strategy=strategy,
                    remote_revision=envelope["remote_revision"])
