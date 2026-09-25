"""§9/§26 — Procesamiento no usa la sucursal como ubicación ni como almacén: la
ubicación la resuelve Inventario (`StockLocationResolver`) o viene de la
reserva. Se revisa el ÁRBOL del programa: ninguna asignación ni argumento
`location_id`/`*_location_id`/`warehouse_id` toma un valor que sea una sucursal,
ni como respaldo (`x or branch_id`)."""
import ast

from tests.architecture._meat_processing_code import production_files, rel, tree

DESTINOS = ("location_id", "from_location_id", "to_location_id", "allocated_location_id")


def _menciona_sucursal(nodo) -> bool:
    for n in ast.walk(nodo):
        if isinstance(n, ast.Name) and n.id in ("branch_id", "sucursal_id", "branch"):
            return True
        if isinstance(n, ast.Attribute) and n.attr in ("branch_id", "_branch_id", "sucursal_id"):
            return True
    return False


def test_no_location_is_ever_taken_from_a_branch():
    fugas = []
    for p in production_files():
        for n in ast.walk(tree(p)):
            if isinstance(n, ast.keyword) and n.arg in DESTINOS and _menciona_sucursal(n.value):
                fugas.append((rel(p), n.value.lineno))
            if isinstance(n, ast.Assign):
                nombres = [t.id if isinstance(t, ast.Name) else getattr(t, "attr", "")
                           for t in n.targets]
                if any(x in DESTINOS for x in nombres) and _menciona_sucursal(n.value):
                    fugas.append((rel(p), n.lineno))
    assert fugas == []


def test_no_warehouse_is_ever_taken_from_a_branch():
    fugas = []
    for p in production_files():
        for n in ast.walk(tree(p)):
            if isinstance(n, ast.keyword) and n.arg == "warehouse_id" and isinstance(
                    n.value, ast.BoolOp) and _menciona_sucursal(n.value):
                fugas.append((rel(p), n.value.lineno))
    assert fugas == []
