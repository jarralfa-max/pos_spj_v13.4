"""Auditoría de Producción cárnica 32cfbf (2026-10-16).

P0  selector de «Nueva orden»: la selección se retiene y el diálogo no se acepta
    incompleto.
P1  el perfil de rendimiento manda en el despiece (kg y % de una sola cifra; el
    esquema, si existe, debe coincidir).
P1  transformación directa: lote recibido → una acción, reutilizando el motor.
P1  Compras ya no explota recetas (guardia en tests/architecture).
P2  pesos reales vacíos; usar lo esperado queda ESTIMADO y exige motivo.
+   los lotes de compra de productos sin inspección nacen liberados (343).
"""

from __future__ import annotations

import importlib
import json
from decimal import Decimal

import pytest

from backend.application.meat_processing.authorization import (
    DirectTransformationStageAuthorization,
    MeatProcessingAuthorizationPolicy,
)
from backend.application.meat_processing.integrations.products_recipe_snapshot_adapter import (
    ProductsRecipeSnapshotAdapter,
)
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.queries.direct_transformation_query_service import (
    DirectTransformationQueryService,
)
from backend.application.meat_processing.use_cases import (
    ApproveProcessingOrderUseCase,
    CreateProcessingOrderUseCase,
    PrepareProcessingOrderUseCase,
    ReleaseProcessingOrderUseCase,
)
from backend.application.meat_processing.use_cases.direct_transformation_use_cases import (
    ExecuteDirectTransformationUseCase,
)
from backend.application.meat_processing.use_cases.order_execution_use_cases import (
    ExecuteProcessingOrderUseCase,
)
from backend.domain.meat_processing.enums import ProcessType
from backend.domain.meat_processing.exceptions import MeatProcessingSegregationOfDutiesError
from backend.infrastructure.integrations.meat_processing_execution_ports import (
    execution_ports_factory,
    reservation_port_factory,
)
from backend.infrastructure.integrations.meat_processing_ports import ProcessingOrderFolioAdapter
from backend.shared.ids import new_uuid
from tests.integration._reversible_cutting import active_yield_profile, reversible_cutting_scheme
from tests.integration.meat_processing._generic_plant import KG, Planta, _Only, _Todo, build_db

_P = MeatProcessingPermissions


@pytest.fixture
def conn():
    c = build_db()
    yield c
    c.close()


def _requires_inspection(p: Planta, producto: str) -> None:
    p.conn.execute("INSERT INTO product_quality_profiles (product_id, inspection_required,"
                   " updated_at) VALUES (?, 1, 'x')", (producto,))


def _pollo(p: Planta, *, kg="40", lote="L-POLLO", perfil=True):
    """Pollo con perfil de rendimiento (sin esquema) y precio en cada corte."""
    pollo = p.producto("Pollo Entero")
    pechuga, pierna, merma = (p.producto("Pechuga"), p.producto("Pierna"),
                              p.producto("Menudencia"))
    if perfil:
        active_yield_profile(p.conn, product_id=pollo, outputs=[
            {"product_id": pechuga, "output_type": "MAIN_PRODUCT", "expected_yield_pct": "35",
             "unit_id": KG},
            {"product_id": pierna, "output_type": "CO_PRODUCT", "expected_yield_pct": "55",
             "unit_id": KG},
            {"product_id": merma, "output_type": "WASTE", "expected_yield_pct": "10",
             "unit_id": KG}])
    p.costo(pollo, "40")
    for corte, precio in ((pechuga, "120"), (pierna, "70")):
        p.precio(corte, precio)
    lote_id = p.existencia(pollo, kg, lote=lote)
    return pollo, pechuga, pierna, merma, lote_id


# ── P1: el perfil manda ─────────────────────────────────────────────────────
def test_profile_without_cutting_scheme_now_prepares(conn):
    """Antes se exigía esquema de corte y un producto con perfil activo no se
    podía preparar nunca (caso real: «Pollo Entero»)."""
    p = Planta(conn)
    pollo, *_ = _pollo(p)
    oid = p.orden(ProcessType.DISASSEMBLY, pollo, "20")
    r = p.preparar(oid)
    assert r.success and r.data.get("ready"), (r.message, r.data)


def test_expected_kg_and_pct_come_from_one_figure(conn):
    p = Planta(conn)
    pollo, pechuga, *_ = _pollo(p)
    vista = DirectTransformationQueryService(conn).preview(pollo, Decimal("20"))
    assert vista.problem is None
    fila = next(f for f in vista.rows if f.product_id == pechuga)
    assert fila.expected_pct == Decimal("35.00")
    assert fila.expected_kg == Decimal("7.000")          # 20 × 35 / 100
    assert vista.total_pct == Decimal("100.00") and vista.unassigned_kg == 0


def test_a_scheme_that_contradicts_the_profile_blocks_with_names(conn):
    p = Planta(conn)
    pollo, pechuga, pierna, merma, _ = _pollo(p)
    reversible_cutting_scheme(conn, product_id=pollo, reversible=False, outputs=[
        {"product_id": pechuga, "output_type": "MAIN_PRODUCT", "quantity": "0.40",
         "unit_id": KG},
        {"product_id": pierna, "output_type": "CO_PRODUCT", "quantity": "0.50", "unit_id": KG},
        {"product_id": merma, "output_type": "WASTE", "quantity": "0.10", "unit_id": KG}])
    oid = p.orden(ProcessType.DISASSEMBLY, pollo, "20")
    r = p.preparar(oid)
    assert not r.success and r.error_code == "MASTER_DATA_MISSING"
    assert "Pechuga" in r.message and "40 %" in r.message and "35 %" in r.message
    assert pechuga not in r.message                      # nunca un UUID


def test_a_scheme_that_matches_the_profile_is_accepted(conn):
    p = Planta(conn)
    pollo, pechuga, pierna, merma, _ = _pollo(p)
    reversible_cutting_scheme(conn, product_id=pollo, reversible=False, outputs=[
        {"product_id": pechuga, "output_type": "MAIN_PRODUCT", "quantity": "0.35",
         "unit_id": KG},
        {"product_id": pierna, "output_type": "CO_PRODUCT", "quantity": "0.55", "unit_id": KG},
        {"product_id": merma, "output_type": "WASTE", "quantity": "0.10", "unit_id": KG}])
    snapshot = ProductsRecipeSnapshotAdapter(conn).resolve(
        target_product_id=pollo, process_type=ProcessType.DISASSEMBLY)
    assert snapshot.definition_problems == ()
    assert all(o.source == "YIELD_PROFILE" for o in snapshot.outputs)


def test_a_scheme_alone_is_not_enough(conn):
    p = Planta(conn)
    pollo, pechuga, pierna, merma, _ = _pollo(p, perfil=False)
    reversible_cutting_scheme(conn, product_id=pollo, reversible=False, outputs=[
        {"product_id": pechuga, "output_type": "MAIN_PRODUCT", "quantity": "0.9",
         "unit_id": KG},
        {"product_id": merma, "output_type": "WASTE", "quantity": "0.1", "unit_id": KG}])
    r = p.preparar(p.orden(ProcessType.DISASSEMBLY, pollo, "20"))
    assert not r.success and "perfil de rendimiento" in r.message


# ── P2: estimado explícito ──────────────────────────────────────────────────
def test_estimated_outputs_need_a_reason_and_are_recorded(conn):
    p = Planta(conn)
    pollo, pechuga, pierna, merma, _ = _pollo(p)
    oid = p.lista(ProcessType.DISASSEMBLY, pollo, "20")
    salidas = {pechuga: "7", pierna: "11", merma: "2"}
    sin_motivo = p.ejecutar(oid, salidas, estimated_product_ids=(pierna,))
    assert not sin_motivo.success and sin_motivo.error_code == "ESTIMATE_REASON_REQUIRED"
    r = p.ejecutar(oid, salidas, estimated_product_ids=(pierna,),
                   estimate_reason="Báscula descompuesta")
    assert r.success, r.message
    filas = dict(conn.execute(
        "SELECT product_id, weight_source FROM processing_output_results"
        " WHERE processing_order_id=?", (oid,)).fetchall())
    assert filas[pierna] == "ESTIMATED" and filas[pechuga] == "CAPTURED"
    motivo = conn.execute("SELECT estimate_reason FROM processing_output_results"
                          " WHERE processing_order_id=? AND product_id=?",
                          (oid, pierna)).fetchone()[0]
    assert motivo == "Báscula descompuesta"
    auditoria = json.loads(conn.execute(
        "SELECT after_json FROM meat_processing_audit_log WHERE action='EXECUTED'"
        " AND entity_id=?", (oid,)).fetchone()[0])
    assert auditoria["estimated_outputs"] == [pierna]


# ── P1: transformación directa ──────────────────────────────────────────────
def _direct(conn, permisos: dict):
    real = MeatProcessingAuthorizationPolicy(_Only(permisos))
    etapas = MeatProcessingAuthorizationPolicy(
        DirectTransformationStageAuthorization(_Only(permisos)))
    return ExecuteDirectTransformationUseCase(
        real,
        create_uc=CreateProcessingOrderUseCase(etapas, folio_port=ProcessingOrderFolioAdapter),
        approve_uc=ApproveProcessingOrderUseCase(etapas),
        prepare_uc=PrepareProcessingOrderUseCase(
            etapas, recipe_snapshot_port=ProductsRecipeSnapshotAdapter(conn),
            reservation_port_factory=reservation_port_factory(conn)),
        release_uc=ReleaseProcessingOrderUseCase(etapas),
        execute_uc=ExecuteProcessingOrderUseCase(
            etapas, ports_factory=execution_ports_factory(), authorizer_checker=_Todo()),
        lots_query_factory=DirectTransformationQueryService)


def test_direct_transformation_runs_with_only_its_own_permission(conn):
    p = Planta(conn)
    pollo, pechuga, pierna, merma, lote = _pollo(p)
    uc = _direct(conn, {p.operario: (_P.DIRECT_TRANSFORMATION_EXECUTE,)})
    op = new_uuid()
    r = uc.execute(conn, operation_id=op, branch_id=p.branch, lot_id=lote,
                   input_weight=Decimal("20"), actor_user_id=p.operario, outputs=[
                       {"product_id": pechuga, "weight": Decimal("6.9")},
                       {"product_id": pierna, "weight": Decimal("11")},
                       {"product_id": merma, "weight": Decimal("2.1")}])
    assert r.success, r.message
    orden = conn.execute("SELECT status, source_type, source_reference_id, approved_by_user_id,"
                         " folio FROM processing_orders WHERE id=?", (r.data["order_id"],)
                         ).fetchone()
    assert tuple(orden)[:4] == ("CLOSED", "DIRECT_TRANSFORMATION", lote, None)
    assert r.data["folio"] == orden[4]
    acciones = [a for (a,) in conn.execute(
        "SELECT action FROM meat_processing_audit_log WHERE entity_id=? ORDER BY rowid",
        (r.data["order_id"],))]
    assert "APPROVED_BY_DIRECT_TRANSFORMATION" in acciones and acciones[-1] == "CLOSED"
    assert p.saldo(pollo) == Decimal("20")                # 40 − 20, del lote elegido
    assert p.saldo(pechuga) == Decimal("6.9") and p.saldo(pierna) == Decimal("11")
    assert p.saldo(merma) == 0                            # la merma no entra a existencia
    # idempotente: mismo operation_id, misma orden
    otra = uc.execute(conn, operation_id=op, branch_id=p.branch, lot_id=lote,
                      input_weight=Decimal("20"), actor_user_id=p.operario, outputs=[])
    assert otra.success and otra.data.get("already_processed")
    assert otra.data["order_id"] == r.data["order_id"]


def test_direct_transformation_requires_its_permission(conn):
    p = Planta(conn)
    pollo, pechuga, pierna, merma, lote = _pollo(p)
    todos_menos = tuple(c for c in vars(_P).values() if isinstance(c, str)
                        and c != _P.DIRECT_TRANSFORMATION_EXECUTE)
    r = _direct(conn, {p.operario: todos_menos}).execute(
        conn, operation_id=new_uuid(), branch_id=p.branch, lot_id=lote,
        input_weight=Decimal("20"), actor_user_id=p.operario, outputs=[])
    assert not r.success and r.error_code == "PERMISSION_DENIED"


def test_direct_transformation_rejects_unreleased_or_short_lots(conn):
    p = Planta(conn)
    pollo, pechuga, pierna, merma, lote = _pollo(p, kg="10")
    uc = _direct(conn, {p.operario: (_P.DIRECT_TRANSFORMATION_EXECUTE,)})
    corto = uc.execute(conn, operation_id=new_uuid(), branch_id=p.branch, lot_id=lote,
                       input_weight=Decimal("20"), actor_user_id=p.operario, outputs=[])
    assert not corto.success and corto.error_code == "INSUFFICIENT_AVAILABILITY"
    conn.execute("UPDATE inventory_lots SET quality_status='PENDING_INSPECTION' WHERE id=?",
                 (lote,))
    pendiente = uc.execute(conn, operation_id=new_uuid(), branch_id=p.branch, lot_id=lote,
                           input_weight=Decimal("5"), actor_user_id=p.operario, outputs=[])
    assert not pendiente.success and pendiente.error_code == "LOT_NOT_RELEASED"
    assert conn.execute("SELECT COUNT(*) FROM processing_orders").fetchone()[0] == 0


def test_a_normal_order_still_needs_a_different_approver(conn):
    p = Planta(conn)
    pollo, *_ = _pollo(p)
    r = CreateProcessingOrderUseCase(p.auth()).execute(
        conn, operation_id=new_uuid(), branch_id=p.branch, warehouse_id=p.warehouse,
        process_type=ProcessType.DISASSEMBLY, target_product_id=pollo,
        planned_quantity=Decimal("0"), planned_weight=Decimal("5"), actor_user_id=p.operario)
    a = ApproveProcessingOrderUseCase(p.auth()).execute(
        conn, order_id=r.entity_id, operation_id=new_uuid(), actor_user_id=p.operario,
        direct_transformation=True)
    assert not a.success and a.error_code == "SEGREGATION_OF_DUTIES"
    from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
        MeatProcessingUnitOfWork,
    )
    orden = MeatProcessingUnitOfWork(conn).orders.get(r.entity_id)
    with pytest.raises(MeatProcessingSegregationOfDutiesError):
        orden.approve_direct_transformation(actor_user_id=p.operario)


def test_lots_list_explains_what_cannot_be_used(conn):
    p = Planta(conn)
    pollo, pechuga, pierna, merma, lote = _pollo(p)
    q = DirectTransformationQueryService(conn)
    assert q.unavailable_reason(p.branch) is None
    assert [x.lot_id for x in q.lots(p.branch) if x.eligible] == [lote]
    conn.execute("UPDATE inventory_lots SET quality_status='PENDING_INSPECTION' WHERE id=?",
                 (lote,))
    (fila,) = q.lots(p.branch)
    assert not fila.eligible and "Calidad" in fila.blocked_reason
    conn.execute("UPDATE warehouses SET allow_production=0")
    assert "Producción" in q.unavailable_reason(p.branch)


# ── lotes de compra liberados y migración 343 ───────────────────────────────
def test_purchase_lots_are_released_unless_the_product_needs_inspection(conn):
    from backend.application.event_handlers.inventory.purchase_receipt_handler import (
        PurchaseReceiptHandler,
    )
    p = Planta(conn)
    libre, revisado = p.producto("Sin inspección"), p.producto("Con inspección")
    _requires_inspection(p, revisado)
    handler = PurchaseReceiptHandler(conn)
    for producto, codigo in ((libre, "L-LIBRE"), (revisado, "L-REV")):
        handler.handle({"operation_id": new_uuid(), "goods_receipt_id": new_uuid(),
                        "branch_id": p.branch, "warehouse_id": p.warehouse,
                        "user_id": p.gerente, "lines": [{
                            "product_id": producto, "quantity": "5", "unit": "KG",
                            "lot_code": codigo, "to_location_id": p.ubicacion}]})
    estados = dict(conn.execute("SELECT lot_code, quality_status FROM inventory_lots"
                                " WHERE lot_code IN ('L-LIBRE','L-REV')").fetchall())
    assert estados == {"L-LIBRE": "RELEASED", "L-REV": "PENDING_INSPECTION"}


def test_migration_343_releases_stuck_purchase_lots_and_seeds_permission(conn):
    p = Planta(conn)
    libre, revisado = p.producto("Sin inspección"), p.producto("Con inspección")
    _requires_inspection(p, revisado)
    for producto, codigo in ((libre, "A"), (revisado, "B")):
        conn.execute(
            "INSERT INTO inventory_lots (id, product_id, lot_code, origin_type, quality_status,"
            " traceability_status, branch_id, created_at) VALUES (?,?,?,'PURCHASE',"
            "'PENDING_INSPECTION','LINKED',?,'x')", (new_uuid(), producto, codigo, p.branch))
    conn.execute("CREATE TABLE IF NOT EXISTS roles (id TEXT PRIMARY KEY, nombre TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS rol_permisos (id TEXT PRIMARY KEY, rol_id TEXT,"
                 " modulo TEXT, accion TEXT, permitido INTEGER DEFAULT 1)")
    conn.execute("INSERT INTO roles VALUES ('r-alm','almacen'), ('r-caj','cajero')")
    conn.execute("INSERT INTO rol_permisos VALUES ('x1','r-alm','PRODUCCION','orden.iniciar',1)")
    m = importlib.import_module("migrations.standalone.343_meat_direct_transformation")
    m.run(conn)
    m.run(conn)
    estados = dict(conn.execute("SELECT lot_code, quality_status FROM inventory_lots"
                                " WHERE lot_code IN ('A','B')").fetchall())
    assert estados == {"A": "RELEASED", "B": "PENDING_INSPECTION"}
    roles = [r for (r,) in conn.execute(
        "SELECT rol_id FROM rol_permisos WHERE accion='transformacion_directa.ejecutar'")]
    assert roles == ["r-alm"]


# ── P0: selector y diálogo ──────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app():
    QtWidgets = pytest.importorskip("PyQt5.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _dialog(**extra):
    from frontend.desktop.components.search_selector import SearchOption
    from frontend.desktop.modules.meat_processing.dialogs import CreateProcessingOrderDialog
    opciones = {"pollo": [SearchOption(id="p1", label="Pollo Entero")],
                "po": [SearchOption(id="p1", label="Pollo Entero"),
                       SearchOption(id="p2", label="Pollo Marinado")]}
    return CreateProcessingOrderDialog(
        process_types=[("DISASSEMBLY", "Despiece"), ("MIXING", "Mezclado")],
        product_provider=lambda q, _proceso: opciones.get(q, []), **extra)


def test_click_keeps_the_product_after_the_list_is_gone(app):
    dlg = _dialog()
    dlg.product._search_box.setText("po")
    dlg.product._results.itemClicked.emit(dlg.product._results.item(1))
    assert dlg.product_id() == "p2"
    assert dlg.product._search_box.text() == "Pollo Marinado"
    assert dlg.product._results.count() == 0                # la lista ya no existe


def test_enter_picks_the_only_result_and_typing_again_forgets_it(app):
    dlg = _dialog()
    dlg.product._search_box.setText("pollo")
    dlg.product._search_box.returnPressed.emit()
    assert dlg.product_id() == "p1"
    dlg.product._search_box.setText("po")                    # nueva búsqueda
    assert dlg.product_id() is None


def test_changing_the_process_forgets_the_product(app):
    dlg = _dialog()
    dlg.product._search_box.setText("pollo")
    dlg.product._search_box.returnPressed.emit()
    dlg.process_type_combo.setCurrentIndex(1)
    assert dlg.product_id() is None


def test_the_dialog_does_not_close_incomplete(app):
    dlg = _dialog()
    dlg._accept_if_valid()
    assert dlg.result() == 0 and "producto" in dlg._error.text()
    dlg.product._search_box.setText("pollo")
    dlg.product._search_box.returnPressed.emit()
    dlg._accept_if_valid()
    assert dlg.result() == 0 and "peso" in dlg._error.text()
    dlg.weight.set_decimal(Decimal("20"))
    dlg._accept_if_valid()
    assert dlg.result() == 1


def test_a_missing_production_warehouse_is_said_upfront(app):
    from PyQt5.QtWidgets import QDialogButtonBox
    dlg = _dialog(blocking_problem="La sucursal no tiene un almacén habilitado para producción.")
    boton = dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok)
    assert not boton.isEnabled()


def test_execution_weights_start_empty_and_estimates_are_explicit(app):
    from frontend.desktop.modules.meat_processing.dialogs_execution import (
        ExecuteProcessingOrderDialog,
    )
    plan = {"effective_version": "rendimiento v1",
            "inputs": [{"product_id": "in", "product_name": "Pollo", "reserved_weight": "20",
                        "lots": []}],
            "outputs": [{"product_id": "a", "product_name": "Pechuga", "output_type": "MAIN_PRODUCT",
                         "expected_weight": Decimal("7"), "quality_gate": False},
                        {"product_id": "b", "product_name": "Pierna", "output_type": "CO_PRODUCT",
                         "expected_weight": Decimal("11"), "quality_gate": False}]}
    dlg = ExecuteProcessingOrderDialog(plan=plan)
    assert all(c.decimal_value() is None for c in dlg._campos.values())
    dlg._campos["a"].set_decimal(Decimal("6.8"))
    dlg._accept_if_valid()
    assert dlg.result() == 0 and "Pierna" in dlg._error.text()
    dlg._use_expected_for_empty()
    assert dlg.estimated_product_ids() == ("b",)
    assert dlg._campos["b"].decimal_value() == Decimal("11")
    dlg._accept_if_valid()
    assert dlg.result() == 0 and "motivo" in dlg._error.text()
    dlg.estimate_reason.setText("Sin báscula")
    dlg._accept_if_valid()
    assert dlg.result() == 1 and dlg.estimate_reason_text() == "Sin báscula"
    dlg._campos["b"].set_decimal(Decimal("10.9"))           # pesado a mano: deja de ser estimado
    assert dlg.estimated_product_ids() == ()


def test_direct_transformation_dialog_previews_and_balances(app, conn):
    from frontend.desktop.modules.meat_processing.dialogs_direct_transformation import (
        DirectTransformationDialog,
    )
    p = Planta(conn)
    pollo, pechuga, pierna, merma, lote = _pollo(p)
    q = DirectTransformationQueryService(conn)

    class _Presenter:
        def preview(self, product_id, kg):
            return q.preview(product_id, kg)

    (fila,) = q.lots(p.branch)
    dlg = DirectTransformationDialog(lot=fila, presenter=_Presenter())
    dlg.input_kg.set_decimal(Decimal("20"))
    assert dlg.table.rowCount() == 3
    assert all(c.decimal_value() is None for c in dlg._campos.values())
    dlg._accept_if_valid()
    assert dlg.result() == 0 and "Falta el peso real" in dlg._error.text()
    dlg._campos[pechuga].set_decimal(Decimal("6.8"))
    dlg._campos[merma].set_decimal(Decimal("2.2"))
    dlg._use_expected_for_empty()
    assert dlg.estimated_product_ids() == (pierna,)
    assert dlg._campos[pierna].decimal_value() == Decimal("11.000")
    assert "diferencia sin clasificar 0.000 kg" in dlg.balance.text()
    dlg.input_kg.set_decimal(Decimal("10"))                  # cambia lo esperado
    assert dlg._campos[pierna].decimal_value() == Decimal("5.500")   # sigue estimado
    assert dlg._campos[pechuga].decimal_value() == Decimal("6.800")  # lo pesado se conserva
    dlg.input_kg.set_decimal(Decimal("50"))
    dlg._accept_if_valid()
    assert dlg.result() == 0 and "40.000 kg disponibles" in dlg._error.text()
