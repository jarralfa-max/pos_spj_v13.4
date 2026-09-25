"""§2/§26 — la ejecución lee SÓLO la definición congelada. Ningún módulo de la
ejecución importa repositorios, casos de uso ni consultas de Productos. Leer
Productos es de la preparación (`products_recipe_snapshot_adapter`), una vez."""
from tests.architecture._meat_processing_code import ROOT, EXECUTION_MODULES, imported_modules

PROHIBIDO = ("backend.infrastructure.db.repositories.products",
             "backend.application.products",
             "backend.application.meat_processing.integrations.products_recipe_snapshot_adapter")


def test_execution_modules_exist():
    assert all((ROOT / m).exists() for m in EXECUTION_MODULES)


def test_execution_never_imports_products():
    fugas = [(m, i) for m in EXECUTION_MODULES for i in imported_modules(ROOT / m)
             if i.startswith(PROHIBIDO)]
    assert fugas == []
