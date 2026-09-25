"""§12/§26 — Procesamiento no calcula costos: no importa el repartidor de
Costos, no tiene servicio de reparto propio y no escribe costos en sus tablas.
Leer el costo que asignó Costos (registros, pantallas) sí se permite."""
import re

from tests.architecture._meat_processing_code import (
    ROOT,
    code_strings,
    imported_modules,
    production_files,
    rel,
)


def test_there_is_no_cost_allocation_service_in_processing():
    assert not (ROOT / "backend/domain/meat_processing/services/cost_allocation_service.py").exists()


def test_processing_does_not_import_the_costing_allocator():
    fugas = [rel(p) for p in production_files()
             if any(m.startswith("backend.domain.costing") for m in imported_modules(p))]
    assert fugas == []


def test_processing_never_writes_a_cost():
    escribe = re.compile(r"(INSERT INTO|UPDATE)\s+\w+.*\b(allocated_cost|unit_cost|input_unit_cost)\b",
                         re.I | re.S)
    fugas = [(rel(p), linea) for p in production_files() for linea, s in code_strings(p)
             if escribe.search(s)]
    assert fugas == []


def test_processing_results_have_no_cost_columns():
    from backend.infrastructure.db.schema import meat_processing_schema as esquema

    ddl = " ".join(esquema._DDL_OUTPUT_RESULTS)
    assert not re.search(r"\b(allocated_cost|unit_cost|input_unit_cost|unit_price)\b", ddl)
