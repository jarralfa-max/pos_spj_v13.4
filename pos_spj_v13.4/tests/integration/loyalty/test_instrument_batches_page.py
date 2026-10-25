"""La pantalla «Lotes de vales y cupones» de Fidelidad, por el presenter REAL
(auditoría de Fidelidad 968e0bc, ampliación): una persona crea y envía, otra
aprueba, imprime el pliego en PDF y activa; una pieza extraviada se retira y se
repone con código nuevo. La tabla nunca muestra el código completo.
"""

from __future__ import annotations

import os
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")
pytest.importorskip("reportlab")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from tests.integration.loyalty.test_loy29_fidelidad_end_to_end import (  # noqa: E402,F401
    _ok,
    conn,
    template_db,
    two_users,
)


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


def _page(presenter, *, pdf_path, form_values=None, text="extraviado"):
    from frontend.desktop.modules.fidelidad.pages.instrument_batches_page import (
        InstrumentBatchesPage,
        _Dialogs,
    )

    class _Form:
        def __init__(self, definitions, branch_id, parent):
            self.definitions = definitions

        def exec_(self):
            return 1

        def values(self):
            datos = dict(form_values)
            datos["definition_id"] = self.definitions["VOUCHER"][0][0]
            return datos

    dialogos = _Dialogs()
    dialogos.batch_form = _Form
    dialogos.ask_text = staticmethod(lambda *_a: text)
    dialogos.save_pdf = staticmethod(lambda *_a: str(pdf_path))
    dialogos.confirm = staticmethod(lambda *_a: True)
    pagina = InstrumentBatchesPage(presenter, dialogs=dialogos)
    pagina.ensure_loaded()
    return pagina


def _select_first(table):
    table.selectRow(0)


def test_batch_lifecycle_through_the_screen(app, conn, two_users, tmp_path):
    from backend.domain.commercial_instruments.enums import VoucherType

    a, b = two_users
    _ok(a.run_command("create_voucher_definition", code="REGALO", name="Vale de regalo",
                      voucher_type=VoucherType.PROMOTIONAL_VOUCHER))
    pdf = tmp_path / "pliego.pdf"
    valores = {"kind": "VOUCHER", "name": "Navidad", "quantity": 12,
               "funding_source": "THIRD_PARTY", "valid_to": None, "branch_ids": (),
               "unit_value": Decimal("100"), "redemption_mode": "MULTI_EVENT",
               "max_redemptions": None, "max_percent_per_sale": Decimal("20"),
               "percent_base": "GROSS", "leftover_policy": "REQUIRE_FULL_USE"}
    creador = _page(a, pdf_path=pdf, form_values=valores)
    aprobador = _page(b, pdf_path=pdf, form_values=valores)

    creador._create()
    assert creador.batches_table.rowCount() == 1, creador.status_label.text()
    _select_first(creador.batches_table)
    creador._submit()

    # Quien crea no aprueba: el backend lo rechaza y la pantalla lo dice.
    _select_first(creador.batches_table)
    creador._approve()
    assert "no puede aprobarlo" in creador.status_label.text()

    aprobador.refresh()
    _select_first(aprobador.batches_table)
    aprobador._approve()
    _select_first(aprobador.batches_table)
    aprobador._print()
    assert pdf.exists() and pdf.read_bytes().startswith(b"%PDF")
    assert "12 piezas" in aprobador.status_label.text()
    _select_first(aprobador.batches_table)
    aprobador._activate()
    assert "activo" in aprobador.status_label.text().lower()

    _select_first(aprobador.batches_table)
    assert aprobador.pieces_table.rowCount() == 12
    codigos = [aprobador.pieces_table.item(fila, 2).text()
               for fila in range(aprobador.pieces_table.rowCount())]
    assert all(c.endswith("…") and len(c) <= 7 for c in codigos)

    # Retirar una pieza y reponerla: imprime sólo esa, con su código nuevo.
    reposicion = tmp_path / "reposicion.pdf"
    aprobador.dialogs.save_pdf = staticmethod(lambda *_a: str(reposicion))
    aprobador.pieces_table.selectRow(0)
    aprobador._revoke()
    assert reposicion.exists(), aprobador.status_label.text()
    assert "1 piezas" in aprobador.status_label.text()


def test_actions_are_hidden_without_permission(app, conn, tmp_path):
    from frontend.desktop.modules.fidelidad.composition import build_fidelidad_presenter
    from backend.shared.ids import new_uuid

    class _ReadOnly:
        user_id = new_uuid()
        active_branch_id = new_uuid()
        is_active = True

        def tiene_permiso(self, code):
            return code == "GROWTH_ENGINE.lote.ver"

    pagina = _page(build_fidelidad_presenter(conn, _ReadOnly()), pdf_path=tmp_path / "x.pdf",
                   form_values={})
    assert not any(boton.isVisibleTo(pagina) for boton in pagina.buttons.values())
