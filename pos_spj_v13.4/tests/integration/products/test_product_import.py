"""Importación CSV/XLSX — parser + flujo preview→aprobar→ejecutar + segregación."""

import io
import sqlite3
import zipfile

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_import_commands import (
    CreateImportBatchCommand,
    ImportBatchActionCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.queries.product_import_query_service import (
    ProductImportQueryService,
)
from backend.application.products.use_cases.product_import_use_cases import (
    ApproveImportBatchUseCase,
    CreateImportBatchUseCase,
    ExecuteImportBatchUseCase,
)
from backend.domain.products.exceptions import (
    ProductPermissionDeniedError,
    SegregationOfDutiesError,
)
from backend.infrastructure.imports import product_import_parser as parser
from backend.infrastructure.db.schema.products_schema import create_products_schema

_UNIT = "unit-kg-0001"
_CSV = (
    "nombre,tipo,unidad,codigo\n"
    "Bistec de Res,RAW_MATERIAL,unit-kg-0001,\n"
    "Costilla,RAW_MATERIAL,unit-kg-0001,COST-1\n"
    "Sin tipo,,unit-kg-0001,\n"          # inválida: falta tipo
)


def _xlsx_bytes(matrix: list[list[str]]) -> bytes:
    """Construye un .xlsx mínimo válido (inline strings) sin openpyxl."""
    def _cell(ci, value):
        col = chr(ord("A") + ci)
        return (f'<c r="{col}%ROW%" t="inlineStr"><is><t>'
                f'{value}</t></is></c>')
    rows_xml = []
    for ri, row in enumerate(matrix, start=1):
        cells = "".join(_cell(ci, v).replace("%ROW%", str(ri))
                        for ci, v in enumerate(row))
        rows_xml.append(f'<row r="{ri}">{cells}</row>')
    sheet = (
        '<?xml version="1.0"?><worksheet '
        'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(rows_xml)}</sheetData></worksheet>')
    content_types = (
        '<?xml version="1.0"?><Types '
        'xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/></Types>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.execute("INSERT INTO units_of_measure (id, code, name, dimension, active) "
              "VALUES (?, 'KG', 'Kilogramo', 'WEIGHT', 1)", (_UNIT,))
    c.execute("INSERT INTO product_code_generation_rules "
              "(id, scope_type, scope_value, prefix, padding, separator, active) "
              "VALUES ('r0','DEFAULT','','PRD',6,'-',1)")
    c.commit()
    yield c
    c.close()


class _Checker:
    def __init__(self, granted):
        self._granted = set(granted)

    def has_permission(self, user_id, code):
        return code in self._granted


_P = ProductPermissions
_FULL = ProductsAuthorizationPolicy(_Checker({
    _P.IMPORT_EXECUTE, _P.IMPORT_APPROVE, _P.CREATE, _P.OVERRIDE_CODE}))


# ── parser ────────────────────────────────────────────────────────────────
def test_parse_csv_maps_headers():
    rows = parser.parse("x.csv", _CSV.encode("utf-8"))
    assert len(rows) == 3
    assert rows[0] == {"name": "Bistec de Res", "product_type": "RAW_MATERIAL",
                       "base_unit_id": _UNIT, "code": ""}


def test_parse_xlsx_reads_inline_strings():
    data = _xlsx_bytes([["nombre", "tipo", "unidad"],
                        ["Pollo", "RAW_MATERIAL", _UNIT]])
    rows = parser.parse("x.xlsx", data)
    assert rows == [{"name": "Pollo", "product_type": "RAW_MATERIAL",
                     "base_unit_id": _UNIT}]


# ── flujo ───────────────────────────────────────────────────────────────────
def _create_batch(conn, auth=None, user="creator", data=None, filename="p.csv"):
    return CreateImportBatchUseCase(conn, auth or _FULL).execute(
        CreateImportBatchCommand(operation_id="op", filename=filename,
                                 data=data if data is not None else _CSV.encode(),
                                 user_id=user))


def test_create_batch_stages_and_validates(conn):
    r = _create_batch(conn)
    assert r.success and r.total == 3 and r.valid == 2 and r.invalid == 1
    q = ProductImportQueryService(conn)
    assert q.get_job(r.job_id)["status"] == "PREVIEWED"
    preview = q.preview_rows(r.job_id)
    assert [row["status"] for row in preview] == ["VALID", "VALID", "INVALID"]
    assert "tipo" not in preview[2]["error"].lower() or "faltan" in \
        preview[2]["error"].lower()


def test_create_requires_permission(conn):
    auth = ProductsAuthorizationPolicy(_Checker(set()))
    with pytest.raises(ProductPermissionDeniedError):
        _create_batch(conn, auth=auth)


def test_approve_requires_second_user(conn):
    r = _create_batch(conn, user="alice")
    with pytest.raises(SegregationOfDutiesError):
        ApproveImportBatchUseCase(conn, _FULL).execute(ImportBatchActionCommand(
            operation_id="a", job_id=r.job_id, user_id="alice"))
    ok = ApproveImportBatchUseCase(conn, _FULL).execute(ImportBatchActionCommand(
        operation_id="a", job_id=r.job_id, user_id="bob"))
    assert ok.success


def test_execute_requires_approval_first(conn):
    r = _create_batch(conn)
    ex = ExecuteImportBatchUseCase(conn, _FULL).execute(ImportBatchActionCommand(
        operation_id="e", job_id=r.job_id, user_id="bob"))
    assert not ex.success and "aprobado" in ex.message.lower()


def test_full_flow_creates_products(conn):
    r = _create_batch(conn, user="alice")
    ApproveImportBatchUseCase(conn, _FULL).execute(ImportBatchActionCommand(
        operation_id="a", job_id=r.job_id, user_id="bob"))
    ex = ExecuteImportBatchUseCase(conn, _FULL).execute(ImportBatchActionCommand(
        operation_id="e", job_id=r.job_id, user_id="bob"))
    assert ex.success and ex.created == 2  # sólo las 2 filas válidas
    n = conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]
    assert n == 2
    # la fila con código explícito conserva su código; la vacía se autogenera.
    codes = {row["code"] for row in conn.execute("SELECT code FROM products")}
    assert "COST-1" in codes
    assert any(c.startswith("PRD-") for c in codes)
    assert ProductImportQueryService(conn).get_job(r.job_id)["status"] == "EXECUTED"


def test_execute_is_idempotent_per_row(conn):
    r = _create_batch(conn, user="alice")
    ApproveImportBatchUseCase(conn, _FULL).execute(ImportBatchActionCommand(
        operation_id="a", job_id=r.job_id, user_id="bob"))
    uc = ExecuteImportBatchUseCase(conn, _FULL)
    uc.execute(ImportBatchActionCommand(operation_id="e", job_id=r.job_id,
                                        user_id="bob"))
    # Reejecutar no vuelve a crear (las filas ya están CREATED, no VALID).
    conn.execute("UPDATE product_import_jobs SET status='APPROVED' WHERE id=?",
                 (r.job_id,))
    conn.commit()
    again = uc.execute(ImportBatchActionCommand(operation_id="e2", job_id=r.job_id,
                                                user_id="bob"))
    assert again.created == 2  # created_count acumulado, sin filas nuevas
    n = conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]
    assert n == 2
