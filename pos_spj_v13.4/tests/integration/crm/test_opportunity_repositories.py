"""CRM-5 — Opportunity/CRMStageDefinition/OpportunityStageHistory/
OpportunityProductInterest repository round-trips + seeded pipeline."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.crm.entities.opportunity import Opportunity
from backend.domain.crm.entities.opportunity_product_interest import OpportunityProductInterest
from backend.domain.crm.entities.opportunity_stage_history import OpportunityStageHistory
from backend.domain.crm.entities.stage_definition import CRMStageDefinition
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


def _stage(uow, code="CUSTOM_STAGE", sequence_order=99, **kwargs) -> CRMStageDefinition:
    stage = CRMStageDefinition.create(code, code.title(), sequence_order, **kwargs)
    uow.stage_definitions.save(stage)
    return stage


def _opportunity(uow, stage_id, **kwargs) -> Opportunity:
    return Opportunity.create(
        uow.opportunities.next_code(), kwargs.pop("customer_id", "cust-1"),
        kwargs.pop("name", "Venta anual"), stage_id, created_by_user_id="u1", **kwargs)


class TestCRMStageDefinitionRepository:
    def test_default_pipeline_is_seeded_by_migration(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            stages = uow.stage_definitions.list_active_ordered()
        codes = [s.code for s in stages]
        assert codes == [
            "PROSPECTING", "QUALIFICATION", "PROPOSAL", "NEGOTIATION",
            "CLOSED_WON", "CLOSED_LOST",
        ]

    def test_get_default_initial_stage_skips_terminal_stages(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            stage = uow.stage_definitions.get_default_initial_stage()
        assert stage.code == "PROSPECTING"

    def test_get_won_and_lost_stage(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            won = uow.stage_definitions.get_won_stage()
            lost = uow.stage_definitions.get_lost_stage()
        assert won.code == "CLOSED_WON"
        assert lost.code == "CLOSED_LOST"

    def test_save_and_get_custom_stage_with_required_fields(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            stage = _stage(uow, required_fields=("amount", "expected_close_date"),
                           min_activities=2)
        with CRMUnitOfWork(crm_conn) as uow2:
            fetched = uow2.stage_definitions.get(stage.id)
            assert fetched.required_fields == ("amount", "expected_close_date")
            assert fetched.min_activities == 2

    def test_get_by_code_is_case_insensitive_on_lookup(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            fetched = uow.stage_definitions.get_by_code("prospecting")
        assert fetched is not None and fetched.code == "PROSPECTING"

    def test_deactivated_stage_excluded_from_active_ordered(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            stage = _stage(uow)
            stage.deactivate()
            uow.stage_definitions.update(stage)
        with CRMUnitOfWork(crm_conn) as uow2:
            codes = [s.code for s in uow2.stage_definitions.list_active_ordered()]
        assert stage.code not in codes


class TestOpportunityRepository:
    def test_save_and_get(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            stage = uow.stage_definitions.get_default_initial_stage()
            opp = _opportunity(uow, stage.id, operation_id="op-1")
            uow.opportunities.save(opp, operation_id="op-1")
        with CRMUnitOfWork(crm_conn) as uow2:
            fetched = uow2.opportunities.get(opp.id)
            assert fetched.name == "Venta anual"
            assert fetched.status.value == "OPEN"
            assert fetched.stage_id == stage.id

    def test_next_code_increments(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            stage = uow.stage_definitions.get_default_initial_stage()
            o1 = _opportunity(uow, stage.id, operation_id="op-1")
            uow.opportunities.save(o1, operation_id="op-1")
        with CRMUnitOfWork(crm_conn) as uow2:
            o2 = _opportunity(uow2, stage.id, operation_id="op-2")
            uow2.opportunities.save(o2, operation_id="op-2")
        assert str(o1.code) == "OPP-000001"
        assert str(o2.code) == "OPP-000002"

    def test_get_by_operation_id_is_idempotency_lookup(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            stage = uow.stage_definitions.get_default_initial_stage()
            opp = _opportunity(uow, stage.id, operation_id="op-dup")
            uow.opportunities.save(opp, operation_id="op-dup")
        with CRMUnitOfWork(crm_conn) as uow2:
            found = uow2.opportunities.get_by_operation_id("op-dup")
            assert found is not None and found.id == opp.id

    def test_decimal_and_date_round_trip(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            stage = uow.stage_definitions.get_default_initial_stage()
            opp = _opportunity(uow, stage.id, operation_id="op-1", amount="25000.75",
                               expected_close_date=date(2026, 11, 15))
            uow.opportunities.save(opp, operation_id="op-1")
        with CRMUnitOfWork(crm_conn) as uow2:
            fetched = uow2.opportunities.get(opp.id)
            assert fetched.amount == Decimal("25000.75")
            assert fetched.expected_close_date == date(2026, 11, 15)

    def test_update_persists_stage_and_status(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            stage = uow.stage_definitions.get_default_initial_stage()
            opp = _opportunity(uow, stage.id, operation_id="op-1")
            uow.opportunities.save(opp, operation_id="op-1")
        with CRMUnitOfWork(crm_conn) as uow2:
            opp = uow2.opportunities.get(opp.id)
            opp.cancel("cliente se retractó")
            uow2.opportunities.update(opp)
        with CRMUnitOfWork(crm_conn) as uow3:
            reloaded = uow3.opportunities.get(opp.id)
            assert reloaded.status.value == "CANCELLED"
            assert reloaded.close_reason == "cliente se retractó"

    def test_list_owned_by_filters_by_owner(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            stage = uow.stage_definitions.get_default_initial_stage()
            mine = _opportunity(uow, stage.id, name="Mia", operation_id="op-1",
                                owner_user_id="u1")
            uow.opportunities.save(mine, operation_id="op-1")
            other = _opportunity(uow, stage.id, name="Ajena", operation_id="op-2",
                                 owner_user_id="u2")
            uow.opportunities.save(other, operation_id="op-2")
        with CRMUnitOfWork(crm_conn) as uow2:
            results = uow2.opportunities.list_owned_by(("u1",))
            assert [o.id for o in results] == [mine.id]

    def test_list_open_owned_by_excludes_closed(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            stage = uow.stage_definitions.get_default_initial_stage()
            open_opp = _opportunity(uow, stage.id, name="Abierta", operation_id="op-1",
                                    owner_user_id="u1")
            uow.opportunities.save(open_opp, operation_id="op-1")
            won_opp = _opportunity(uow, stage.id, name="Ganada", operation_id="op-2",
                                   owner_user_id="u1")
            uow.opportunities.save(won_opp, operation_id="op-2")
            won_opp.win()
            uow.opportunities.update(won_opp)
        with CRMUnitOfWork(crm_conn) as uow2:
            results = uow2.opportunities.list_open_owned_by(("u1",))
            assert [o.id for o in results] == [open_opp.id]

    def test_rollback_on_exception_discards_all_writes(self, crm_conn):
        try:
            with CRMUnitOfWork(crm_conn) as uow:
                stage = uow.stage_definitions.get_default_initial_stage()
                opp = _opportunity(uow, stage.id, operation_id="op-1")
                uow.opportunities.save(opp, operation_id="op-1")
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        count = crm_conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
        assert count == 0


class TestOpportunityStageHistoryRepository:
    def test_save_and_list_for_opportunity_ordered(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            stage = uow.stage_definitions.get_default_initial_stage()
            opp = _opportunity(uow, stage.id, operation_id="op-1")
            uow.opportunities.save(opp, operation_id="op-1")
            h1 = OpportunityStageHistory.create(opp.id, stage.id, "u1")
            uow.stage_history.save(h1)
        with CRMUnitOfWork(crm_conn) as uow2:
            history = uow2.stage_history.list_for_opportunity(opp.id)
            assert len(history) == 1
            assert history[0].from_stage_id is None
            assert history[0].to_stage_id == stage.id


class TestOpportunityProductInterestRepository:
    def test_save_and_list_for_opportunity(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            stage = uow.stage_definitions.get_default_initial_stage()
            opp = _opportunity(uow, stage.id, operation_id="op-1")
            uow.opportunities.save(opp, operation_id="op-1")
            interest = OpportunityProductInterest.create(
                opp.id, "Barra energética 24pz", quantity="10", estimated_unit_price="120.00")
            uow.product_interests.save(interest)
        with CRMUnitOfWork(crm_conn) as uow2:
            interests = uow2.product_interests.list_for_opportunity(opp.id)
            assert len(interests) == 1
            assert interests[0].quantity == Decimal("10")
            assert interests[0].estimated_unit_price == Decimal("120.00")
