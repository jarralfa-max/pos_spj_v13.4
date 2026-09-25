"""§14/§26 — ninguna identidad ni `operation_id` se arma concatenando cadenas
(`f"{orden}:consumo:{producto}"`): siempre es un UUIDv7 propio (`new_uuid()`),
persistido antes de llamar a otro contexto cuando hay que reintentar."""
import ast

from tests.architecture._meat_processing_code import ROOT, production_files, rel, tree

EXTRA = ("backend/application/costing", "backend/application/quality",
         "backend/application/losses/yield_variance_case.py",
         "backend/application/inventory/use_cases/production_reservation_use_cases.py",
         "backend/application/inventory/services/lot_quality_projection.py")

IDENTIDADES = ("operation_id", "event_id", "entity_id", "reservation_id", "lot_id", "id")


def _archivos():
    extra = []
    for e in EXTRA:
        ruta = ROOT / e
        extra += sorted(ruta.rglob("*.py")) if ruta.is_dir() else [ruta]
    return production_files() + [p for p in extra if "__pycache__" not in p.parts]


def _armada(valor) -> bool:
    return isinstance(valor, ast.JoinedStr) or (
        isinstance(valor, ast.BinOp) and isinstance(valor.op, ast.Add)
        and any(isinstance(x, ast.Constant) and isinstance(x.value, str)
                for x in (valor.left, valor.right)))


def test_identities_are_never_built_from_strings():
    fugas = []
    for p in _archivos():
        for n in ast.walk(tree(p)):
            if isinstance(n, ast.keyword) and n.arg in IDENTIDADES and _armada(n.value):
                fugas.append((rel(p), n.value.lineno, n.arg))
            if isinstance(n, ast.Assign) and _armada(n.value):
                for t in n.targets:
                    nombre = t.id if isinstance(t, ast.Name) else getattr(t, "attr", "")
                    if nombre in IDENTIDADES:
                        fugas.append((rel(p), n.lineno, nombre))
    assert fugas == []
