"""Lote 6: regresiones de los tracebacks reportados en validación manual.

1. audit_logs.id NOT NULL → insert_audit_log acuña UUIDv7.
2. conciliation_runs.id NOT NULL → INSERT con new_uuid (estático).
3. ventas usa InventoryQueryService.get_stock (get_stock_sucursal no existe).
4. cfdi_service importa new_uuid (name 'new_uuid' is not defined).
5. tarjetas_fidelidad: columnas canónicas codigo_qr/id_cliente (no `codigo`).
6. Botones rápidos FX del POS registran el atajo real (no solo el badge).
"""
from __future__ import annotations

from pathlib import Path

from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db

APP_ROOT = Path(__file__).resolve().parents[2]


def _code(path: str) -> str:
    text = (APP_ROOT / path).read_text(encoding="utf-8")
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    )


def test_audit_log_insert_mints_uuid_id():
    from repositories.audit_repository import AuditRepository

    conn = make_db()
    repo = AuditRepository(conn)
    repo.insert_audit_log(
        usuario="admin", accion="UNLOCK", modulo="seguridad",
        entidad="usuario", entidad_id=new_uuid(),
    )
    row = conn.execute(
        "SELECT id, accion FROM audit_logs ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    assert row is not None and row[0], "audit_logs.id debe acuñarse (NOT NULL)"
    assert row[1] == "UNLOCK"


def test_conciliation_insert_includes_uuid_id():
    code = _code("core/services/distribution_engine.py")
    block = code.split("INSERT INTO conciliation_runs", 1)[1][:400]
    assert "id, branch_id" in block
    assert "new_uuid()" in block


def test_ventas_uses_canonical_inventory_query_service():
    code = _code("modulos/ventas.py")
    assert "get_stock_sucursal(" not in code, (
        "InventoryApplicationService no tiene get_stock_sucursal — usar "
        "InventoryQueryService.get_stock"
    )
    assert "inventory_query_service" in code


def test_cfdi_service_has_new_uuid_imported():
    import core.services.cfdi_service as cfdi

    assert hasattr(cfdi, "new_uuid"), "generar_cfdi usaba new_uuid sin importarlo"


def test_create_customer_assigns_loyalty_card_with_canonical_columns():
    from backend.application.use_cases.create_customer_use_case import (
        CreateCustomerCommand,
        CreateCustomerUseCase,
    )

    conn = make_db()
    uc = CreateCustomerUseCase(conn)
    res = uc.execute(CreateCustomerCommand(
        operation_id=new_uuid(), name="Cliente Tarjeta", loyalty_code="eeee",
    ))
    assert res["ok"] is True and res["existing"] is False

    card = conn.execute(
        "SELECT codigo_qr, id_cliente, estado, activa FROM tarjetas_fidelidad"
        " WHERE codigo_qr='eeee'"
    ).fetchone()
    assert card is not None
    assert card[1] == res["id"] and card[2] == "asignada" and card[3] == 1

    # Lookup por código: segundo alta con el mismo código devuelve el existente
    res2 = uc.execute(CreateCustomerCommand(
        operation_id=new_uuid(), name="Otro Nombre", loyalty_code="eeee",
    ))
    assert res2["existing"] is True and res2["id"] == res["id"]


def test_create_customer_assigns_pregenerated_card():
    from backend.application.use_cases.create_customer_use_case import (
        CreateCustomerCommand,
        CreateCustomerUseCase,
    )

    conn = make_db()
    conn.execute(
        "INSERT INTO tarjetas_fidelidad (id, codigo_qr, estado, es_pregenerada)"
        " VALUES (?, 'QR-PRE-1', 'disponible', 1)",
        (new_uuid(),),
    )
    uc = CreateCustomerUseCase(conn)
    res = uc.execute(CreateCustomerCommand(
        operation_id=new_uuid(), name="Cliente Pre", loyalty_code="QR-PRE-1",
    ))
    card = conn.execute(
        "SELECT id_cliente, estado FROM tarjetas_fidelidad WHERE codigo_qr='QR-PRE-1'"
    ).fetchone()
    assert card[0] == res["id"] and card[1] == "asignada"
    n = conn.execute(
        "SELECT COUNT(*) FROM tarjetas_fidelidad WHERE codigo_qr='QR-PRE-1'"
    ).fetchone()[0]
    assert n == 1, "asignar una tarjeta pregenerada no debe duplicarla"


def test_fkey_buttons_register_real_shortcut():
    code = _code("modulos/ventas.py")
    body = code.split("class _FKeyButton", 1)[1].split("\nclass ", 1)[0]
    assert "self.setShortcut(QKeySequence(fkey))" in body, (
        "el badge FX debe registrar el atajo real, no solo pintarlo"
    )
