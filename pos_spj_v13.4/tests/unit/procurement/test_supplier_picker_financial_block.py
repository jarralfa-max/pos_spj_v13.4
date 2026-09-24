"""El selector de proveedores de Compras debe ENSEÑAR el bloqueo, no esconderlo.

Este archivo probaba la tabla heredada `proveedores` y sus dos columnas
(`bloqueado_financiero`, `compras_habilitadas`). Desde el corte SUP-6 el selector
lee el maestro canónico, donde el bloqueo no es una columna sino una fila de
`supplier_blocks`.

Los casos NO se relajaron al migrarlos: se hicieron más exigentes. Ahora pasan
por la **migración 263**, que es la que traduce las columnas heredadas a
bloqueos, y comprueban lo que más podía romperse en ese corte — que copiar un
proveedor bloqueado al maestro no lo DESBLOQUEE en silencio, convirtiéndolo en
elegible para comprar.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

from backend.application.procurement.queries.direct_purchase_read_services import (
    SupplierPickerQueryService,
)
from backend.application.procurement.queries.supplier_directory_query_service import (
    SupplierDirectoryQueryService,
)
from backend.infrastructure.db.schema.supplier_schema import create_supplier_schema
from frontend.desktop.modules.purchasing.direct_purchase_presenter import (
    _supplier_subtitle,
)

_263 = importlib.import_module("migrations.standalone.263_suppliers_legacy_into_master")


def _base(*, con_columnas_178: bool) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_supplier_schema(conn)
    if con_columnas_178:
        conn.execute(
            "CREATE TABLE proveedores(id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER,"
            " bloqueado_financiero INTEGER, compras_habilitadas INTEGER)")
    else:
        conn.execute(
            "CREATE TABLE proveedores(id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER)")
    return conn


@pytest.fixture
def conn_sin_migracion_178():
    """Base anterior a la migración 178: no hay columnas de bloqueo que traducir."""
    conn = _base(con_columnas_178=False)
    conn.execute("INSERT INTO proveedores VALUES ('s1','Proveedor Uno',1)")
    conn.commit()
    _263.run(conn)
    yield conn
    conn.close()


@pytest.fixture
def conn_con_migracion_178():
    conn = _base(con_columnas_178=True)
    conn.execute("INSERT INTO proveedores VALUES ('s1','Proveedor Bloqueado',1,1,1)")
    conn.execute("INSERT INTO proveedores VALUES ('s2','Proveedor Normal',1,0,1)")
    conn.execute("INSERT INTO proveedores VALUES ('s3','Proveedor Sin Compras',1,0,0)")
    conn.commit()
    _263.run(conn)
    yield conn
    conn.close()


def test_the_supplier_survives_the_cutover_and_is_still_found(conn_sin_migracion_178):
    """Lo mínimo del corte: el proveedor heredado se sigue encontrando, con su
    id intacto — del que cuelgan todas las compras ya registradas."""
    rows = SupplierPickerQueryService(conn_sin_migracion_178).search("Proveedor")
    assert [r["id"] for r in rows] == ["s1"]
    assert rows[0]["name"] == "Proveedor Uno"


def test_without_migration_178_no_block_is_invented(conn_sin_migracion_178):
    """Sin columnas de bloqueo no hay bloqueo que traducir, y no se inventa."""
    row = SupplierPickerQueryService(conn_sin_migracion_178).search("Proveedor")[0]
    assert row["bloqueado_financiero"] == 0
    assert row["compras_habilitadas"] == 1


def test_a_blocked_supplier_is_not_silently_unblocked_by_the_cutover(
        conn_con_migracion_178):
    """EL RIESGO CENTRAL de la migración 263.

    Si al copiar al maestro se perdieran los bloqueos, un proveedor bloqueado
    pasaría a ser elegible para comprar sin que nadie lo decidiera.
    """
    by_id = {r["id"]: r
             for r in SupplierPickerQueryService(conn_con_migracion_178).search("Proveedor")}
    assert by_id["s1"]["bloqueado_financiero"] == 1
    assert by_id["s2"]["bloqueado_financiero"] == 0
    assert by_id["s3"]["compras_habilitadas"] == 0


def test_the_two_block_kinds_stay_distinguishable(conn_con_migracion_178):
    """El maestro guarda el bloqueo por TIPO de fila, no en dos columnas.
    Colapsarlos daría el mensaje equivocado al comprador."""
    by_id = {r["id"]: r
             for r in SupplierPickerQueryService(conn_con_migracion_178).search("Proveedor")}
    assert _supplier_subtitle(by_id["s1"]) == "Bloqueado financieramente"
    assert _supplier_subtitle(by_id["s3"]) == "Compras deshabilitadas"


def test_a_blocked_supplier_is_shown_not_hidden(conn_con_migracion_178):
    """Decisión de comportamiento que se preserva: el selector los MUESTRA
    etiquetados. Esconderlos dejaría al comprador sin saber por qué falta un
    proveedor que sabe que existe."""
    ids = {r["id"] for r in SupplierPickerQueryService(conn_con_migracion_178).search("Proveedor")}
    assert ids == {"s1", "s2", "s3"}


def test_the_gate_still_rejects_what_the_picker_labels(conn_con_migracion_178):
    """Selector y puerta de guardado comparten AHORA la misma definición de
    "comprable". Antes vivían en servicios distintos y podían discrepar."""
    from backend.domain.procurement.exceptions import SupplierNotEligibleError

    gate = SupplierDirectoryQueryService(conn_con_migracion_178)
    gate.require_eligible("s2")  # normal: no levanta
    for bloqueado in ("s1", "s3"):
        with pytest.raises(SupplierNotEligibleError):
            gate.require_eligible(bloqueado)


def test_supplier_subtitle_flags_blocked_and_disabled_suppliers():
    assert _supplier_subtitle({"bloqueado_financiero": 1}) == "Bloqueado financieramente"
    assert _supplier_subtitle({"compras_habilitadas": 0}) == "Compras deshabilitadas"
    assert _supplier_subtitle({"code": "PRV-1"}) == "PRV-1"
    assert _supplier_subtitle({}) == ""  # sin dato — nunca inventa un bloqueo
