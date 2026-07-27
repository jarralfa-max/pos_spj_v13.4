"""Importación UI — flujo presenter/página: cargar CSV, preview, aprobar, ejecutar."""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.catalog_read_service import (  # noqa: E402
    ProductCatalogReadService,
)
from backend.application.products.queries.product_import_query_service import (  # noqa: E402
    ProductImportQueryService,
)
from backend.application.products.use_cases.product_import_use_cases import (  # noqa: E402
    ApproveImportBatchUseCase,
    CreateImportBatchUseCase,
    ExecuteImportBatchUseCase,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402
from frontend.desktop.modules.products.presenter import ProductsPresenter  # noqa: E402

_UNIT = "unit-kg-0001"
_CSV = ("nombre,tipo,unidad\n"
        "Bistec,RAW_MATERIAL,unit-kg-0001\n"
        "Costilla,RAW_MATERIAL,unit-kg-0001\n").encode("utf-8")


class _Session:
    user_id = "bob"  # el aprobador/ejecutor (distinto de quien crea el batch)


@pytest.fixture
def presenter():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_products_schema(conn)
    conn.execute("INSERT INTO units_of_measure (id, code, name, dimension, active) "
                 "VALUES (?, 'KG', 'Kilogramo', 'WEIGHT', 1)", (_UNIT,))
    conn.execute("INSERT INTO product_code_generation_rules "
                 "(id, scope_type, scope_value, prefix, padding, separator, active) "
                 "VALUES ('r0','DEFAULT','','PRD',6,'-',1)")
    conn.commit()

    p = ProductsPresenter(
        read_service_factory=lambda: ProductCatalogReadService(conn),
        import_read_factory=lambda: ProductImportQueryService(conn),
        import_write_factory=lambda: {
            "create": CreateImportBatchUseCase(conn),
            "approve": ApproveImportBatchUseCase(conn),
            "execute": ExecuteImportBatchUseCase(conn),
        },
        session_context=_Session())
    p._conn = conn
    yield p
    conn.close()


def test_presenter_can_import(presenter):
    assert presenter.can_import is True


def _create_as(conn, user):
    from backend.application.products.commands.product_import_commands import (
        CreateImportBatchCommand,
    )
    return CreateImportBatchUseCase(conn).execute(CreateImportBatchCommand(
        operation_id="op", filename="p.csv", data=_CSV, user_id=user)).job_id


def test_create_preview_via_presenter(presenter):
    # El creador es la sesión (bob); la vista previa es sólo lectura.
    ok, _msg, job_id = presenter.create_import_batch(filename="p.csv", data=_CSV)
    assert ok and job_id
    preview = presenter.import_preview(job_id)
    assert len(preview) == 2 and all(r["status"] == "VALID" for r in preview)


def test_approve_and_execute_via_presenter(presenter):
    # Batch creado por 'alice'; la sesión (bob) aprueba y ejecuta (segregación OK).
    job_id = _create_as(presenter._conn, "alice")
    ok2, _m2, _ = presenter.approve_import_batch(job_id)
    assert ok2
    ok3, _m3, _ = presenter.execute_import_batch(job_id)
    assert ok3
    n = presenter._conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]
    assert n == 2


def test_page_loads_and_lists_preview(presenter, monkeypatch):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.pages.import_page import ProductImportPage
    app = QApplication.instance() or QApplication([])
    page = ProductImportPage(presenter)
    # Simula la selección de archivo creando el batch directamente y refrescando.
    _ok, _m, job_id = presenter.create_import_batch(filename="p.csv", data=_CSV)
    page._job_id = job_id
    page._refresh()
    assert page.table.rowCount() == 2
