"""P2 guardrail — the dead top-level legacy InventoryRepository stays retired.

``repositories/inventory_repository.py`` (int product/branch IDs; wrote
``movimientos_inventario`` / ``inventario_actual`` / ``branch_inventory``) had zero
production importers — ``core/app_container.py`` and every real caller use the
canonical-adjacent ``backend.infrastructure.db.repositories.inventory_repository``
instead, and the ``InventoryService`` shim (INV-27) ignores the legacy repo
parameter entirely, delegating to ``CanonicalInventoryRepository``. It was only
constructed (inertly) by two test fixtures. This guardrail keeps it from coming
back and removes another blocker from the ``movimientos_inventario`` DROP list.
"""

from pathlib import Path
from tests.architecture.architecture_guardrails import APP_ROOT

ROOT = APP_ROOT


def test_legacy_top_level_inventory_repository_file_is_removed():
    assert not (ROOT / "repositories/inventory_repository.py").exists()


def test_nothing_imports_the_legacy_top_level_inventory_repository():
    # Match real import statements only (line starts with "from ..."), so guardrail
    # files that embed the forbidden import as a string literal (to assert its
    # absence elsewhere) don't self-flag.
    offenders = []
    for folder in ("backend", "core", "frontend", "interfaz", "modulos", "tests",
                   "repositories", "services", "integrations", "application"):
        base = ROOT / folder
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            for line in path.read_text(errors="ignore").splitlines():
                if line.strip().startswith(
                        "from repositories.inventory_repository import"):
                    offenders.append(str(path))
                    break
    assert offenders == []


def test_app_container_uses_only_the_canonical_adjacent_module():
    src = (ROOT / "core/app_container.py").read_text(errors="ignore")
    assert ("from backend.infrastructure.db.repositories.inventory_repository "
            "import InventoryRepository") in src
    assert "from repositories.inventory_repository import" not in src
