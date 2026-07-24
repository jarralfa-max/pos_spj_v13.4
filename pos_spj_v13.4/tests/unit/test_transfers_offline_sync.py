import pytest

from backend.application.transfers.offline_sync import (
    OfflineConflictType, OfflineSyncStatus, OfflineTransferEnvelope,
    TransferOfflineSyncService,
)
from backend.domain.transfers.exceptions import OfflineOperationNotAllowedError
from backend.domain.transfers.policies.offline_transfer_policy import (
    OfflineTransferOperation, OfflineTransferPolicy,
)


class Repository:
    def __init__(self):
        self.hashes, self.sequences, self.versions, self.results = {}, {}, {}, []
    def operation_hash(self, operation_id): return self.hashes.get(operation_id)
    def last_synced_sequence(self, device_id): return self.sequences.get(device_id, 0)
    def aggregate_version(self, transfer_id): return self.versions.get(transfer_id, 1)
    def record_result(self, *, envelope, result):
        self.results.append(result)
        if result.status is OfflineSyncStatus.SYNCED:
            self.hashes[envelope.operation_id] = envelope.payload_hash
            self.sequences[envelope.device_id] = envelope.local_sequence


class Executor:
    def __init__(self): self.operations = []
    def execute(self, envelope): self.operations.append(envelope.operation_id)


def envelope(operation_id="operation-1", sequence=1, transfer_id="transfer-1",
             operation=OfflineTransferOperation.RECEIVE, payload=None, version=1):
    return OfflineTransferEnvelope(operation_id, "device-1", sequence, transfer_id,
                                   operation, version, payload or {"quantity": "1.250"})


def service(repository=None):
    repository = repository or Repository()
    executor = Executor()
    policy = OfflineTransferPolicy(frozenset({OfflineTransferOperation.PICK,
                                              OfflineTransferOperation.RECEIVE}))
    return TransferOfflineSyncService(policy=policy, repository=repository,
                                      executor=executor), repository, executor


def test_sync_orders_operations_and_replay_is_idempotent():
    sync, repository, executor = service()
    first, second = envelope("operation-1", 1, "transfer-1"), envelope(
        "operation-2", 2, "transfer-2")
    results = sync.synchronize((second, first))
    assert [result.status for result in results] == [OfflineSyncStatus.SYNCED] * 2
    assert executor.operations == ["operation-1", "operation-2"]
    assert sync.synchronize((first,))[0].status is OfflineSyncStatus.SYNCED
    assert executor.operations == ["operation-1", "operation-2"]


def test_sync_detects_sequence_payload_and_version_conflicts_without_execution():
    sync, repository, executor = service()
    gap = sync.synchronize((envelope(sequence=2),))[0]
    assert gap.conflict_type is OfflineConflictType.SEQUENCE_GAP
    repository.hashes["duplicate"] = envelope("duplicate", payload={"x": "1"}).payload_hash
    mismatch = sync.synchronize((envelope("duplicate", payload={"x": "2"}),))[0]
    assert mismatch.conflict_type is OfflineConflictType.PAYLOAD_MISMATCH
    stale = sync.synchronize((envelope("stale", version=0),))[0]
    assert stale.conflict_type is OfflineConflictType.AGGREGATE_VERSION
    assert executor.operations == []
    assert {result.conflict_type for result in repository.results} == {
        OfflineConflictType.SEQUENCE_GAP, OfflineConflictType.PAYLOAD_MISMATCH,
        OfflineConflictType.AGGREGATE_VERSION,
    }


def test_policy_rejects_critical_operation_not_configured_for_offline():
    sync, _, _ = service()
    with pytest.raises(OfflineOperationNotAllowedError):
        sync.synchronize((envelope(operation=OfflineTransferOperation.DISPATCH),))


def test_envelope_hash_is_canonical_and_sequence_is_positive():
    left = envelope(payload={"weight": "2.500", "pieces": "2"})
    right = envelope(payload={"pieces": "2", "weight": "2.500"})
    assert left.payload_hash == right.payload_hash
    with pytest.raises(ValueError):
        envelope(sequence=0)
