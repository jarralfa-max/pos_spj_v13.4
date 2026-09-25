"""Folio humano de la orden: OP-<código de sucursal>-00001 (decisión del usuario,
2026-09-24). El código es el de Configuración → Empresa y sucursales; el
consecutivo, el contador seguro del sistema, por sucursal y sin reinicio."""
from __future__ import annotations

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.use_cases import CreateProcessingOrderUseCase
from backend.application.use_cases.configuracion.company_branch_use_cases import (
    UpdateBranchProfileUseCase,
)
from backend.domain.meat_processing.enums import ProcessType
from backend.domain.settings.exceptions import ConfigurationInvalidValueError
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.infrastructure.integrations.meat_processing_ports import (
    ProcessingOrderFolioAdapter,
)
from backend.shared.ids import new_uuid
from tests.integration.meat_processing._generic_plant import Planta, build_db


def _folio(p, oid):
    return MeatProcessingUnitOfWork(p.conn).orders.get(oid).folio


@pytest.fixture()
def planta():
    conn = build_db()
    p = Planta(conn)
    p.insumo = p.producto("Canal bovina")
    yield p
    conn.close()


def test_orders_are_numbered_per_branch(planta):
    primera = planta.orden(ProcessType.CUTTING, planta.insumo, "10")
    segunda = planta.orden(ProcessType.CUTTING, planta.insumo, "10")
    assert _folio(planta, primera) == f"OP-{planta.codigo}-00001"
    assert _folio(planta, segunda) == f"OP-{planta.codigo}-00002"


def test_each_branch_has_its_own_counter(planta):
    otra = Planta(planta.conn)
    planta.orden(ProcessType.CUTTING, planta.insumo, "10")
    oid = otra.orden(ProcessType.CUTTING, planta.insumo, "10")
    assert _folio(otra, oid) == f"OP-{otra.codigo}-00001"


def test_a_branch_without_code_cannot_create_orders(planta):
    planta.conn.execute("DELETE FROM branch_profiles")
    planta.conn.commit()
    r = CreateProcessingOrderUseCase(planta.auth(), folio_port=ProcessingOrderFolioAdapter).execute(
        planta.conn, operation_id=new_uuid(), branch_id=planta.branch,
        warehouse_id=planta.warehouse, process_type=ProcessType.CUTTING,
        target_product_id=planta.insumo, planned_quantity=Decimal("0"),
        planned_weight=Decimal("10"), actor_user_id=planta.operario)
    assert not r.success and r.error_code == "FOLIO_UNAVAILABLE"
    assert "Configuración" in r.message
    assert planta.conn.execute("SELECT COUNT(*) FROM processing_orders").fetchone()[0] == 0


def test_the_folio_never_changes_once_assigned(planta):
    oid = planta.orden(ProcessType.CUTTING, planta.insumo, "10")
    with MeatProcessingUnitOfWork(planta.conn) as uow:
        orden = uow.orders.get(oid)
        with pytest.raises(Exception):
            orden.assign_folio("OP-OTRO-00099")
        orden.folio = "OP-OTRO-00099"          # aun forzado en memoria…
        uow.orders.save(orden)
    assert _folio(planta, oid) == f"OP-{planta.codigo}-00001"   # …la base conserva el suyo


def test_changing_the_branch_code_changes_only_new_folios(planta):
    vieja = planta.orden(ProcessType.CUTTING, planta.insumo, "10")
    UpdateBranchProfileUseCase(planta.conn).execute(branch_id=planta.branch, name="Planta",
                                                    code="nte")
    nueva = planta.orden(ProcessType.CUTTING, planta.insumo, "10")
    assert _folio(planta, vieja) == f"OP-{planta.codigo}-00001"
    assert _folio(planta, nueva) == "OP-NTE-00001"


def test_a_code_used_by_another_branch_is_refused(planta):
    otra = Planta(planta.conn)
    with pytest.raises(ConfigurationInvalidValueError):
        UpdateBranchProfileUseCase(planta.conn).execute(
            branch_id=planta.branch, name="Planta", code=otra.codigo.lower())


# ── migración 275 ──────────────────────────────────────────────────────────
def _base_vieja():
    c = sqlite3.connect(":memory:")
    importlib.import_module("migrations.standalone.187_meat_processing_bounded_context_schema").run(c)
    c.execute("ALTER TABLE processing_orders RENAME TO _po")
    ddl = c.execute("SELECT sql FROM sqlite_master WHERE name='_po'").fetchone()[0]
    c.execute(ddl.replace("_po", "processing_orders", 1).replace("folio TEXT,", ""))
    c.execute("DROP TABLE _po")
    c.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT NOT NULL,"
              " activa INTEGER DEFAULT 1, fecha_alta DATETIME DEFAULT (datetime('now')))")
    from backend.infrastructure.db.schema.document_output_schema import (
        create_document_numbering_schema,
    )
    from backend.infrastructure.db.schema.settings_schema import (
        create_company_branch_profile_schema,
    )
    create_company_branch_profile_schema(c)
    create_document_numbering_schema(c)
    return c


def _orden_vieja(c, branch, creada):
    c.execute("INSERT INTO processing_orders (id, operation_id, branch_id, warehouse_id,"
              " process_type, target_product_id, planned_quantity, planned_weight, status,"
              " created_by_user_id, created_at, updated_at) VALUES"
              " (?,?,?,?,'CUTTING',?,'0','10','DRAFT',?,?,?)",
              (new_uuid(), new_uuid(), branch, new_uuid(), new_uuid(), new_uuid(), creada,
               creada))


def _migrar(c):
    importlib.import_module("migrations.standalone.275_processing_order_folio").run(c)


def test_migration_gives_every_branch_a_unique_code_from_its_name():
    c = _base_vieja()
    for nombre in ("Centro", "Centro Norte", "Álamos"):
        c.execute("INSERT INTO sucursales (id, nombre) VALUES (?,?)", (new_uuid(), nombre))
    _orden_vieja(c, new_uuid(), "2026-01-01")
    _migrar(c)
    assert sorted(r[0] for r in c.execute("SELECT code FROM branch_profiles")) == [
        "ALA", "CEN", "CEN2"]


def test_migration_numbers_existing_orders_in_creation_order_and_new_ones_continue():
    c = _base_vieja()
    branch = new_uuid()
    c.execute("INSERT INTO sucursales (id, nombre) VALUES (?,?)", (branch, "Centro"))
    for creada in ("2026-03-01", "2026-01-01", "2026-02-01"):
        _orden_vieja(c, branch, creada)
    _migrar(c)
    _migrar(c)                                                 # idempotente
    folios = [r[0] for r in c.execute(
        "SELECT folio FROM processing_orders ORDER BY created_at")]
    assert folios == ["OP-CEN-00001", "OP-CEN-00002", "OP-CEN-00003"]
    assert ProcessingOrderFolioAdapter(c).next_folio(branch) == "OP-CEN-00004"


def test_the_folio_is_unique():
    c = _base_vieja()
    branch = new_uuid()
    c.execute("INSERT INTO sucursales (id, nombre) VALUES (?,?)", (branch, "Centro"))
    _orden_vieja(c, branch, "2026-01-01")
    _orden_vieja(c, branch, "2026-01-02")
    _migrar(c)
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("UPDATE processing_orders SET folio='OP-CEN-00001'")


# ── pantallas ──────────────────────────────────────────────────────────────
def test_the_orders_list_and_the_traceability_show_the_folio():
    from backend.application.meat_processing.queries.lot_traceability_query_service import (
        MeatLotTraceabilityQueryService,
    )
    from backend.application.meat_processing.queries.processing_order_query_service import (
        ProcessingOrderQueryService,
    )
    from frontend.desktop.modules.meat_processing.presenters.meat_traceability_presenter import (
        MeatTraceabilityPresenter,
    )
    from frontend.desktop.modules.meat_processing.presenters.processing_order_presenter import (
        ProcessingOrderPresenter,
    )

    conn = build_db()
    p = Planta(conn)
    especie = p.especie("Bovino")
    canal = p.producto("Canal", lote=True, especie=especie)
    pulpa = p.producto("Pulpa", lote=True, especie=especie)
    p.despiece(canal, [(pulpa, "MAIN_PRODUCT", "1")], especie=especie)
    p.costo(canal, "90")
    p.existencia(canal, "20", lote="C-1", vence="2031-01-01")
    oid = p.lista(ProcessType.DISASSEMBLY, canal, "10")
    assert p.ejecutar(oid, {pulpa: "10"}).success

    presentador = ProcessingOrderPresenter(
        connection_provider=lambda: conn, query_factory=ProcessingOrderQueryService,
        session_context=None)
    filas = presentador.orders(branch_id=p.branch).rows
    assert filas[0][0] == f"OP-{p.codigo}-00001"

    lote = MeatLotTraceabilityQueryService(conn).search_lots(p.branch)[0].lot_id
    resumen = MeatTraceabilityPresenter(conn, branch_id=p.branch).trace(lote).summary
    assert f"OP-{p.codigo}-00001" in resumen
