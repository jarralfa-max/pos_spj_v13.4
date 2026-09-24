"""SUP-6 — un solo contrato de búsqueda de proveedores, y un solo maestro.

Lo que se prueba aquí es lo que estaba roto de verdad: **el módulo de Proveedores
y Compras buscaban en tablas distintas y devolvían conjuntos disjuntos**, así que
un proveedor dado de alta y aprobado hoy no se podía elegir al crear una compra.

`test_the_module_and_purchasing_see_the_same_suppliers` es el caso central: es la
afirmación que fallaba antes del corte.
"""

import importlib
import sqlite3

import pytest

from backend.application.procurement.queries.direct_purchase_read_services import (
    SupplierPickerQueryService,
)
from backend.application.suppliers.queries.supplier_read_services import (
    SearchSuppliersQueryService,
)
from backend.application.suppliers.queries.supplier_search_query_service import (
    SearchProcurementSuppliersQueryService,
    SupplierDirectorySearchQueryService,
    SupplierSearchQuery,
    normalize_supplier_text,
)
from backend.infrastructure.db.repositories.suppliers.base import normalize_name
from backend.infrastructure.db.schema.supplier_schema import create_supplier_schema
from backend.shared.ids import new_uuid

_263 = importlib.import_module("migrations.standalone.263_suppliers_legacy_into_master")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_supplier_schema(c)
    c.commit()
    yield c
    c.close()


def _alta(conn, *, id=None, code="PRV-000001", nombre="Carnes del Norte SA",
          status="ACTIVE", rfc=None, trade=""):
    """Alta por la vía canónica (lo que hace el módulo de Proveedores)."""
    supplier_id = id or new_uuid()
    conn.execute(
        "INSERT INTO supplier_master (id, supplier_code, legal_name, trade_name,"
        " normalized_name, tax_identifier, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,datetime('now'),datetime('now'))",
        (supplier_id, code, nombre, trade, normalize_name(nombre), rfc, status))
    conn.commit()
    return supplier_id


def _bloquear(conn, supplier_id, block_type="PURCHASING_BLOCK", expires_at=None):
    conn.execute(
        "INSERT INTO supplier_blocks (id, supplier_id, block_type, reason,"
        " effective_at, expires_at, created_by_user_id, active)"
        " VALUES (?,?,?,'motivo','2020-01-01',?,'u1',1)",
        (new_uuid(), supplier_id, block_type, expires_at))
    conn.commit()


class TestTheSplitIsGone:
    def test_the_module_and_purchasing_see_the_same_suppliers(self, conn):
        """EL FALLO QUE MOTIVÓ TODO.

        Antes: el módulo leía `supplier_master` y Compras `proveedores`, sin
        ningún escritor en producción para la segunda. Los dos conjuntos eran
        disjuntos y el alta de hoy no se podía comprar.
        """
        sid = _alta(conn, nombre="Carnes del Norte SA")
        del_modulo = {r["id"] for r in SearchSuppliersQueryService(conn).search(query="Carnes")}
        de_compras = {r["id"] for r in SupplierPickerQueryService(conn).search("Carnes")}
        assert del_modulo == de_compras == {sid}

    def test_purchasing_no_longer_reads_the_legacy_table(self, conn):
        """Un proveedor que SÓLO existe en la tabla heredada, sin pasar por la
        migración, ya no aparece: la fuente es el maestro."""
        conn.execute("CREATE TABLE proveedores (id TEXT PRIMARY KEY, nombre TEXT,"
                     " activo INTEGER)")
        conn.execute("INSERT INTO proveedores VALUES ('viejo','Abarrotes Viejo',1)")
        conn.commit()
        assert SupplierPickerQueryService(conn).search("Abarrotes") == []


class TestOneSqlBuilder:
    def test_the_presets_only_add_restrictions(self, conn):
        """El módulo ve borradores; Compras no. Misma consulta, distinto preset."""
        _alta(conn, code="PRV-000001", nombre="Aprobado SA", status="ACTIVE")
        _alta(conn, code="PRV-000002", nombre="Borrador SA", status="DRAFT")
        _alta(conn, code="PRV-000003", nombre="De Baja SA", status="INACTIVE")

        directorio = {s.legal_name for s in
                      SupplierDirectorySearchQueryService(conn).search(SupplierSearchQuery())}
        compras = {s.legal_name for s in
                   SearchProcurementSuppliersQueryService(conn).search(SupplierSearchQuery())}
        assert directorio == {"Aprobado SA", "Borrador SA", "De Baja SA"}
        # Compras excluye lo que ya no opera, pero NO el borrador: un preset
        # sólo añade la restricción que declara.
        assert compras == {"Aprobado SA", "Borrador SA"}

    def test_a_preset_cannot_be_relaxed_by_the_caller(self, conn):
        """`restrict` sólo enciende banderas. Si un módulo exigió algo, otro no
        puede apagarlo pidiéndolo en la consulta."""
        _alta(conn, nombre="De Baja SA", status="INACTIVE")
        servicio = SearchProcurementSuppliersQueryService(conn)
        resultado = servicio.search(SupplierSearchQuery(active_only=False))
        assert resultado == []


class TestNormalization:
    def test_the_search_normalizes_exactly_like_the_master_persists(self):
        """CONTRATO: si las dos normalizaciones divergen, la rama normalizada de
        la búsqueda deja de acertar y nadie se entera — que es justo lo que
        pasaba antes."""
        for texto in ("Carnes del Norte S.A.", "JALAPEÑO", "Ábaco  y   Cía",
                      "  espacios  ", "Ñandú-99"):
            assert normalize_supplier_text(texto) == normalize_name(texto)

    def test_searching_with_spaces_and_accents_now_matches(self, conn):
        """LA RAMA QUE NO ACERTABA NUNCA.

        El maestro guarda `carnesdelnortesa`; la búsqueda anterior comparaba
        contra `%carnes del norte%` y no coincidía jamás. Aquí se comprueba
        contra un nombre cuyo `legal_name` NO contiene el término tal cual, así
        que sólo puede encontrarse por el normalizado.
        """
        _alta(conn, nombre="Cárnes, del Nórte S.A.")
        encontrados = SupplierDirectorySearchQueryService(conn).search(
            SupplierSearchQuery(text="carnes del norte"))
        assert [s.legal_name for s in encontrados] == ["Cárnes, del Nórte S.A."]

    def test_the_code_and_the_tax_id_are_also_searchable(self, conn):
        _alta(conn, code="PRV-000042", nombre="Acme SA", rfc="AAA010101AAA")
        servicio = SupplierDirectorySearchQueryService(conn)
        assert len(servicio.search(SupplierSearchQuery(text="PRV-000042"))) == 1
        assert len(servicio.search(SupplierSearchQuery(text="AAA010101"))) == 1


class TestBlocks:
    def test_a_blocked_supplier_is_listed_but_flagged(self, conn):
        """Compras los MUESTRA etiquetados; esconderlos dejaría al comprador sin
        saber por qué falta un proveedor que sabe que existe."""
        sid = _alta(conn, nombre="Bloqueado SA")
        _bloquear(conn, sid, "PURCHASING_BLOCK")
        encontrados = SearchProcurementSuppliersQueryService(conn).search(
            SupplierSearchQuery())
        assert [s.supplier_id for s in encontrados] == [sid]
        assert encontrados[0].purchasing_blocked is True

    def test_the_two_block_kinds_are_projected_separately(self, conn):
        compras = _alta(conn, code="PRV-000001", nombre="Sin Compras SA")
        pago = _alta(conn, code="PRV-000002", nombre="Sin Pago SA")
        _bloquear(conn, compras, "PURCHASING_BLOCK")
        _bloquear(conn, pago, "PAYMENT_BLOCK")
        por_id = {s.supplier_id: s for s in
                  SupplierDirectorySearchQueryService(conn).search(SupplierSearchQuery())}
        assert por_id[compras].purchasing_blocked and not por_id[compras].payment_blocked
        assert por_id[pago].payment_blocked and not por_id[pago].purchasing_blocked

    def test_a_payment_block_also_prevents_purchasing(self, conn):
        """Regla heredada que se preserva a propósito: no se compra a quien no
        se le puede pagar. En el modelo viejo lo hacía `bloqueado_financiero`."""
        sid = _alta(conn, nombre="Sin Pago SA")
        _bloquear(conn, sid, "PAYMENT_BLOCK")
        assert SupplierDirectorySearchQueryService(conn).is_purchasable(sid) is False

    def test_an_expired_block_does_not_count(self, conn):
        sid = _alta(conn, nombre="Ya Desbloqueado SA")
        _bloquear(conn, sid, "PURCHASING_BLOCK", expires_at="2020-06-01 00:00:00")
        assert SupplierDirectorySearchQueryService(conn).is_purchasable(sid) is True

    def test_a_draft_supplier_is_never_purchasable(self, conn):
        sid = _alta(conn, nombre="Borrador SA", status="DRAFT")
        assert SupplierDirectorySearchQueryService(conn).is_purchasable(sid) is False

    def test_is_purchasable_is_false_for_an_unknown_supplier(self, conn):
        servicio = SupplierDirectorySearchQueryService(conn)
        assert servicio.is_purchasable("no-existe") is False
        assert servicio.exists("no-existe") is False


class TestExplainEmpty:
    def test_no_suppliers_at_all(self, conn):
        razon = SupplierDirectorySearchQueryService(conn).explain_empty(
            SupplierSearchQuery(text="lo que sea"))
        assert razon.code == "SIN_PROVEEDORES"

    def test_there_are_suppliers_but_none_active(self, conn):
        _alta(conn, nombre="Borrador SA", status="DRAFT")
        razon = SearchProcurementSuppliersQueryService(conn).explain_empty(
            SupplierSearchQuery(text="Borrador", status="ACTIVE"))
        assert razon.code == "SIN_APROBAR"

    def test_the_term_simply_does_not_match(self, conn):
        _alta(conn, nombre="Carnes del Norte SA")
        razon = SupplierDirectorySearchQueryService(conn).explain_empty(
            SupplierSearchQuery(text="zzzzz"))
        assert razon.code == "NO_COINCIDE"

    def test_everything_is_blocked_for_purchasing(self, conn):
        sid = _alta(conn, nombre="Bloqueado SA")
        _bloquear(conn, sid, "PURCHASING_BLOCK")
        razon = SupplierDirectorySearchQueryService(conn).explain_empty(
            SupplierSearchQuery(text="Bloqueado", purchasable_only=True))
        assert razon.code == "BLOQUEADOS_PARA_COMPRAS"

    def test_none_when_there_are_results(self, conn):
        _alta(conn, nombre="Carnes del Norte SA")
        assert SupplierDirectorySearchQueryService(conn).explain_empty(
            SupplierSearchQuery(text="Carnes")) is None


class TestDegradation:
    def test_a_reduced_master_does_not_blow_up_the_search(self):
        """Hay fixtures y bases antiguas con un `supplier_master` mínimo.
        Seleccionar una columna inexistente lanzaría `OperationalError`, y el
        consumidor lo atrapa devolviendo []: búsqueda vacía en silencio."""
        c = sqlite3.connect(":memory:")
        c.row_factory = sqlite3.Row
        c.execute("CREATE TABLE supplier_master (id TEXT PRIMARY KEY, legal_name TEXT)")
        c.execute("INSERT INTO supplier_master VALUES ('s1','Acme SA')")
        c.commit()
        encontrados = SupplierDirectorySearchQueryService(c).search(
            SupplierSearchQuery(text="Acme"))
        assert [s.supplier_id for s in encontrados] == ["s1"]
        assert encontrados[0].purchasing_blocked is False
        c.close()

    def test_paging_is_honoured(self, conn):
        for i in range(1, 6):
            _alta(conn, code=f"PRV-00000{i}", nombre=f"Proveedor {i}")
        servicio = SupplierDirectorySearchQueryService(conn)
        pagina1 = servicio.search(SupplierSearchQuery(page=1, page_size=2))
        pagina2 = servicio.search(SupplierSearchQuery(page=2, page_size=2))
        assert len(pagina1) == len(pagina2) == 2
        assert {s.supplier_id for s in pagina1} & {s.supplier_id for s in pagina2} == set()
        assert servicio.count(SupplierSearchQuery()) == 5


class TestTheScreenExplainsItself:
    """El estado vacío del listado decía SIEMPRE "No hay proveedores que
    coincidan", incluso cuando el catálogo estaba vacío o cuando ninguno estaba
    aprobado. Tres situaciones con tres acciones distintas, presentadas como
    una."""

    def _presenter(self, conn):
        from frontend.desktop.modules.finance.suppliers.supplier_presenter import (
            SupplierPresenter,
        )
        return SupplierPresenter(
            connection_provider=lambda: conn,
            query_services={"search": SearchSuppliersQueryService(conn)},
            use_cases={})

    def test_it_says_there_are_no_suppliers_yet(self, conn):
        # "todavía" y no "no hay proveedores": el mensaje de RESPALDO (el que
        # devuelve el `except`) también contiene lo segundo, así que afirmarlo
        # dejaba pasar el caso en el que la consulta real falla.
        mensaje = self._presenter(conn).suppliers_empty_reason()
        assert "todavía" in mensaje.lower()

    def test_it_says_none_are_approved_yet(self, conn):
        _alta(conn, nombre="Borrador SA", status="DRAFT")
        mensaje = self._presenter(conn).suppliers_empty_reason(status="ACTIVE")
        assert "activo" in mensaje.lower()

    def test_it_says_the_term_does_not_match(self, conn):
        _alta(conn, nombre="Carnes del Norte SA")
        mensaje = self._presenter(conn).suppliers_empty_reason(search="zzzzz")
        assert "coincide" in mensaje.lower()
