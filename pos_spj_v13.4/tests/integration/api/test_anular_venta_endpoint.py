"""`POST /api/v1/ventas/{id}/anular` — adaptador delgado, no SQL propio.

Antes el endpoint hacía `UPDATE ventas SET estado='cancelada'` con SQL
directo. La venta quedaba anulada PERO conservaba su asiento contable y su
cuenta por cobrar, el inventario no volvía, la caja no se compensaba, los
puntos no se revertían y no se emitía ningún evento: los libros y el ledger
de ventas divergían en silencio (§11/§19/§31).

Ahora delega en `SalesReversalService.cancel_sale()`, que ya hacía todo eso
de forma atómica y que el contenedor construye con el `finance_service`
real. Estas pruebas fijan el contrato del adaptador: que delegue, que
traduzca los errores de negocio a códigos HTTP y que no vuelva a ejecutar
SQL por su cuenta.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from api.auth import verify_api_key
from api.deps import get_sales_reversal_service
from api.main import app
from core.services.sales_reversal_service import (
    CancelResultDTO,
    ReversalError,
    UsuarioRequeridoError,
    VentaNoCompletadaError,
    VentaNoEncontradaError,
    VentaYaCanceladaError,
)

ROOT = Path(__file__).resolve().parents[3]
ENDPOINT = "/api/v1/ventas/V-1/anular"


class _FakeReversal:
    """Doble del servicio: registra la llamada o lanza lo que se le pida."""

    def __init__(self, raises: Exception | None = None) -> None:
        self.raises = raises
        self.calls: list[tuple] = []

    def cancel_sale(self, sale_id, usuario, motivo=""):
        self.calls.append((sale_id, usuario, motivo))
        if self.raises is not None:
            raise self.raises
        return CancelResultDTO(
            sale_id=sale_id, operation_id="CANCEL-V-1-abcd1234",
            total_revertido=250.5, inventario_restaurado=3,
        )


@pytest.fixture
def client():
    def _make(service):
        app.dependency_overrides[verify_api_key] = lambda: "test-key"
        app.dependency_overrides[get_sales_reversal_service] = lambda: service
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def test_delegates_to_the_reversal_service(client):
    service = _FakeReversal()
    response = client(service).post(
        ENDPOINT, params={"usuario": "cajera1", "motivo": "cliente se arrepintió"})

    assert response.status_code == 200
    assert service.calls == [("V-1", "cajera1", "cliente se arrepintió")]


def test_returns_the_operations_evidence_not_just_ok(client):
    """El `operation_id` es lo que permite auditar la reversa; el endpoint
    viejo sólo devolvía `{"ok": True}`."""
    body = client(_FakeReversal()).post(
        ENDPOINT, params={"usuario": "cajera1"}).json()

    assert body["ok"] is True
    assert body["estado"] == "cancelada"
    assert body["operation_id"] == "CANCEL-V-1-abcd1234"
    assert body["total_revertido"] == 250.5
    assert body["inventario_restaurado"] == 3


def test_motivo_is_optional_and_forwarded_empty(client):
    service = _FakeReversal()
    client(service).post(ENDPOINT, params={"usuario": "cajera1"})
    assert service.calls == [("V-1", "cajera1", "")]


def test_usuario_is_required(client):
    """Sin actor no hay audit trail: `cancel_sale()` rechaza una
    cancelación anónima, así que el endpoint la rechaza antes."""
    assert client(_FakeReversal()).post(ENDPOINT).status_code == 422


@pytest.mark.parametrize(
    "error, expected_status",
    [
        (VentaNoEncontradaError("no existe"), 404),
        (VentaYaCanceladaError("ya cancelada"), 409),
        (VentaNoCompletadaError("VENTA_NO_COMPLETADA: estado=pendiente"), 409),
        (UsuarioRequeridoError("usuario es obligatorio"), 422),
        (ReversalError("fallo de negocio"), 409),
    ],
)
def test_business_errors_map_to_http_codes(client, error, expected_status):
    """Ninguna falla de negocio conocida debe salir como 500: la
    transacción del servicio ya hizo rollback total."""
    response = client(_FakeReversal(raises=error)).post(
        ENDPOINT, params={"usuario": "cajera1"})
    assert response.status_code == expected_status


def test_a_completed_sale_is_the_only_thing_this_endpoint_cancels(client):
    """Cambio de contrato deliberado: antes se aceptaba cualquier estado y
    se marcaba 'cancelada' igual, dejando un registro incoherente."""
    response = client(
        _FakeReversal(raises=VentaNoCompletadaError(
            "VENTA_NO_COMPLETADA: id=V-1 estado=pendiente"))
    ).post(ENDPOINT, params={"usuario": "cajera1"})

    assert response.status_code == 409
    assert "VENTA_NO_COMPLETADA" in response.json()["detail"]


def test_the_endpoint_runs_no_sql_of_its_own():
    """§19: el router es un adaptador. Se comprueba sobre el AST de la
    función y NO sobre el texto del archivo, porque el docstring cita el
    `UPDATE ventas SET estado='cancelada'` retirado para explicar qué se
    corrigió; un `in source` lo marcaría como vivo. El propio docstring de
    la función también es un `ast.Constant`, así que se descarta aparte."""
    tree = ast.parse((ROOT / "api/routers/ventas.py").read_text(encoding="utf-8"))
    function = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "anular_venta"
    )
    # El nodo del docstring se descarta por IDENTIDAD: `ast.get_docstring()`
    # devuelve el texto ya normalizado y no coincide con el literal crudo.
    docstring_node = None
    if function.body and isinstance(function.body[0], ast.Expr):
        first = function.body[0].value
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            docstring_node = first

    literals = [
        node.value for node in ast.walk(function)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and node is not docstring_node
    ]
    sql = [
        text for text in literals
        if any(verb in text.upper() for verb in ("SELECT ", "UPDATE ", "INSERT ", "DELETE "))
    ]
    assert not sql, f"SQL embebido en el router: {sql}"

    called = [
        node.func.attr for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "cancel_sale" in called
    assert "execute" not in called, "el router no debe tocar la conexión"
