"""§15/§23/§26 — en tiempo de ejecución nada de Procesamiento ni de sus
integraciones se autoriza con `permissive_for_tests()`.

- Las raíces de composición (fábrica de escritorio, puertos de ejecución,
  adaptadores, manejadores, concesiones) no lo mencionan.
- Todo caso de uso que construye la fábrica recibe su política explícita.
- Los casos de uso de otros contextos que invocan los adaptadores exigen una
  política (no tienen una permisiva por omisión).
"""
import ast

from tests.architecture._meat_processing_code import ROOT, code_strings, identifiers, rel, tree

COMPOSICION = (
    "backend/infrastructure/desktop/meat_processing_factory.py",
    "backend/infrastructure/integrations/meat_processing_ports.py",
    "backend/infrastructure/integrations/meat_processing_execution_ports.py",
    "backend/application/event_handlers/meat_processing/quality_decision_handler.py",
    "backend/application/meat_processing/integration_grants.py",
    "backend/application/inventory/integration_grants.py",
    "backend/application/costing/processing_costing.py",
    "backend/application/costing/wiring.py",
    "backend/application/quality/output_inspection.py",
    "backend/application/quality/wiring.py",
    "backend/application/losses/yield_variance_case.py",
)


def test_composition_roots_never_mention_the_permissive_policy():
    fugas = [m for m in COMPOSICION
             if any(n == "permissive_for_tests" for _, n in identifiers(ROOT / m))]
    assert fugas == []


def test_every_use_case_built_by_the_factory_gets_an_explicit_policy():
    fabrica = ROOT / "backend/infrastructure/desktop/meat_processing_factory.py"
    sin_politica = []
    for n in ast.walk(tree(fabrica)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and \
                n.func.id.endswith("UseCase") and not n.args and not any(
                    k.arg == "authorization" for k in n.keywords):
            sin_politica.append((n.func.id, n.lineno))
    assert sin_politica == []


def test_cross_context_use_cases_require_an_explicit_policy():
    """Sin política no arrancan: reventar es mejor que conceder todo."""
    import pytest

    from backend.application.costing.processing_costing import AllocateProductionCostUseCase
    from backend.application.inventory.use_cases.production_reservation_use_cases import (
        ReserveStockForProductionUseCase,
    )
    from backend.application.losses.yield_variance_case import (
        RequestYieldVarianceLossCaseUseCase,
    )
    from backend.application.quality.output_inspection import (
        DecideOutputInspectionUseCase,
        RequestOutputInspectionUseCase,
    )

    for caso in (AllocateProductionCostUseCase, ReserveStockForProductionUseCase,
                 RequestYieldVarianceLossCaseUseCase, DecideOutputInspectionUseCase,
                 RequestOutputInspectionUseCase):
        with pytest.raises((ValueError, TypeError)):
            caso(None)


def test_the_word_does_not_hide_in_strings_either():
    fugas = [(m, l) for m in COMPOSICION for l, s in code_strings(ROOT / m)
             if "permissive_for_tests" in s]
    assert fugas == []
