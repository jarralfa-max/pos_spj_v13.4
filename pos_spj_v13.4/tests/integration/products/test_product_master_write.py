"""PROD-19 paso 7b — alta/edición del maestro `products` (born-clean, sin precio)."""

import json
import sqlite3

import pytest

from backend.application.products.commands.product_master_commands import (
    CreateProductMasterCommand,
    UpdateProductMasterCommand,
)
from backend.application.products.use_cases.product_master_use_cases import (
    CreateProductMasterUseCase,
    UpdateProductMasterUseCase,
)
from backend.infrastructure.db.repositories.products.product_master_repository import (
    ProductMasterRepository,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema


_UNIT_ID = "unit-kg-0001"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    # P0-03: unidad base debe ser un id de catálogo real, no el texto "KG".
    c.execute("INSERT INTO units_of_measure (id, code, name, dimension, active) "
              "VALUES (?, 'KG', 'Kilogramo', 'WEIGHT', 1)", (_UNIT_ID,))
    c.commit()
    yield c
    c.close()


def _create(conn, **kw):
    base = dict(operation_id="op1", code="A-1", name="Bistec de Res",
                product_type="RAW_MATERIAL", base_unit_id=_UNIT_ID, user_id="u1")
    base.update(kw)
    return CreateProductMasterUseCase(conn).execute(CreateProductMasterCommand(**base))


def test_create_writes_canonical_products(conn):
    r = _create(conn)
    assert r.success and r.product_id
    row = conn.execute("SELECT * FROM products WHERE id=?", (r.product_id,)).fetchone()
    assert row["code"] == "A-1" and row["name"] == "Bistec de Res"
    assert row["name_normalized"] == "bistec de res"
    assert row["product_type"] == "RAW_MATERIAL" and row["base_unit_id"] == _UNIT_ID
    assert row["sellable"] == 1 and row["inventory_managed"] == 1


def test_create_rejects_text_unit_code_as_id(conn):
    # P0-03: guardar "KG" (código) como base_unit_id debe fallar; requiere UUID real.
    r = _create(conn, code="Z-9", name="Sin unidad", base_unit_id="KG")
    assert not r.success and "unidad" in r.message.lower()


def test_create_is_uuidv7_id(conn):
    r = _create(conn)
    assert "-" in r.product_id and len(r.product_id) == 36  # UUID canónico


def test_create_rejects_duplicate_code(conn):
    _create(conn)
    r2 = _create(conn, operation_id="op2", name="Otro")
    assert not r2.success and "ya existe" in r2.message


def test_create_validates_required(conn):
    with pytest.raises(ValueError):
        CreateProductMasterUseCase(conn).execute(
            CreateProductMasterCommand(operation_id="", code="", name="",
                                       product_type="", base_unit_id=""))


def test_create_emits_outbox_event(conn):
    r = _create(conn)
    row = conn.execute("SELECT event_name, payload FROM product_outbox WHERE entity_id=?",
                       (r.product_id,)).fetchone()
    assert row["event_name"] == "PRODUCT_CREATED"
    assert json.loads(row["payload"])["code"] == "A-1"


def test_master_has_no_price_or_stock(conn):
    _create(conn)
    cols = {c[1] for c in conn.execute("PRAGMA table_info(products)")}
    assert not (cols & {"precio", "price", "existencia", "sale_price", "costo"})


def test_update_changes_fields(conn):
    r = _create(conn)
    cmd = UpdateProductMasterCommand(
        operation_id="op9", product_id=r.product_id, code="A-1", name="Bistec Premium",
        product_type="PRIMARY_CUT", base_unit_id=_UNIT_ID, species_id="sp1",
        sellable=True, purchasable=False, inventory_managed=True)
    r2 = UpdateProductMasterUseCase(conn).execute(cmd)
    assert r2.success
    row = conn.execute("SELECT * FROM products WHERE id=?", (r.product_id,)).fetchone()
    assert row["name"] == "Bistec Premium" and row["product_type"] == "PRIMARY_CUT"
    # P0-01: el update NO cambia el estado (sigue DRAFT); eso es del ciclo de vida.
    assert row["lifecycle_status"] == "DRAFT" and row["purchasable"] == 0


def test_update_meat_without_species_fails(conn):
    r = _create(conn)
    cmd = UpdateProductMasterCommand(
        operation_id="op9", product_id=r.product_id, code="A-1", name="Corte",
        product_type="PRIMARY_CUT", base_unit_id=_UNIT_ID)  # sin especie
    r2 = UpdateProductMasterUseCase(conn).execute(cmd)
    assert not r2.success and "especie" in r2.message.lower()


def test_create_starts_in_draft(conn):
    # P0-01: el alta nace DRAFT aunque el comando pida ACTIVE.
    r = _create(conn, lifecycle_status="ACTIVE")
    row = conn.execute("SELECT lifecycle_status FROM products WHERE id=?",
                       (r.product_id,)).fetchone()
    assert row[0] == "DRAFT"


def test_update_unknown_product(conn):
    cmd = UpdateProductMasterCommand(
        operation_id="op9", product_id="nope", code="X-1", name="X",
        product_type="RAW_MATERIAL", base_unit_id=_UNIT_ID)
    r = UpdateProductMasterUseCase(conn).execute(cmd)
    assert not r.success and "no existe" in r.message


def test_update_rejects_code_collision(conn):
    a = _create(conn)
    b = _create(conn, operation_id="op2", code="B-1", name="Pollo")
    cmd = UpdateProductMasterCommand(
        operation_id="op9", product_id=b.product_id, code="A-1", name="Pollo",
        product_type="RAW_MATERIAL", base_unit_id=_UNIT_ID)
    r = UpdateProductMasterUseCase(conn).execute(cmd)
    assert not r.success and "ya existe" in r.message


def test_repo_code_exists_excludes_self(conn):
    r = _create(conn)
    repo = ProductMasterRepository(conn)
    assert repo.code_exists("A-1")
    assert not repo.code_exists("A-1", exclude_id=r.product_id)
