"""Architecture tests: waste module must comply with REGLA CERO (UUIDv7 identity).

These tests protect against regressions after the int-cast removal in the
waste pipeline (merma.py, waste_application_service.py, waste_repository.py).
"""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]

MERMA_UI = PACKAGE_ROOT / "modulos" / "merma.py"
WASTE_SERVICE = PACKAGE_ROOT / "backend" / "application" / "services" / "waste_application_service.py"
WASTE_REPO = PACKAGE_ROOT / "backend" / "infrastructure" / "db" / "repositories" / "waste_repository.py"
WASTE_COMMAND = PACKAGE_ROOT / "backend" / "application" / "commands" / "waste_commands.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


# ── UI layer ──────────────────────────────────────────────────────────────────

def test_merma_ui_does_not_cast_product_id_to_int():
    """merma.py must not use int(product_id) — REGLA CERO."""
    src = _read(MERMA_UI)
    assert "int(product_id)" not in src, (
        "merma.py casts product_id to int — violates REGLA CERO"
    )


def test_merma_ui_does_not_cast_sucursal_id_to_int_in_stock_query():
    """merma.py must not use int(self.sucursal_id) when querying stock."""
    src = _read(MERMA_UI)
    assert "int(self.sucursal_id)" not in src, (
        "merma.py casts sucursal_id to int — violates REGLA CERO"
    )


def test_merma_ui_uses_new_uuid_not_uuid4():
    """merma.py must use new_uuid() from backend.shared.ids, not uuid.uuid4()."""
    src = _read(MERMA_UI)
    assert "uuid.uuid4()" not in src, (
        "merma.py uses uuid.uuid4() — must use new_uuid() from backend.shared.ids"
    )
    assert "new_uuid()" in src, (
        "merma.py must call new_uuid() for operation_id generation"
    )


def test_merma_ui_imports_new_uuid():
    """merma.py must import new_uuid from backend.shared.ids."""
    src = _read(MERMA_UI)
    assert "from backend.shared.ids import new_uuid" in src or "new_uuid" in src, (
        "merma.py must import new_uuid from backend.shared.ids"
    )


# ── Application service layer ─────────────────────────────────────────────────

def test_waste_application_service_does_not_cast_product_id_to_int():
    """WasteApplicationService must not use int(product_id) — REGLA CERO."""
    src = _read(WASTE_SERVICE)
    assert "int(product_id)" not in src, (
        "waste_application_service.py casts product_id to int — violates REGLA CERO"
    )


def test_waste_application_service_does_not_cast_branch_id_to_int():
    """WasteApplicationService must not use int(branch_id) — REGLA CERO."""
    src = _read(WASTE_SERVICE)
    assert "int(branch_id)" not in src, (
        "waste_application_service.py casts branch_id to int — violates REGLA CERO"
    )


# ── Repository layer ──────────────────────────────────────────────────────────

def test_waste_repository_get_product_signature_is_str():
    """WasteRepository.get_product_for_waste must accept product_id: str, not int | str."""
    src = _read(WASTE_REPO)
    assert "product_id: int | str" not in src, (
        "waste_repository.py has int | str product_id — must be str only"
    )


def test_waste_repository_branch_id_signatures_are_str():
    """All branch_id (sucursal) params must be UUID str — no int | str contracts (REGLA CERO)."""
    src = _read(WASTE_REPO)
    assert "branch_id: str | int" not in src and "branch_id: int | str" not in src, (
        "waste_repository.py has int | str branch_id — sucursal is a UUID, must be str only"
    )


def test_waste_repository_does_not_use_lastrowid_as_entity_id():
    """WasteRepository.register_waste must not return lastrowid as the entity id.

    The canonical waste entity identity is the operation_id (a UUID), not an
    auto-increment integer row id.
    """
    src = _read(WASTE_REPO)
    assert "lastrowid" not in src, (
        "waste_repository.py uses lastrowid as entity identity — violates REGLA CERO. "
        "Return the operation_id (UUID) instead."
    )


# ── Command contract ──────────────────────────────────────────────────────────

def test_waste_command_product_id_is_str():
    """RegisterWasteCommand.product_id must be str, not int."""
    src = _read(WASTE_COMMAND)
    assert "product_id: int" not in src, (
        "waste_commands.py declares product_id as int — must be str"
    )
