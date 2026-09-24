"""Las sucursales asignadas de la sesión, leídas de un solo modo (Fase 10).

`ApplicationContext.assigned_branch_ids` se empezó a poblar el 2026-09-17,
pero los composition roots de Cárnico y Mermas seguían armando
`frozenset({branch})`: la asignación se escribía y nadie la leía. Medido el
2026-09-21 sobre copia de la base real: Corregidora tiene UN usuario, quien
crea una orden no la aprueba, y admin —asignado a la sucursal— era rechazado
con "Sucursal fuera del alcance del actor".
"""
from __future__ import annotations

from types import SimpleNamespace

from backend.application.security.session_branch_scope import assigned_branch_ids

PROPIA, OTRA = "suc-propia", "suc-otra"


def test_sin_asignaciones_manda_la_sucursal_propia():
    sesion = SimpleNamespace(assigned_branch_ids=frozenset())
    assert assigned_branch_ids(sesion, PROPIA) == {PROPIA}


def test_las_asignadas_se_suman_a_la_propia():
    sesion = SimpleNamespace(assigned_branch_ids=frozenset({OTRA}))
    assert assigned_branch_ids(sesion, PROPIA) == {PROPIA, OTRA}


def test_acepta_el_alias_en_espanol():
    sesion = SimpleNamespace(sucursales_asignadas=frozenset({OTRA}))
    assert assigned_branch_ids(sesion, PROPIA) == {PROPIA, OTRA}


def test_una_sesion_sin_el_atributo_no_revienta():
    assert assigned_branch_ids(SimpleNamespace(), PROPIA) == {PROPIA}


def test_ids_vacios_o_en_blanco_no_entran():
    sesion = SimpleNamespace(assigned_branch_ids=frozenset({"", "  ", OTRA}))
    assert assigned_branch_ids(sesion, PROPIA) == {PROPIA, OTRA}


def test_sin_sucursal_activa_solo_quedan_las_asignadas():
    sesion = SimpleNamespace(assigned_branch_ids=frozenset({OTRA}))
    assert assigned_branch_ids(sesion, "") == {OTRA}


def test_los_dos_contextos_de_ejecucion_lo_usan():
    """Trinquete: si un composition root vuelve a `frozenset({branch})`, el
    nivel «sucursales asignadas» del alcance se queda hueco otra vez."""
    import inspect

    from backend.infrastructure.desktop import losses_factory, meat_processing_factory

    for modulo in (losses_factory, meat_processing_factory):
        fuente = inspect.getsource(modulo)
        assert "assigned_branch_ids=frozenset({branch})" not in fuente, modulo.__name__
        assert "_assigned_branches(" in fuente, modulo.__name__
