"""§10/§26 — Procesamiento no libera calidad.

- Nada de Procesamiento CAMBIA el estado de calidad de un lote en Inventario
  (`SetLotQualityStatusUseCase` es de Calidad). Registrar el lote de una salida
  sí: lo hace Inventario, con el estado que dicta la configuración de Productos.
- Sólo `quality_use_cases` escribe una decisión en el output, y sólo la invoca
  el manejador de los eventos de Calidad; la ejecución no la importa.
- La ejecución nunca asigna `RELEASED` a un output.
"""
import ast

from tests.architecture._meat_processing_code import (
    ROOT,
    EXECUTION_MODULES,
    identifiers,
    imported_modules,
    production_files,
    rel,
    tree,
)

QUIEN_REGISTRA = {"backend/application/meat_processing/use_cases/quality_use_cases.py",
                  "backend/application/event_handlers/meat_processing/quality_decision_handler.py",
                  "backend/application/meat_processing/use_cases/__init__.py"}


def test_processing_never_changes_a_lot_quality_status():
    fugas = [rel(p) for p in production_files()
             if any(n in ("SetLotQualityStatusUseCase", "LotQualityProjection")
                    for _, n in identifiers(p))
             or any(m.endswith(("SetLotQualityStatusUseCase", "lot_quality_projection"))
                    for m in imported_modules(p))]
    assert fugas == []


def test_only_the_quality_callback_records_a_quality_decision():
    fugas = [rel(p) for p in production_files()
             if rel(p) not in QUIEN_REGISTRA
             and any(n == "RecordQualityDecisionUseCase" for _, n in identifiers(p))]
    assert fugas == []


def test_execution_never_marks_an_output_released():
    fugas = []
    for m in EXECUTION_MODULES:
        if m.endswith("quality_use_cases.py"):
            continue
        for n in ast.walk(tree(ROOT / m)):
            if isinstance(n, ast.Attribute) and n.attr == "RELEASED" and isinstance(
                    n.value, ast.Name) and n.value.id == "OutputQualityStatus":
                fugas.append((m, n.lineno))
    assert fugas == []
