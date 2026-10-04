"""LOY-29 — la UI de Fidelidad ya no tiene letreros de "en construcción".

* Cada ruta del sidebar (§6, con Tarjetas DENTRO de Fidelidad) construye una
  página real; ninguna cae en un estado vacío de "próxima fase".
* Una ruta sólo se muestra con su propio permiso de lectura.
* Una acción de una página de registros abre su diálogo (sustituido aquí) y
  llama al caso de uso con los valores capturados.
* El diseñador valida con el dominio y guarda una versión nueva.
"""

from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from backend.shared.ids import new_uuid  # noqa: E402


@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PyQt5")
    from PyQt5.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    import migrations.m000_base_schema as base
    from backend.infrastructure.db.schema.commercial_instruments_schema import (
        create_commercial_instruments_schema,
    )
    from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema
    from backend.infrastructure.db.schema.loyalty_cards_schema import create_loyalty_cards_schema
    from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema
    from backend.infrastructure.db.schema.sweepstakes_schema import create_sweepstakes_schema

    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    base.up(c)
    for crear in (create_customers_crm_schema, create_loyalty_schema,
                  create_commercial_instruments_schema, create_sweepstakes_schema,
                  create_loyalty_cards_schema):
        crear(c)
    c.commit()
    yield c
    c.close()


class _Session:
    def __init__(self, permisos=None):
        self.user_id = new_uuid()
        self.active_branch_id = new_uuid()
        self.is_active = True
        self._permisos = permisos

    def tiene_permiso(self, code) -> bool:
        return self._permisos is None or code in self._permisos


def _workspace(conn, session):
    from frontend.desktop.modules.fidelidad.composition import create_fidelidad_view

    return create_fidelidad_view(conn, session)


def test_every_route_has_a_real_page_and_no_placeholder(app, conn):
    from PyQt5.QtWidgets import QLabel

    from frontend.desktop.modules.fidelidad.fidelidad_routes import FIDELIDAD_ROUTES

    w = _workspace(conn, _Session())
    assert set(w._route_index_by_id) == {r.route_id for r in FIDELIDAD_ROUTES}
    textos = " ".join(lbl.text() for lbl in w.findChildren(QLabel))
    assert "en construccion" not in textos.lower()
    assert "próxima fase" not in textos.lower()
    assert any(r.route_id.startswith("cards.") for r in FIDELIDAD_ROUTES)


def test_route_needs_its_own_read_permission(app, conn):
    from backend.application.loyalty.permissions import LoyaltyPermissions as LP

    w = _workspace(conn, _Session({LP.VIEW, LP.PROGRAM_VIEW}))
    # Las reglas de acumulación son parte de la definición del programa (2026-10-03).
    assert set(w._route_index_by_id) == {"fidelidad.overview", "loyalty.programs",
                                         "loyalty.rules"}


def test_record_action_runs_the_use_case_with_dialog_values(app, conn):
    from frontend.desktop.modules.fidelidad.records import catalog
    from frontend.desktop.modules.fidelidad.records.record_page import LoyaltyRecordPage
    from frontend.desktop.modules.fidelidad.composition import build_fidelidad_presenter
    from PyQt5.QtWidgets import QDialog

    presenter = build_fidelidad_presenter(conn, _Session())
    page = LoyaltyRecordPage(presenter, catalog.PROGRAMS)

    class _Dialog:
        def __init__(self, *_a, **_k):
            pass

        def exec_(self):
            return QDialog.Accepted

        def values(self):
            return {"code": "P1", "name": "Puntos SPJ", "currency_name": "Puntos"}

    page.dialogs.action = _Dialog
    crear = next(a for a in catalog.PROGRAMS.actions if a.command == "create_program")
    page.run_action(crear)
    page.reload()
    assert page.table.rowCount() == 1
    assert "creado" in page._notice.text().lower()


def test_designer_validates_and_saves_a_new_version(app, conn):
    from backend.application.loyalty.queries.records_query_service import LoyaltyRecord as R
    from frontend.desktop.modules.fidelidad.cards.designer_page import CardDesignerPage
    from frontend.desktop.modules.fidelidad.composition import build_fidelidad_presenter
    from backend.domain.loyalty_cards.enums import LoyaltyCardTemplateTargetType

    presenter = build_fidelidad_presenter(conn, _Session())
    assert presenter.run_command(
        "create_card_template", code="T1", name="Clásica",
        target_type=LoyaltyCardTemplateTargetType.PHYSICAL).success
    page = CardDesignerPage(presenter)
    page.ensure_loaded()
    template_id = presenter.records(R.CARD_TEMPLATES).rows[0]["id"]
    page.template.set_current_id(template_id)
    page.load_design()
    page.add_element("VARIABLE")
    page.add_element("QR")
    page.face.set_current_id("back_elements")
    page.add_element("BARCODE")
    assert page.validate()
    page.save()
    versiones = presenter.records(R.CARD_TEMPLATE_VERSIONS).rows
    assert len(versiones) == 1
    import json
    guardado = presenter.card_design(template_id)
    esquema = json.loads(guardado[1])
    assert len(esquema["elements"]) == 2 and len(esquema["back_elements"]) == 1


def test_generated_pdf_is_offered_and_saved(app, conn, tmp_path):
    """El PDF de un lote se generaba y se descartaba; ahora se entrega."""
    from types import SimpleNamespace

    from frontend.desktop.modules.fidelidad.cards.cards_catalog import PRINT_JOBS
    from frontend.desktop.modules.fidelidad.composition import build_fidelidad_presenter
    from frontend.desktop.modules.fidelidad.records.record_page import LoyaltyRecordPage

    presenter = build_fidelidad_presenter(conn, _Session())
    page = LoyaltyRecordPage(presenter, PRINT_JOBS)
    destino = tmp_path / "lote.pdf"
    page.dialogs.save_pdf = lambda _parent, _sugerido: str(destino)
    resultado = SimpleNamespace(success=True, message="PDF de lote renderizado",
                                data={"pdf_bytes": b"%PDF-1.4 prueba"})
    mensaje = page._deliver_pdf(resultado, "Impresión generada.")
    assert destino.read_bytes() == b"%PDF-1.4 prueba"
    assert str(destino) in mensaje
    page.dialogs.save_pdf = lambda _parent, _sugerido: None
    assert "no se guardó" in page._deliver_pdf(resultado, "Impresión generada.")


def test_authorizer_field_verifies_credentials_through_the_presenter(app):
    from frontend.desktop.modules.fidelidad.records.action_dialog import ActionDialog
    from frontend.desktop.modules.fidelidad.records.specs import ActionSpec, FieldKind, FieldSpec

    class _Presenter:
        def verify_authorizer(self, usuario, clave):
            return ("id-gerente", "") if clave == "buena" else (None, "Clave incorrecta.")

    accion = ActionSpec("adjust_points", "Ajustar", "x", fields=(
        FieldSpec("authorizer_user_id", "Autoriza", FieldKind.AUTHORIZER),))
    dialogo = ActionDialog(accion, _Presenter())
    campo = dialogo._widgets["authorizer_user_id"]
    campo.user.setText("gerente")
    campo.password.setText("mala")
    assert dialogo.values() is None
    campo.password.setText("buena")
    assert dialogo.values() == {"authorizer_user_id": "id-gerente"}
