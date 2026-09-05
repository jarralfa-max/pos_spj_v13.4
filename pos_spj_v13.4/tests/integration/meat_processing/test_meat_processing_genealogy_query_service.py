"""PROC-18 e2e (§38): ChainOutputAsConsumptionUseCase records a genealogy
link for every output→consumption chain, and ProcessGenealogyQueryService
traces upstream/downstream/recall over those links."""

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.queries import ProcessGenealogyQueryService
from backend.application.meat_processing.use_cases import (
    ApproveProcessingOrderUseCase,
    CaptureProcessOutputUseCase,
    ChainOutputAsConsumptionUseCase,
    CreateProcessingOrderUseCase,
)
from backend.domain.meat_processing.enums import OutputType, ProcessType
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.187_meat_processing_bounded_context_schema").run(c)
    importlib.import_module(
        "migrations.standalone.251_meat_processing_genealogy_schema").run(c)
    yield c
    c.close()


def _approved_order(conn, process_type=ProcessType.CUTTING):
    created = CreateProcessingOrderUseCase().execute(
        conn, operation_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
        process_type=process_type, target_product_id=new_uuid(),
        planned_quantity=Decimal("10"), planned_weight=Decimal("10"),
        actor_user_id=new_uuid())
    ApproveProcessingOrderUseCase().execute(
        conn, order_id=created.entity_id, operation_id=new_uuid(), actor_user_id=new_uuid())
    return created.entity_id


def _output(conn, order_id, output_type=OutputType.SEMI_FINISHED):
    captured = CaptureProcessOutputUseCase().execute(
        conn, order_id=order_id, operation_id=new_uuid(), product_id=new_uuid(),
        output_type=output_type, quantity=Decimal("5"), weight=Decimal("5"),
        actor_user_id=new_uuid())
    return captured.entity_id


def _chain(conn, upstream_output_id, downstream_order_id):
    result = ChainOutputAsConsumptionUseCase().execute(
        conn, upstream_output_id=upstream_output_id, downstream_order_id=downstream_order_id,
        operation_id=new_uuid(), actor_user_id=new_uuid())
    assert result.success
    with MeatProcessingUnitOfWork(conn) as uow:
        consumption = uow.consumptions.get(result.entity_id)
    return consumption.id


class TestChainRecordsGenealogyLink:
    def test_link_is_saved_with_correct_direction(self, conn):
        order_a = _approved_order(conn)
        output_a = _output(conn, order_a)
        order_b = _approved_order(conn, ProcessType.MIXING)
        consumption_id = _chain(conn, output_a, order_b)

        service = ProcessGenealogyQueryService(conn)
        downstream = service.get_downstream_links("ProcessOutput", output_a)
        assert len(downstream) == 1
        assert downstream[0].downstream_entity_type == "MaterialConsumption"
        assert downstream[0].downstream_entity_id == consumption_id

        upstream = service.get_upstream_links("MaterialConsumption", consumption_id)
        assert len(upstream) == 1
        assert upstream[0].upstream_entity_type == "ProcessOutput"
        assert upstream[0].upstream_entity_id == output_a


class TestTraceMultiHop:
    """Links only connect *across* orders (§38: within one order, consumption
    and output already share processing_order_id — no link is recorded for
    that, see ProcessGenealogyLink's own docstring). So a chain of two
    ChainOutputAsConsumptionUseCase calls produces two independent one-hop
    links, not a single two-hop path, unless the second chain call reuses the
    same entity on both ends."""

    def test_trace_downstream_stops_at_the_consumption_it_produced(self, conn):
        order_a = _approved_order(conn)
        output_a = _output(conn, order_a)
        order_b = _approved_order(conn, ProcessType.MIXING)
        consumption_id = _chain(conn, output_a, order_b)

        service = ProcessGenealogyQueryService(conn)
        links = service.trace_downstream("ProcessOutput", output_a)
        assert len(links) == 1
        assert links[0].downstream_entity_type == "MaterialConsumption"
        assert links[0].downstream_entity_id == consumption_id

    def test_trace_upstream_chains_across_orders_when_the_same_output_is_reused(self, conn):
        # output_a is chained into both order_b's consumption AND (reused
        # directly, no new order in between) order_c's consumption — trace
        # from order_c's consumption should surface both hops when a second
        # link shares output_a as its upstream node.
        order_a = _approved_order(conn)
        output_a = _output(conn, order_a)
        order_b = _approved_order(conn, ProcessType.MIXING)
        consumption_b = _chain(conn, output_a, order_b)
        order_c = _approved_order(conn, ProcessType.PACKAGING)
        consumption_c = _chain(conn, output_a, order_c)

        service = ProcessGenealogyQueryService(conn)
        links = service.trace_upstream("MaterialConsumption", consumption_c)
        assert len(links) == 1
        assert links[0].upstream_entity_id == output_a
        assert links[0].downstream_entity_id == consumption_c
        assert links[0].downstream_entity_id != consumption_b

    def test_no_links_returns_empty(self, conn):
        service = ProcessGenealogyQueryService(conn)
        assert service.trace_downstream("ProcessOutput", new_uuid()) == []
        assert service.trace_upstream("ProcessOutput", new_uuid()) == []


class TestRecall:
    def test_trace_lot_downstream_finds_everything_from_that_lot(self, conn):
        order_a = _approved_order(conn)
        captured = CaptureProcessOutputUseCase().execute(
            conn, order_id=order_a, operation_id=new_uuid(), product_id=new_uuid(),
            output_type=OutputType.SEMI_FINISHED, quantity=Decimal("5"), weight=Decimal("5"),
            actor_user_id=new_uuid(), lot_id=new_uuid())
        output_a = captured.entity_id
        with MeatProcessingUnitOfWork(conn) as uow:
            lot_id = uow.outputs.get(output_a).lot_id
        order_b = _approved_order(conn, ProcessType.MIXING)
        consumption_id = _chain(conn, output_a, order_b)

        service = ProcessGenealogyQueryService(conn)
        links = service.trace_lot_downstream(lot_id)
        assert len(links) == 1
        assert links[0].downstream_entity_id == consumption_id

    def test_trace_lot_downstream_no_lot_returns_empty(self, conn):
        service = ProcessGenealogyQueryService(conn)
        assert service.trace_lot_downstream(new_uuid()) == []
