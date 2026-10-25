"""Dominio de la estructura organizacional (auditoría enterprise, Fase 1)."""

from __future__ import annotations

import pytest

from backend.domain.organization.org_unit import (
    SUGGESTED_CAPABILITIES,
    Capability,
    OrgUnit,
    OrgUnitError,
    OrgUnitStatus,
    OrgUnitType,
    check_capabilities,
    suggest_code,
)

EMPRESA = "01a00000-0000-7000-8000-0000000000e1"


def _unidad(tipo=OrgUnitType.RETAIL_BRANCH, code="CENTRO", parent=None, **kw):
    return OrgUnit.create(company_id=kw.pop("company_id", EMPRESA), unit_type=tipo,
                          code=code, name=kw.pop("name", code.title()), parent=parent, **kw)


def test_code_is_normalized_and_validated():
    assert _unidad(code=" norte-1 ").code == "NORTE-1"
    for malo in ("", "A", "con espacio", "X" * 25):
        with pytest.raises(OrgUnitError):
            _unidad(code=malo)


def test_only_operating_sites_have_a_site_row():
    assert OrgUnitType.PRODUCTION_PLANT.is_operating_site
    assert OrgUnitType.WAREHOUSE.is_operating_site
    assert not OrgUnitType.REGION.is_operating_site


def test_hierarchy_rules():
    region = _unidad(OrgUnitType.REGION, "BAJIO")
    planta = _unidad(OrgUnitType.PRODUCTION_PLANT, "PLANTA", parent=region)
    assert planta.parent_id == region.id
    # Un almacén puede pertenecer a una planta; una sucursal no.
    assert _unidad(OrgUnitType.WAREHOUSE, "ALM-P", parent=planta).parent_id == planta.id
    with pytest.raises(OrgUnitError, match="no puede depender"):
        _unidad(OrgUnitType.RETAIL_BRANCH, "SUC", parent=planta)
    with pytest.raises(OrgUnitError, match="otra empresa"):
        _unidad(OrgUnitType.RETAIL_BRANCH, "SUC", parent=region,
                company_id="01a00000-0000-7000-8000-0000000000e2")


def test_inactive_parent_receives_no_children():
    region = _unidad(OrgUnitType.REGION, "BAJIO")
    region.deactivate(active_children=0)
    with pytest.raises(OrgUnitError, match="no está activa"):
        _unidad(OrgUnitType.RETAIL_BRANCH, "SUC", parent=region)


def test_move_rejects_cycles():
    a = _unidad(OrgUnitType.REGION, "RA")
    b = _unidad(OrgUnitType.REGION, "RB", parent=a)
    with pytest.raises(OrgUnitError, match="ciclo"):
        a.move_under(b, ancestors_of_parent={a.id})
    with pytest.raises(OrgUnitError, match="ciclo"):
        a.move_under(a, ancestors_of_parent=set())
    b.move_under(None, ancestors_of_parent=set())
    assert b.parent_id is None


def test_lifecycle():
    u = _unidad()
    with pytest.raises(OrgUnitError, match="dependiente"):
        u.deactivate(active_children=1)
    u.deactivate(active_children=0)
    assert u.status is OrgUnitStatus.INACTIVE
    u.reactivate()
    with pytest.raises(OrgUnitError, match="dependiente"):
        u.close(active_children=2)
    u.close(active_children=0)
    assert u.status is OrgUnitStatus.CLOSED and u.closed_at
    for accion in (lambda: u.reactivate(), lambda: u.rename(name="X"),
                   lambda: u.deactivate(active_children=0)):
        with pytest.raises(OrgUnitError):
            accion()


def test_capability_rules():
    for tipo, caps in SUGGESTED_CAPABILITIES.items():
        check_capabilities(tipo, caps)   # las sugerencias son válidas
    with pytest.raises(OrgUnitError, match="no opera"):
        check_capabilities(OrgUnitType.REGION, frozenset({Capability.POS}))
    with pytest.raises(OrgUnitError, match="POS requiere"):
        check_capabilities(OrgUnitType.RETAIL_BRANCH, frozenset({Capability.POS,
                                                                  Capability.SALES}))
    # La planta no vende por sugerencia: lo que rige es lo guardado, no el tipo.
    assert Capability.SALES not in SUGGESTED_CAPABILITIES[OrgUnitType.PRODUCTION_PLANT]
    check_capabilities(OrgUnitType.PRODUCTION_PLANT, frozenset({
        Capability.SALES, Capability.CASH, Capability.POS, Capability.PRODUCTION}))


def test_suggest_code():
    assert suggest_code("Corregidora", set()) == "CORREGIDORA"
    assert suggest_code("Planta Querétaro Norte", set()) == "PLANTA-QUERETARO-NOR"
    assert suggest_code("Centro", {"CENTRO"}) == "CENTRO-2"
    assert suggest_code("", set()) == "UNIDAD"
