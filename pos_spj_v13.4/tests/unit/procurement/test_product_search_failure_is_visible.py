"""§35 en Compras: un fallo de búsqueda no puede verse como "sin resultados".

Los dos presentadores de Compras envolvían `product_options` en un
`except Exception: return []`. Eso anulaba el mecanismo que `EntitySearchInput`
ya tiene (fila de estado + señal `search_failed`, probado en
`tests/unit/test_phase3_ui_components.py`) y hacía que una sesión sin sucursal
activa —o un error real de SQL— se presentara al comprador como un catálogo
vacío, sin ninguna pista de que la búsqueda ni siquiera llegó a ejecutarse.
"""

import sqlite3

import pytest

from backend.application.procurement.permissions import PurchasePermissions
from frontend.desktop.modules.purchasing.direct_purchase_presenter import (
    DirectPurchasePresenter,
)
from frontend.desktop.modules.purchasing.enterprise_presenter import (
    EnterprisePurchasingPresenter,
)


class Session:
    is_active = True
    user_id = "user-1"
    active_branch_id = "branch-1"
    sucursal_nombre = "Sucursal Centro"

    def tiene_permiso(self, code):
        return code == PurchasePermissions.DIRECT_CREATE


class _CatalogoQueTruena:
    """Lo que pasa de verdad cuando el esquema no está donde se espera."""

    def search(self, query, *, branch_id=None, limit=20):
        raise sqlite3.OperationalError("no such table: products")


class _CatalogoVacio:
    def search(self, query, *, branch_id=None, limit=20):
        return []


def _enterprise(session, catalog):
    return EnterprisePurchasingPresenter(
        connection_provider=lambda: None, read_services={}, analytics=None,
        use_cases={}, session_context=session, product_catalog=catalog)


def _direct(session, catalog):
    return DirectPurchasePresenter(
        connection_provider=lambda: None, read_service=None, supplier_picker=None,
        use_cases={}, session_context=session, product_catalog=catalog)


@pytest.mark.parametrize("build", [_enterprise, _direct])
def test_un_fallo_de_sql_no_se_disfraza_de_lista_vacia(build):
    presenter = build(Session(), _CatalogoQueTruena())
    with pytest.raises(sqlite3.OperationalError):
        presenter.product_options("pollo")


class _CatalogoQueAnota:
    def __init__(self):
        self.branch_ids = []

    def search(self, query, *, branch_id=None, limit=20):
        self.branch_ids.append(branch_id)
        return []


@pytest.mark.parametrize("build", [_enterprise, _direct])
def test_sin_sucursal_activa_la_busqueda_es_global(build):
    """Las compras son GLOBALES (decisión del usuario 2026-09-25): sin sucursal
    se busca igual en todo el catálogo; la sucursal sólo sirve para marcar lo
    no habilitado. Antes una sesión sin sucursal no podía buscar."""
    session = Session()
    session.active_branch_id = ""
    catalogo = _CatalogoQueAnota()
    assert build(session, catalogo).product_options("pollo") == []
    assert catalogo.branch_ids == [None]


@pytest.mark.parametrize("build", [_enterprise, _direct])
def test_sin_catalogo_inyectado_sigue_devolviendo_vacio(build):
    """Contrato intacto: no tener catálogo cableado no es un fallo, es no
    tener la función disponible."""
    assert build(Session(), None).product_options("pollo") == []


@pytest.mark.parametrize("build", [_enterprise, _direct])
def test_cero_coincidencias_reales_siguen_siendo_lista_vacia(build):
    assert build(Session(), _CatalogoVacio()).product_options("pollo") == []
