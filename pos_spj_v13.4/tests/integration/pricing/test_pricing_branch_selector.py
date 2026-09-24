"""La sucursal se ELIGE también en Precios, no se teclea.

Mismo fallo que en Compras y encontrado al barrer por el mismo patrón: los dos
diálogos de precio pedían la sucursal en una caja de texto libre
("Sucursal (vacío = todas)"), es decir, el UUID escrito a mano. El propio
diálogo de lote ya decía en su docstring que pedir un identificador a mano es
pedir un dato que el usuario no puede conocer — lo decía de la categoría,
mientras la sucursal justo debajo era exactamente eso.

Aquí el vacío SIGNIFICA algo (el precio rige en todas las sucursales), así que
"Todas las sucursales" es una opción explícita y no el resultado de dejar un
campo en blanco.
"""

import sqlite3

import pytest
from PyQt5.QtWidgets import QApplication

from backend.application.security.branch_scope_query_service import (
    BranchScopeQueryService,
    BranchSearchQuery,
)
from frontend.desktop.components.searchable_combo import SearchableComboBox
from frontend.desktop.modules.pricing.dialogs.pricing_dialogs import (
    BulkPriceDialog,
    ProductPriceFormDialog,
)
from frontend.desktop.modules.pricing.presenter import PricingPresenter


@pytest.fixture(scope="module")
def app():
    # A nivel de módulo: crear la QApplication dentro del cuerpo de un test
    # tumba pytest en silencio en este entorno.
    return QApplication.instance() or QApplication([])


class _Session:
    user_id = "u1"
    active_branch_id = "b1"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER)")
    c.execute("INSERT INTO sucursales VALUES ('b1','Matriz',1), ('b2','San Bartolo',1)")
    c.execute("CREATE TABLE usuarios (id TEXT PRIMARY KEY, sucursal_id TEXT)")
    c.execute("INSERT INTO usuarios VALUES ('u1','b1')")
    c.commit()
    yield c
    c.close()


def _presenter(conn, session=None):
    return PricingPresenter(
        read_service_factory=lambda: None,
        connection_provider=lambda: conn,
        session_context=session if session is not None else _Session())


class TestTheOptions:
    def test_all_branches_is_an_explicit_option_not_an_empty_field(self, conn):
        opciones = _presenter(conn).branch_options()
        assert opciones[0] == ("", "Todas las sucursales")

    def test_only_the_users_branches_are_offered(self, conn):
        """u1 pertenece a b1 y no tiene asignaciones: San Bartolo no debe
        aparecer. Ofrecer todas y esconderlas en la pantalla sería una fuga —
        el nombre ya habría viajado."""
        ids = {i for i, _ in _presenter(conn).branch_options()}
        assert ids == {"", "b1"}
        # Comprobación cruzada: el servicio de alcance dice lo mismo.
        alcance = BranchScopeQueryService(conn).search(
            BranchSearchQuery(allowed_for_user="u1", page_size=50))
        assert {o.branch_id for o in alcance} == {"b1"}

    def test_without_a_session_only_all_branches_is_offered(self, conn):
        """Sin usuario no hay alcance que resolver. Se falla cerrado, pero sin
        dejar el diálogo inservible: "Todas" sigue siendo una opción válida."""
        class _SinUsuario:
            user_id = ""
        assert _presenter(conn, _SinUsuario()).branch_options() == [
            ("", "Todas las sucursales")]


class TestTheDialogs:
    def test_the_price_dialog_offers_a_selector_not_a_text_box(self, app, conn):
        dialog = ProductPriceFormDialog(
            list_options=[("l1", "BASE · Base")],
            branch_options=_presenter(conn).branch_options())
        assert isinstance(dialog._branch, SearchableComboBox)

    def test_choosing_all_branches_yields_none(self, app, conn):
        """`None` es lo que el caso de uso entiende por "todas"; "" o un texto
        vacío no lo son."""
        dialog = ProductPriceFormDialog(
            list_options=[("l1", "BASE · Base")],
            branch_options=_presenter(conn).branch_options())
        dialog._branch.set_current_id("")
        assert dialog.values()["branch_id"] is None

    def test_choosing_a_branch_yields_its_id(self, app, conn):
        dialog = ProductPriceFormDialog(
            list_options=[("l1", "BASE · Base")],
            branch_options=_presenter(conn).branch_options())
        assert dialog._branch.set_current_id("b1") is True
        assert dialog.values()["branch_id"] == "b1"

    def test_the_bulk_dialog_too(self, app, conn):
        dialog = BulkPriceDialog(
            list_options=[("l1", "BASE · Base")],
            category_options=[("c1", "Carnes")],
            branch_options=_presenter(conn).branch_options())
        assert isinstance(dialog._branch, SearchableComboBox)
        dialog._branch.set_current_id("b1")
        assert dialog.values()["branch_id"] == "b1"


class TestEditingDoesNotWidenTheScope:
    def test_editing_keeps_a_branch_that_is_not_in_the_offered_list(self, app, conn):
        """EL RIESGO SILENCIOSO.

        Si el precio que se edita está acotado a una sucursal fuera del alcance
        del usuario, dejar el combo en "Todas" y guardar NO modificaría ese
        precio: el caso de uso hace upsert por (lista, producto, sucursal), así
        que crearía un precio para TODAS las sucursales. La sucursal se añade a
        la lista para conservarla; no es una fuga, viene del renglón que el
        usuario acaba de abrir.
        """
        dialog = ProductPriceFormDialog(
            list_options=[("l1", "BASE · Base")],
            branch_options=_presenter(conn).branch_options(),
            initial={"price_list_id": "l1", "product_id": "p1",
                     "branch_id": "b2", "sale_price": "100", "min_price": None})
        assert dialog.values()["branch_id"] == "b2"

    def test_editing_an_all_branches_price_stays_all_branches(self, app, conn):
        dialog = ProductPriceFormDialog(
            list_options=[("l1", "BASE · Base")],
            branch_options=_presenter(conn).branch_options(),
            initial={"price_list_id": "l1", "product_id": "p1",
                     "branch_id": None, "sale_price": "100", "min_price": None})
        assert dialog.values()["branch_id"] is None
