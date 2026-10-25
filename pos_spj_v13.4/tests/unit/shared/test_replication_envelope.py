"""Contrato del sobre de replicación (arquitectura híbrida, Slice 1)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.domain.cash_register.events import CashEvents, cash_event_payload
from backend.shared.ids import new_uuid
from backend.shared.sync.replication_envelope import (
    MAX_PAYLOAD_BYTES,
    EnvelopeError,
    ReplicationAck,
    ReplicationEnvelope,
    ReplicationOutcome,
    canonical_json,
    envelope_from_outbox_event,
)

T0 = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def _sobre(**cambios) -> ReplicationEnvelope:
    datos = dict(
        event_id=new_uuid(), operation_id=new_uuid(), event_type="SALE_COMPLETED",
        schema_version=1, aggregate_type="sales.sale", aggregate_id=new_uuid(),
        aggregate_version=3, branch_id=new_uuid(), workstation_id=new_uuid(),
        sequence_no=7, occurred_at=T0, actor_id=new_uuid(),
        payload={"total": Decimal("1250.50"), "lines": [{"qty": Decimal("1.250")}]})
    datos.update(cambios)
    return ReplicationEnvelope(**datos)


# ── ida y vuelta ─────────────────────────────────────────────────────────────
def test_round_trip_is_exact_and_deterministic():
    sobre = _sobre(correlation_id=new_uuid(), causation_id=new_uuid(),
                   authorization={"permission": "POS.venta.cobrar"})
    texto = sobre.to_json()
    assert texto == sobre.to_json()                      # determinista
    leido = ReplicationEnvelope.from_json(texto)
    assert leido == sobre and leido.content_hash == sobre.content_hash
    # El Decimal conserva valor y escala; nunca pasa por float.
    assert json.loads(texto)["payload"] == {"total": "1250.50", "lines": [{"qty": "1.250"}]}


def test_canonical_json_orders_keys_and_normalizes_time_to_utc():
    mexico = timezone(timedelta(hours=-6))
    a = canonical_json({"b": 1, "a": datetime(2026, 10, 24, 6, 0, tzinfo=mexico)})
    assert a == '{"a":"2026-10-24T12:00:00+00:00","b":1}'
    sobre = _sobre(occurred_at=datetime(2026, 10, 24, 6, 0, tzinfo=mexico))
    assert sobre.occurred_at == T0 and sobre.occurred_at.tzinfo == timezone.utc


# ── dinero y tipos ───────────────────────────────────────────────────────────
def test_float_is_refused_when_building_and_when_reading():
    with pytest.raises(EnvelopeError) as e:
        _sobre(payload={"total": 1250.5})
    assert e.value.code == "FLOAT_NOT_ALLOWED" and "payload.total" in str(e.value)
    texto = _sobre().to_json().replace('"1250.50"', "1250.50")
    with pytest.raises(EnvelopeError) as e:
        ReplicationEnvelope.from_json(texto)
    assert e.value.code == "FLOAT_NOT_ALLOWED"


@pytest.mark.parametrize("payload,code", [
    ({"x": Decimal("NaN")}, "DECIMAL_NOT_FINITE"),
    ({"x": datetime(2026, 1, 1)}, "NAIVE_DATETIME"),
    ({1: "clave numérica"}, "NON_STRING_KEY"),
    ({"x": object()}, "UNSERIALIZABLE"),
])
def test_values_that_would_lose_meaning_are_refused(payload, code):
    with pytest.raises(EnvelopeError) as e:
        _sobre(payload=payload)
    assert e.value.code == code


def test_payload_size_is_capped():
    with pytest.raises(EnvelopeError) as e:
        _sobre(payload={"x": "a" * (MAX_PAYLOAD_BYTES + 1)})
    assert e.value.code == "PAYLOAD_TOO_LARGE"


# ── identidad, orden y versiones ─────────────────────────────────────────────
@pytest.mark.parametrize("cambio,code", [
    ({"event_id": "1"}, "INVALID_IDENTIFIER"),
    ({"branch_id": "01900000-0000-4000-8000-000000000001"}, "INVALID_IDENTIFIER"),
    ({"actor_id": "admin"}, "INVALID_IDENTIFIER"),
    ({"event_type": "venta"}, "INVALID_EVENT_TYPE"),
    ({"aggregate_type": "Sale"}, "INVALID_AGGREGATE_TYPE"),
    ({"sequence_no": 0}, "INVALID_ORDINAL"),
    ({"aggregate_version": -1}, "INVALID_ORDINAL"),
    ({"schema_version": True}, "INVALID_ORDINAL"),
    ({"occurred_at": datetime(2026, 10, 24, 12, 0)}, "NAIVE_DATETIME"),
    ({"envelope_version": 2}, "ENVELOPE_VERSION_UNSUPPORTED"),
])
def test_contract_violations_have_stable_codes(cambio, code):
    with pytest.raises(EnvelopeError) as e:
        _sobre(**cambio)
    assert e.value.code == code


def test_event_and_operation_identity_must_differ():
    mismo = new_uuid()
    with pytest.raises(EnvelopeError) as e:
        _sobre(event_id=mismo, operation_id=mismo)
    assert e.value.code == "IDENTITY_COLLISION"


def test_content_hash_ignores_transport_but_not_the_fact():
    sobre = _sobre()
    reenviado = _sobre(**{**_campos(sobre), "sequence_no": 99,
                          "workstation_id": new_uuid(), "correlation_id": new_uuid()})
    assert reenviado.content_hash == sobre.content_hash
    alterado = _sobre(**{**_campos(sobre), "payload": {"total": Decimal("1250.51")}})
    assert alterado.content_hash != sobre.content_hash


def _campos(sobre):
    return {k: getattr(sobre, k) for k in (
        "event_id", "operation_id", "event_type", "schema_version", "aggregate_type",
        "aggregate_id", "aggregate_version", "branch_id", "workstation_id", "sequence_no",
        "occurred_at", "payload", "actor_id")}


def test_tampered_envelope_is_detected_on_arrival():
    datos = json.loads(_sobre().to_json())
    datos["payload"]["total"] = "1.00"
    with pytest.raises(EnvelopeError) as e:
        ReplicationEnvelope.from_dict(datos)
    assert e.value.code == "CONTENT_HASH_MISMATCH"


@pytest.mark.parametrize("mutar,code", [
    (lambda d: d.pop("content_hash"), "MALFORMED"),
    (lambda d: d.update(envelope_version=9), "ENVELOPE_VERSION_UNSUPPORTED"),
    (lambda d: d.update(occurred_at="ayer"), "MALFORMED"),
])
def test_unreadable_envelopes_are_refused(mutar, code):
    datos = json.loads(_sobre().to_json())
    mutar(datos)
    with pytest.raises(EnvelopeError) as e:
        ReplicationEnvelope.from_dict(datos)
    assert e.value.code == code
    with pytest.raises(EnvelopeError) as e:
        ReplicationEnvelope.from_json("{no es json")
    assert e.value.code == "MALFORMED"


# ── desde el outbox real de un contexto ──────────────────────────────────────
def test_wraps_the_canonical_event_a_context_writes_to_its_outbox():
    branch, user, shift = new_uuid(), new_uuid(), new_uuid()
    evento = cash_event_payload(CashEvents.SHIFT_OPENED, operation_id=new_uuid(),
                                entity_id=shift, branch_id=branch, user_id=user,
                                opening_amount="500.00")
    estacion = new_uuid()
    sobre = envelope_from_outbox_event(
        json.loads(json.dumps(evento)), aggregate_type="cash_register.shift",
        aggregate_version=1, workstation_id=estacion, sequence_no=1)
    assert (sobre.event_id, sobre.aggregate_id, sobre.branch_id, sobre.actor_id) == (
        evento["event_id"], shift, branch, user)
    assert sobre.event_type == CashEvents.SHIFT_OPENED
    assert ReplicationEnvelope.from_json(sobre.to_json()) == sobre


def test_outbox_event_without_timezone_is_refused():
    evento = {"event_id": new_uuid(), "event_name": "SALE_COMPLETED",
              "operation_id": new_uuid(), "entity_id": new_uuid(), "branch_id": new_uuid(),
              "timestamp": "2026-10-24T12:00:00", "payload": {}}
    with pytest.raises(EnvelopeError) as e:
        envelope_from_outbox_event(evento, aggregate_type="sales.sale", aggregate_version=1,
                                   workstation_id=new_uuid(), sequence_no=1)
    assert e.value.code == "NAIVE_DATETIME"


# ── acuses ───────────────────────────────────────────────────────────────────
def test_only_accepted_and_duplicate_settle_an_envelope():
    assert {o for o in ReplicationOutcome if o.settles} == {
        ReplicationOutcome.ACCEPTED, ReplicationOutcome.DUPLICATE}


def test_ack_round_trip_and_failures_need_a_code():
    ack = ReplicationAck(event_id=new_uuid(), outcome="CONFLICT", error_code="EVENT_ID_REUSED",
                         conflict={"server_hash": "abc"})
    assert ReplicationAck.from_dict(ack.to_dict()) == ack
    for outcome in ("CONFLICT", "REJECTED", "RETRY"):
        with pytest.raises(EnvelopeError) as e:
            ReplicationAck(event_id=new_uuid(), outcome=outcome)
        assert e.value.code == "MALFORMED_ACK"
    with pytest.raises(EnvelopeError) as e:
        ReplicationAck.from_dict({"event_id": new_uuid(), "outcome": "QUIZAS"})
    assert e.value.code == "MALFORMED_ACK"
