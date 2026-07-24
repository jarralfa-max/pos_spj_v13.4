"""Ordered, idempotent synchronization of locally captured transfer operations."""
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Protocol

from backend.domain.transfers.policies.offline_transfer_policy import (
    OfflineTransferOperation, OfflineTransferPolicy,
)


class OfflineSyncStatus(str, Enum):
    PENDING = "PENDING"
    SYNCED = "SYNCED"
    CONFLICT = "CONFLICT"
    REJECTED = "REJECTED"


class OfflineConflictType(str, Enum):
    SEQUENCE_GAP = "SEQUENCE_GAP"
    PAYLOAD_MISMATCH = "PAYLOAD_MISMATCH"
    AGGREGATE_VERSION = "AGGREGATE_VERSION"


@dataclass(frozen=True, slots=True)
class OfflineTransferEnvelope:
    operation_id: str
    device_id: str
    local_sequence: int
    transfer_id: str
    operation_type: OfflineTransferOperation
    base_version: int
    payload: dict[str, object]

    def __post_init__(self) -> None:
        if not self.operation_id or not self.device_id or not self.transfer_id:
            raise ValueError("Offline envelope requires operation, device, and transfer IDs")
        if self.local_sequence < 1 or self.base_version < 0:
            raise ValueError("Offline sequence/version cannot be negative")

    @property
    def payload_hash(self) -> str:
        canonical = json.dumps(self.payload, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False)
        return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class OfflineSyncResult:
    operation_id: str
    status: OfflineSyncStatus
    conflict_type: OfflineConflictType | None = None


class OfflineTransferSyncRepository(Protocol):
    def operation_hash(self, operation_id: str) -> str | None: ...
    def last_synced_sequence(self, device_id: str) -> int: ...
    def aggregate_version(self, transfer_id: str) -> int: ...
    def record_result(self, *, envelope: OfflineTransferEnvelope,
                      result: OfflineSyncResult) -> None: ...


class OfflineTransferOperationExecutor(Protocol):
    def execute(self, envelope: OfflineTransferEnvelope) -> None: ...


class TransferOfflineSyncService:
    def __init__(self, *, policy: OfflineTransferPolicy,
                 repository: OfflineTransferSyncRepository,
                 executor: OfflineTransferOperationExecutor) -> None:
        self._policy = policy
        self._repository = repository
        self._executor = executor

    def synchronize(self, envelopes: tuple[OfflineTransferEnvelope, ...]) -> tuple[OfflineSyncResult, ...]:
        ordered = tuple(sorted(envelopes, key=lambda item: (item.device_id,
                                                            item.local_sequence)))
        results: list[OfflineSyncResult] = []
        expected_by_device: dict[str, int] = {}
        for envelope in ordered:
            self._policy.require_allowed(envelope.operation_type)
            stored_hash = self._repository.operation_hash(envelope.operation_id)
            if stored_hash is not None:
                status = (OfflineSyncStatus.SYNCED if stored_hash == envelope.payload_hash
                          else OfflineSyncStatus.CONFLICT)
                conflict = None if status is OfflineSyncStatus.SYNCED else OfflineConflictType.PAYLOAD_MISMATCH
                result = OfflineSyncResult(envelope.operation_id, status, conflict)
                if status is OfflineSyncStatus.CONFLICT:
                    self._repository.record_result(envelope=envelope, result=result)
                results.append(result)
                continue
            expected = expected_by_device.setdefault(
                envelope.device_id,
                self._repository.last_synced_sequence(envelope.device_id) + 1)
            if envelope.local_sequence != expected:
                result = OfflineSyncResult(envelope.operation_id, OfflineSyncStatus.CONFLICT,
                                           OfflineConflictType.SEQUENCE_GAP)
            elif self._repository.aggregate_version(envelope.transfer_id) != envelope.base_version:
                result = OfflineSyncResult(envelope.operation_id, OfflineSyncStatus.CONFLICT,
                                           OfflineConflictType.AGGREGATE_VERSION)
            else:
                self._executor.execute(envelope)
                result = OfflineSyncResult(envelope.operation_id, OfflineSyncStatus.SYNCED)
                expected_by_device[envelope.device_id] = expected + 1
            self._repository.record_result(envelope=envelope, result=result)
            results.append(result)
        return tuple(results)
