"""SET-8 — PrintRoute entity + PrintRoutingPolicy (routing/failover,
§25). Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.device_management.entities.print_route import PrintRoute
from backend.domain.device_management.exceptions import (
    DeviceInvalidValueError,
    NoAvailablePrinterError,
    PrintRouteNotFoundError,
)
from backend.domain.device_management.policies.print_routing_policy import resolve_route, select_device
from backend.shared.ids import is_uuidv7, new_uuid


def _route(**overrides) -> PrintRoute:
    kwargs = dict(document_type="sale_ticket", primary_device_id=new_uuid())
    kwargs.update(overrides)
    return PrintRoute.create(**kwargs)


class TestCreate:
    def test_mints_uuidv7_and_normalizes_document_type(self):
        route = _route(document_type="sale_ticket")
        assert is_uuidv7(route.id)
        assert route.document_type == "SALE_TICKET"

    def test_requires_document_type(self):
        with pytest.raises(DeviceInvalidValueError):
            _route(document_type="   ")

    def test_requires_valid_primary_device_id(self):
        with pytest.raises(ValueError):
            _route(primary_device_id="not-a-uuid")

    def test_primary_cannot_appear_in_fallback_chain(self):
        device_id = new_uuid()
        with pytest.raises(DeviceInvalidValueError):
            _route(primary_device_id=device_id, fallback_device_ids=(device_id,))

    def test_fallback_chain_deduplicates(self):
        fallback_id = new_uuid()
        route = _route(fallback_device_ids=(fallback_id, fallback_id))
        assert route.fallback_device_ids == (fallback_id,)

    def test_optional_scope_fields_validated_as_uuid_when_present(self):
        with pytest.raises(ValueError):
            _route(branch_id="not-a-uuid")
        with pytest.raises(ValueError):
            _route(workstation_id="not-a-uuid")


class TestSpecificityAndMatching:
    def test_global_route_has_zero_specificity(self):
        assert _route().specificity() == 0

    def test_specificity_counts_set_scope_dimensions(self):
        route = _route(branch_id=new_uuid(), module="orders")
        assert route.specificity() == 2

    def test_matches_requires_same_document_type(self):
        route = _route(document_type="sale_ticket")
        assert route.matches("SALE_TICKET")
        assert not route.matches("LABEL")

    def test_inactive_route_never_matches(self):
        route = _route()
        route.deactivate()
        assert not route.matches("SALE_TICKET")

    def test_scoped_route_only_matches_its_exact_scope(self):
        branch_id = new_uuid()
        route = _route(branch_id=branch_id)
        assert route.matches("SALE_TICKET", branch_id=branch_id)
        assert not route.matches("SALE_TICKET", branch_id=new_uuid())
        assert not route.matches("SALE_TICKET", branch_id=None)

    def test_unscoped_route_matches_any_context(self):
        route = _route()
        assert route.matches("SALE_TICKET", branch_id=new_uuid(), workstation_id=new_uuid())


class TestMutators:
    def test_set_primary_device_rejects_value_already_in_fallback(self):
        fallback_id = new_uuid()
        route = _route(fallback_device_ids=(fallback_id,))
        with pytest.raises(DeviceInvalidValueError):
            route.set_primary_device(fallback_id)

    def test_set_fallback_chain_rejects_primary(self):
        route = _route()
        with pytest.raises(DeviceInvalidValueError):
            route.set_fallback_chain((route.primary_device_id,))

    def test_activate_deactivate(self):
        route = _route()
        route.deactivate()
        assert route.active is False
        route.activate()
        assert route.active is True


class TestResolveRoute:
    def test_most_specific_route_wins(self):
        branch_id = new_uuid()
        global_route = _route()
        branch_route = _route(branch_id=branch_id)
        resolved = resolve_route("SALE_TICKET", [global_route, branch_route], branch_id=branch_id)
        assert resolved.id == branch_route.id

    def test_falls_back_to_global_route_outside_scope(self):
        branch_id = new_uuid()
        global_route = _route()
        branch_route = _route(branch_id=branch_id)
        resolved = resolve_route("SALE_TICKET", [global_route, branch_route], branch_id=new_uuid())
        assert resolved.id == global_route.id

    def test_raises_when_nothing_matches(self):
        with pytest.raises(PrintRouteNotFoundError):
            resolve_route("SALE_TICKET", [], branch_id=None)

    def test_inactive_candidates_are_ignored(self):
        route = _route()
        route.deactivate()
        with pytest.raises(PrintRouteNotFoundError):
            resolve_route("SALE_TICKET", [route])


class TestSelectDevice:
    def test_primary_selected_when_available(self):
        route = _route()
        selection = select_device(route, is_available=lambda device_id: True)
        assert selection.device_id == route.primary_device_id
        assert selection.used_failover is False
        assert selection.attempted_device_ids == (route.primary_device_id,)

    def test_falls_over_to_first_available_fallback(self):
        fallback_1, fallback_2 = new_uuid(), new_uuid()
        route = _route(fallback_device_ids=(fallback_1, fallback_2))
        selection = select_device(route, is_available=lambda device_id: device_id == fallback_2)
        assert selection.device_id == fallback_2
        assert selection.used_failover is True
        assert selection.attempted_device_ids == (route.primary_device_id, fallback_1, fallback_2)

    def test_raises_when_nothing_in_the_chain_is_available(self):
        route = _route(fallback_device_ids=(new_uuid(),))
        with pytest.raises(NoAvailablePrinterError):
            select_device(route, is_available=lambda device_id: False)
