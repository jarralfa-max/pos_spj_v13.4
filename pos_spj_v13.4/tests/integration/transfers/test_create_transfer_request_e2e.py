"""INV-12 — Create Transfer Request, full stack: presenter -> composition root
-> use case -> repository -> DB. Exercises the exact path
``TransfersModuleHost`` wires in production (minus the Qt dialog itself)."""
from decimal import Decimal

import sqlite3

import pytest

from backend.application.transfers.composition import TransferUseCaseFactory
from backend.infrastructure.db.repositories.transfers.transfer_query_repository import (
    TransferWorkspaceQueryRepository,
)
from backend.infrastructure.db.schema.transfers_schema import create_transfers_schema
from frontend.desktop.modules.transfers.transfers_presenter import TransfersPresenter


class _Session:
    """Operador de transferencias: mismos permisos, alcance sobre b1 y b2."""

    user_id = "u1"
    is_active = True
    active_branch_id = "b1"

    def tiene_permiso(self, code: str) -> bool:
        return code in {"TRANSFERENCIAS.ver", "TRANSFERENCIAS.crear"}


class _SingleBranchSession(_Session):
    """Mismos permisos, UNA sola sucursal. El permiso no es el alcance: u2
    puede crear transferencias, pero sólo entre sucursales que alcanza."""

    user_id = "u2"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_transfers_schema(c)
    c.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER)")
    c.execute("INSERT INTO sucursales VALUES ('b1', 'Matriz', 1), ('b2', 'Sucursal Centro', 1)")
    # `usuarios` hace falta desde que el alcance por sucursal se comprueba de
    # verdad: sin esta tabla no había forma de saber a qué sucursales alcanza
    # `u1`, y la comprobación del caso de uso quedaba inerte. u1 pertenece a b1.
    c.execute("CREATE TABLE usuarios (id TEXT PRIMARY KEY, sucursal_id TEXT)")
    # u2 es el cajero de una sola sucursal: pertenece a b1 y no tiene ninguna
    # asignación. Existe para que las dos reglas se prueben por separado en vez
    # de con el mismo usuario.
    c.execute("INSERT INTO usuarios VALUES ('u1', 'b1'), ('u2', 'b1')")
    # u1 opera las DOS sucursales. Hizo falta asignárselas cuando el destino
    # empezó a comprobarse: una transferencia toca dos sucursales por
    # definición, así que quien la crea necesita alcance sobre ambas. Con sólo
    # b1, u1 no podría crear ninguna transferencia — el caso lo fija abajo
    # `test_a_destination_outside_the_users_branches_is_rejected`.
    c.execute("CREATE TABLE usuarios_sucursales (usuario_id TEXT, sucursal_id TEXT)")
    c.execute("INSERT INTO usuarios_sucursales VALUES ('u1', 'b1'), ('u1', 'b2')")
    c.execute("CREATE TABLE products (id TEXT PRIMARY KEY, base_unit_id TEXT)")
    c.execute("INSERT INTO products VALUES ('p1', 'unit-kg')")
    c.commit()
    yield c
    c.close()


def _presenter(conn, *, session=_Session()):
    factory = TransferUseCaseFactory.from_session(session, connection=conn)
    return TransfersPresenter(
        query_service=TransferWorkspaceQueryRepository(conn), connection=conn,
        create_transfer_request_uc=factory.create_transfer_request(), session_context=session)


class TestCreateTransferRequestEndToEnd:
    def test_creates_a_draft_transfer_with_a_unique_number(self, conn):
        presenter = _presenter(conn)
        ok, message, data = presenter.create_transfer_request(
            origin_branch_id="b1", destination_branch_id="b2", product_id="p1",
            quantity=Decimal("10"), weight=Decimal("2"))

        assert ok is True
        assert data["transfer_number"].startswith("TRF-")
        row = conn.execute(
            "SELECT status, requested_by_user_id FROM stock_transfers WHERE id = ?",
            (data["transfer_id"],)).fetchone()
        assert row["status"] == "DRAFT"
        assert row["requested_by_user_id"] == "u1"
        line = conn.execute(
            "SELECT unit_id, requested_quantity FROM stock_transfer_lines WHERE transfer_id = ?",
            (data["transfer_id"],)).fetchone()
        assert line["unit_id"] == "unit-kg"
        assert line["requested_quantity"] == "10"

    def test_second_request_gets_a_different_sequential_number(self, conn):
        presenter = _presenter(conn)
        _, _, first = presenter.create_transfer_request(
            origin_branch_id="b1", destination_branch_id="b2", product_id="p1", quantity=Decimal("1"))
        _, _, second = presenter.create_transfer_request(
            origin_branch_id="b1", destination_branch_id="b2", product_id="p1", quantity=Decimal("1"))
        assert first["transfer_number"] != second["transfer_number"]

    def test_same_origin_and_destination_is_rejected(self, conn):
        presenter = _presenter(conn)
        ok, message, _ = presenter.create_transfer_request(
            origin_branch_id="b1", destination_branch_id="b1", product_id="p1", quantity=Decimal("1"))
        assert ok is False
        assert "distintos" in message

    def test_unauthorized_user_is_denied_fail_closed(self, conn):
        class _NoPermissionSession(_Session):
            def tiene_permiso(self, code: str) -> bool:
                return False

        presenter = _presenter(conn, session=_NoPermissionSession())
        ok, message, _ = presenter.create_transfer_request(
            origin_branch_id="b1", destination_branch_id="b2", product_id="p1", quantity=Decimal("1"))
        assert ok is False

    def test_branch_options_only_lists_branches_in_scope(self, conn):
        """Este test afirmaba `{"b1", "b2"}` — es decir, fijaba la FUGA como
        contrato: el diálogo recibía todas las sucursales activas y las pintaba
        en los combos, así que cualquiera que abriera Solicitudes descubría el
        nombre de sucursales fuera de su alcance. u2 pertenece a b1 y no tiene
        asignaciones, así que b2 no debe aparecer."""
        presenter = _presenter(conn, session=_SingleBranchSession())
        options = presenter.branch_options()
        assert {o.id for o in options} == {"b1"}

    def test_the_operator_sees_both_branches_they_are_assigned(self, conn):
        """La otra cara: acotar no puede dejar sin sucursales a quien sí las
        tiene asignadas, o el módulo no serviría para nada."""
        presenter = _presenter(conn)
        assert {o.id for o in presenter.branch_options()} == {"b1", "b2"}

    def test_a_request_out_of_scope_is_rejected_by_the_backend(self, conn):
        """La lista acotada es comodidad; el control es el backend. Aunque
        alguien fabrique el id de una sucursal ajena, el caso de uso lo rechaza
        — cosa que ANTES no ocurría, porque la política se construía sin
        verificador de alcance y `require()` no lo evaluaba nunca."""
        presenter = _presenter(conn, session=_SingleBranchSession())
        ok, message, _ = presenter.create_transfer_request(
            origin_branch_id="b2", destination_branch_id="b1", product_id="p1",
            quantity=Decimal("1"))
        assert ok is False
        assert "origen" in message

    def test_a_destination_outside_the_users_branches_is_rejected(self, conn):
        """EL HUECO QUE FALTABA: el origen sí se comprobaba, el destino no.

        u2 alcanza b1, así que sacar mercancía de b1 le corresponde. Dirigirla a
        b2 no: es una sucursal sobre la que no tiene alcance, y hasta ahora el
        backend lo permitía —sólo lo impedía el desplegable de la pantalla, que
        no protege a quien no usa la pantalla—. El mensaje tiene que decir
        DESTINO: saber cuál de las dos sucursales falla es lo que permite pedir
        el permiso correcto.
        """
        presenter = _presenter(conn, session=_SingleBranchSession())
        ok, message, _ = presenter.create_transfer_request(
            origin_branch_id="b1", destination_branch_id="b2", product_id="p1",
            quantity=Decimal("1"))
        assert ok is False
        assert "destino" in message
        assert conn.execute("SELECT COUNT(*) FROM stock_transfers").fetchone()[0] == 0
