"""DeliveryZonePolicy, sin base de datos.

Los casos de uso ya le pasan sólo las OTRAS zonas ACTIVAS de la MISMA sucursal, así
que sus pruebas nunca ejercitan los filtros de la política. Pero esos filtros son el
contrato: una zona inactiva no resuelve domicilios y no bloquea códigos, otra
sucursal no comparte resolución, y una zona no choca consigo misma. Se fijan aquí,
dándole a la política listas mezcladas a propósito.
"""
from __future__ import annotations

import pytest

from backend.domain.orders_delivery.delivery_zone import DeliveryZone
from backend.domain.orders_delivery.exceptions import DeliveryZoneOverlapError
from backend.domain.orders_delivery.policies.delivery_zone_policy import DeliveryZonePolicy
from backend.shared.ids import new_uuid

SUCURSAL = new_uuid()


def _zona(nombre, *codigos, branch_id=SUCURSAL, activa=True):
    zona = DeliveryZone.create(branch_id=branch_id, name=nombre, postal_codes=codigos)
    if not activa:
        zona.deactivate()
    return zona


def test_an_active_zone_of_the_same_branch_sharing_a_code_is_an_overlap():
    with pytest.raises(DeliveryZoneOverlapError, match="06010.*Centro"):
        DeliveryZonePolicy.ensure_no_overlap(
            _zona("Nueva", "06010"), [_zona("Centro", "06000", "06010")])


def test_an_inactive_zone_is_ignored_even_if_the_caller_passes_it():
    DeliveryZonePolicy.ensure_no_overlap(
        _zona("Nueva", "06000"), [_zona("Vieja", "06000", activa=False)])


def test_a_zone_of_another_branch_is_ignored_even_if_the_caller_passes_it():
    DeliveryZonePolicy.ensure_no_overlap(
        _zona("Nueva", "06000"), [_zona("Ajena", "06000", branch_id=new_uuid())])


def test_a_zone_never_overlaps_with_itself():
    zona = _zona("Centro", "06000")

    DeliveryZonePolicy.ensure_no_overlap(zona, [zona])


def test_the_message_lists_every_clash_in_a_stable_order():
    with pytest.raises(DeliveryZoneOverlapError) as error:
        DeliveryZonePolicy.ensure_no_overlap(
            _zona("Nueva", "06000", "06700", "06010"),
            [_zona("Roma", "06700"), _zona("centro", "06010", "06000")])

    assert str(error.value).endswith("06000, 06010 (zona «centro»); 06700 (zona «Roma»)")


@pytest.mark.parametrize("crudo, esperado", [
    (" 06000, 06010 ,06000,, ", ("06000", "06010")),
    ("06000;06010\n06020", ("06000", "06010", "06020")),
    (["06000", " 06000 ", ""], ("06000",)),
    (None, ()),
])
def test_postal_codes_are_normalized(crudo, esperado):
    assert DeliveryZonePolicy.normalize_postal_codes(crudo) == esperado
