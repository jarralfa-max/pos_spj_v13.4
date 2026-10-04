"""Flujo de listas de precio y captura de precios por producto (2026-10-03).

Lo que se medía en la base real antes de este cambio: `BASE01` ACTIVA con cero
precios, ningún precio capturado en todo el módulo, y ninguna forma de
completarla desde la pantalla. Causas, todas cerradas aquí y fijadas por estas
pruebas:

* activar (y aprobar) una lista vacía estaba permitido, y una lista activa es
  inmutable: quedaba vacía para siempre y, si era base, retiraba a la anterior;
* la captura individual y el lote aplicaban reglas distintas de estado, permiso
  y alcance, y la escala por volumen no miraba el estado de la lista;
* fijar un precio por sucursal cuando existía el general reventaba con
  `IntegrityError` (se reutilizaba el id de la fila general);
* editar la vigencia de un precio existente respondía éxito y no la guardaba;
* el catálogo del POS leía la lista con código 'BASE' sin mirar su estado, así
  que tras reemplazar la lista base mostraba los precios de la retirada.
"""

from __future__ import annotations

import importlib
import sqlite3
from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.application.pricing.authorization.policy import PricingAuthorizationPolicy
from backend.application.pricing.permissions import PricingPermissions
from backend.application.pricing.queries.pricing_read_facade import PricingReadFacade
from backend.application.pricing.queries.pricing_read_service import PricingReadService
from backend.application.pricing.use_cases import (
    ActivatePriceListUseCase,
    ApplyPriceToSelectionUseCase,
    ApprovePriceListUseCase,
    CreatePriceListUseCase,
    DuplicatePriceListUseCase,
    SetProductPriceUseCase,
    SetVolumePriceUseCase,
    SubmitPriceListUseCase,
)
from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.enums import PriceListKind, PriceListStatus
from backend.domain.pricing.exceptions import UnknownPriceListStatusError
from backend.infrastructure.db.repositories.pricing.pricing_repository import (
    PricingRepository,
)
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.shared.ids import new_uuid
from frontend.desktop.modules.pricing.presenter import PricingPresenter
from frontend.desktop.modules.pricing.view_models import (
    list_publication_es,
    list_status_es,
    product_prices_table,
    validity_es,
)

_150 = importlib.import_module("migrations.standalone.150_pricing_backfill_from_legacy")
_299 = importlib.import_module("migrations.standalone.299_price_list_status_integrity")

# Fechas LEJANAS respecto de hoy: con "mañana" la prueba fallaba si la corrida
# cruzaba la medianoche (el precio programado pasaba a regir).
HOY = date.today()
AYER = (HOY - timedelta(days=30)).isoformat()
MANANA = (HOY + timedelta(days=30)).isoformat()


class _Concede:
    """Verificador con permisos EXACTOS (o todos, con `*`)."""

    def __init__(self, *codes):
        self._codes = set(codes)

    def has_permission(self, _user_id, code):
        return "*" in self._codes or code in self._codes


def _auth(*codes) -> PricingAuthorizationPolicy:
    return PricingAuthorizationPolicy(_Concede(*(codes or ("*",))))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_pricing_schema(c)
    c.commit()
    yield c
    c.close()


def _op():
    return new_uuid()


def _crear(conn, *, code="LISTA-1", kind="BASE", actor="capturista"):
    r = CreatePriceListUseCase(_auth()).execute(
        conn, actor_user_id=actor, code=code, name=f"Lista {code}", kind=kind,
        operation_id=_op())
    assert r.success, r.message
    return r.entity_id


def _precio(conn, lista, producto="p1", precio="100", actor="capturista", **extra):
    return SetProductPriceUseCase(_auth()).execute(
        conn, actor_user_id=actor, price_list_id=lista, product_id=producto,
        sale_price=precio, operation_id=_op(), **extra)


def _enviar(conn, lista, actor="capturista"):
    return SubmitPriceListUseCase(_auth()).execute(
        conn, actor_user_id=actor, price_list_id=lista, operation_id=_op())


def _aprobar(conn, lista, actor="jefe"):
    return ApprovePriceListUseCase(_auth()).execute(
        conn, actor_user_id=actor, price_list_id=lista, operation_id=_op())


def _activar(conn, lista, actor="jefe"):
    return ActivatePriceListUseCase(_auth()).execute(
        conn, actor_user_id=actor, price_list_id=lista, operation_id=_op())


def _publicar(conn, lista):
    """Revisión → aprobación → activación, con segregación (otro usuario)."""
    for paso in (_enviar(conn, lista), _aprobar(conn, lista), _activar(conn, lista)):
        assert paso.success, paso.message


def _estado(conn, lista) -> str:
    return conn.execute("SELECT status FROM price_list WHERE id=?",
                        (lista,)).fetchone()[0]


def _lista_directa(conn, *, code, status, kind="BASE") -> str:
    """Una lista ya existente en un estado dado (dato heredado/legacy)."""
    lst = PriceList(code=code, name=code, kind=PriceListKind(kind),
                    status=PriceListStatus(status))
    PricingRepository(conn).save_list(lst)
    conn.commit()
    return lst.id


# ── 1-3. captura según el estado de la lista ─────────────────────────────────
def test_borrador_recibe_precio(conn):
    lista = _crear(conn)
    r = _precio(conn, lista)
    assert r.success, r.message
    assert PricingRepository(conn).get_price_row(
        price_list_id=lista, product_id="p1", branch_id=None).sale_price.amount == 100


def test_en_revision_sigue_recibiendo_precios(conn):
    """Política vigente: En revisión acepta precios (y puede volver a Borrador)."""
    lista = _crear(conn)
    assert _enviar(conn, lista).success
    r = _precio(conn, lista, "p2", "55")
    assert r.success, r.message


@pytest.mark.parametrize("status", ["APPROVED", "ACTIVE", "INACTIVE"])
def test_lista_de_solo_lectura_rechaza_y_explica_la_salida(conn, status):
    lista = _lista_directa(conn, code=f"RO-{status}", status=status)

    individual = _precio(conn, lista)
    lote = ApplyPriceToSelectionUseCase(_auth()).execute(
        conn, actor_user_id="u1", price_list_id=lista, sale_price="10",
        product_ids=["p1"], operation_id=_op())

    for r in (individual, lote):
        assert not r.success and r.error_code == "IMMUTABLE_LIST"
        assert r.data["recovery"] == "DUPLICATE"
        assert r.data["list_status"] == status
        assert "duplícala" in r.message.lower()
    assert PricingRepository(conn).prices_of_list(lista) == []


def test_una_lista_inactiva_ya_no_es_editable_en_el_dominio(conn):
    """Antes `is_editable` era "no aprobada ni activa", así que una lista
    INACTIVA —historia— aceptaba precios aunque la pantalla no la ofreciera."""
    lst = PriceList(code="X", name="X", kind=PriceListKind.BASE,
                    status=PriceListStatus.INACTIVE)
    assert not lst.is_editable


def test_escala_por_volumen_respeta_el_estado_de_la_lista(conn):
    lista = _crear(conn)
    precio = _precio(conn, lista)
    _publicar(conn, lista)

    r = SetVolumePriceUseCase(_auth()).execute(
        conn, actor_user_id="u1", product_price_id=precio.entity_id,
        min_quantity="10", price="90", operation_id=_op())

    assert not r.success and r.error_code == "IMMUTABLE_LIST"
    assert PricingRepository(conn).volume_tiers(precio.entity_id) == []


# ── 4. no se activa (ni se aprueba) una lista vacía ──────────────────────────
def test_no_se_aprueba_una_lista_vacia_y_dice_como_completarla(conn):
    lista = _crear(conn)
    _enviar(conn, lista)

    r = _aprobar(conn, lista)

    assert not r.success and r.error_code == "EMPTY_LIST"
    assert "Captura al menos un precio" in r.message
    assert _estado(conn, lista) == "UNDER_REVIEW"   # no cambió nada


def test_no_se_activa_una_lista_aprobada_vacia(conn):
    """Listas aprobadas vacías ANTES de esta regla: la salida es duplicar."""
    lista = _lista_directa(conn, code="APROBADA-VACIA", status="APPROVED")

    r = _activar(conn, lista)

    assert not r.success and r.error_code == "EMPTY_LIST"
    assert "duplícala" in r.message
    assert _estado(conn, lista) == "APPROVED"


def test_no_se_activa_una_lista_con_todos_sus_precios_vencidos(conn):
    lista = _crear(conn)
    assert _precio(conn, lista, effective_from="2020-01-01", effective_to=AYER).success
    _enviar(conn, lista)

    r = _aprobar(conn, lista)

    assert not r.success and r.error_code == "EMPTY_LIST"
    assert "vencieron" in r.message


def test_un_precio_programado_si_cuenta_para_activar(conn):
    lista = _crear(conn)
    assert _precio(conn, lista, effective_from=MANANA).success
    _publicar(conn, lista)
    assert _estado(conn, lista) == "ACTIVE"


def test_activar_un_borrador_sigue_siendo_error_de_estado(conn):
    """La regla de contenido corre DESPUÉS de la de transición."""
    lista = _crear(conn)
    r = _activar(conn, lista)
    assert not r.success and r.error_code == "INVALID_STATE"


# ── 5. ciclo completo con precios ────────────────────────────────────────────
def test_lista_con_precios_pasa_revision_aprobacion_y_activacion(conn):
    lista = _crear(conn)
    assert _precio(conn, lista).success
    assert _enviar(conn, lista).success
    assert _aprobar(conn, lista).success
    assert _activar(conn, lista).success
    assert _estado(conn, lista) == "ACTIVE"


# ── 6. duplicar una lista activa ─────────────────────────────────────────────
def test_duplicar_una_activa_da_un_borrador_editable_con_sus_precios(conn):
    origen = _crear(conn, code="BASE01")
    assert _precio(conn, origen, "p1", "100").success
    assert _precio(conn, origen, "p1", "95", branch_id="suc-1").success
    assert _precio(conn, origen, "p2", "50", effective_from=MANANA).success
    _publicar(conn, origen)

    copia = DuplicatePriceListUseCase(_auth()).execute(
        conn, actor_user_id="capturista", source_list_id=origen, code="BASE02",
        name="Base 2", operation_id=_op())

    assert copia.success, copia.message
    assert copia.data["source_status"] == "ACTIVE" and copia.data["copied_prices"] == 3
    repo = PricingRepository(conn)
    assert repo.get_list(copia.entity_id).status is PriceListStatus.DRAFT
    copiados = {(p.product_id, p.branch_id): p for p in repo.prices_of_list(copia.entity_id)}
    assert copiados[("p1", None)].sale_price.amount == Decimal("100")
    assert copiados[("p1", "suc-1")].sale_price.amount == Decimal("95")
    assert copiados[("p2", None)].effective_from == MANANA

    # Se edita en la copia; la original activa no cambia.
    assert _precio(conn, copia.entity_id, "p1", "110").success
    assert repo.get_price_row(price_list_id=origen, product_id="p1",
                              branch_id=None).sale_price.amount == Decimal("100")


# ── 7. individual y lote: sucursal, permisos, vigencia ───────────────────────
def test_precio_por_sucursal_con_el_general_existente_no_revienta(conn):
    """Antes: `IntegrityError: UNIQUE constraint failed: product_price.id`."""
    lista = _crear(conn)
    assert _precio(conn, lista, "p1", "100").success

    r = _precio(conn, lista, "p1", "90", branch_id="suc-1")

    assert r.success, r.message
    repo = PricingRepository(conn)
    general = repo.get_price_row(price_list_id=lista, product_id="p1", branch_id=None)
    sucursal = repo.get_price_row(price_list_id=lista, product_id="p1", branch_id="suc-1")
    assert general.sale_price.amount == 100 and sucursal.sale_price.amount == 90
    assert general.id != sucursal.id
    # La bitácora no registra el general como "valor anterior" de la sucursal.
    fila = conn.execute("SELECT old_value FROM price_change_log WHERE branch_id='suc-1'"
                        ).fetchone()
    assert fila["old_value"] is None


def test_lote_por_sucursal_con_el_general_existente_no_revienta(conn):
    lista = _crear(conn)
    assert _precio(conn, lista, "p1", "100").success
    r = ApplyPriceToSelectionUseCase(_auth()).execute(
        conn, actor_user_id="u1", price_list_id=lista, sale_price="80",
        product_ids=["p1"], branch_id="suc-1", operation_id=_op())
    assert r.success and r.data["applied"] == 1


def test_editar_la_vigencia_de_un_precio_existente_se_guarda(conn):
    """Antes respondía "Precio actualizado" y la fila conservaba la vigencia
    anterior: el upsert no actualizaba `effective_from`/`effective_to`."""
    lista = _crear(conn)
    assert _precio(conn, lista, "p1", "100").success

    assert _precio(conn, lista, "p1", "100", effective_from="2026-11-01",
                   effective_to="2026-11-30").success
    fila = PricingRepository(conn).get_price_row(price_list_id=lista, product_id="p1",
                                                 branch_id=None)
    assert (fila.effective_from, fila.effective_to) == ("2026-11-01", "2026-11-30")

    # Quitar la programación también se guarda.
    assert _precio(conn, lista, "p1", "100").success
    fila = PricingRepository(conn).get_price_row(price_list_id=lista, product_id="p1",
                                                 branch_id=None)
    assert (fila.effective_from, fila.effective_to) == (None, None)


def test_el_lote_guarda_la_vigencia(conn):
    lista = _crear(conn)
    r = ApplyPriceToSelectionUseCase(_auth()).execute(
        conn, actor_user_id="u1", price_list_id=lista, sale_price="80",
        product_ids=["p1", "p2"], effective_from="2026-12-01",
        effective_to="2026-12-31", operation_id=_op())
    assert r.success, r.message
    assert {p.effective_to for p in PricingRepository(conn).prices_of_list(lista)} == {
        "2026-12-31"}


@pytest.mark.parametrize("desde,hasta", [("2026-12-31", "2026-12-01"),
                                          ("31/12/2026", None)])
def test_vigencia_invalida_se_rechaza_en_individual_y_en_lote(conn, desde, hasta):
    lista = _crear(conn)
    individual = _precio(conn, lista, effective_from=desde, effective_to=hasta)
    lote = ApplyPriceToSelectionUseCase(_auth()).execute(
        conn, actor_user_id="u1", price_list_id=lista, sale_price="80",
        product_ids=["p1"], effective_from=desde, effective_to=hasta,
        operation_id=_op())
    for r in (individual, lote):
        assert not r.success and r.error_code == "VALIDATION"
    assert PricingRepository(conn).prices_of_list(lista) == []


def test_el_precio_por_sucursal_exige_su_permiso_tambien_en_individual(conn):
    """El lote ya exigía `BRANCH_PRICE_MANAGE`; el individual no."""
    lista = _crear(conn)
    solo_editar = PricingAuthorizationPolicy(_Concede(PricingPermissions.PRICE_EDIT))

    sucursal = SetProductPriceUseCase(solo_editar).execute(
        conn, actor_user_id="u1", price_list_id=lista, product_id="p1",
        sale_price="90", branch_id="suc-1", operation_id=_op())
    general = SetProductPriceUseCase(solo_editar).execute(
        conn, actor_user_id="u1", price_list_id=lista, product_id="p1",
        sale_price="90", operation_id=_op())

    assert not sucursal.success and sucursal.error_code == "PERMISSION_DENIED"
    assert general.success, general.message


def test_el_lote_respeta_el_alcance_de_sucursales(conn):
    """El individual validaba el alcance; el lote no."""
    lista = _crear(conn)
    r = ApplyPriceToSelectionUseCase(_auth()).execute(
        conn, actor_user_id="u1", price_list_id=lista, sale_price="80",
        product_ids=["p1"], branch_id="suc-ajena", allowed_branches={"suc-1"},
        operation_id=_op())
    assert not r.success and r.error_code == "BRANCH_SCOPE"


def test_sin_permiso_de_edicion_no_se_captura_ni_en_lote(conn):
    lista = _crear(conn)
    sin_permiso = PricingAuthorizationPolicy(_Concede(PricingPermissions.VIEW))
    individual = SetProductPriceUseCase(sin_permiso).execute(
        conn, actor_user_id="u1", price_list_id=lista, product_id="p1",
        sale_price="9", operation_id=_op())
    lote = ApplyPriceToSelectionUseCase(sin_permiso).execute(
        conn, actor_user_id="u1", price_list_id=lista, sale_price="9",
        product_ids=["p1"], operation_id=_op())
    assert individual.error_code == lote.error_code == "PERMISSION_DENIED"


# ── 8. reemplazo de la lista base ────────────────────────────────────────────
def test_activar_una_base_con_precios_reemplaza_a_la_base_vacia(conn):
    """El escenario real: `BASE01` activa y vacía. La salida es duplicarla,
    capturar precios en la copia y activarla."""
    vacia = _lista_directa(conn, code="BASE01", status="ACTIVE")
    copia = DuplicatePriceListUseCase(_auth()).execute(
        conn, actor_user_id="capturista", source_list_id=vacia, code="BASE02",
        name="Base 2", operation_id=_op())
    assert copia.success and copia.data["copied_prices"] == 0
    assert _precio(conn, copia.entity_id, "p1", "120").success

    _publicar(conn, copia.entity_id)

    activas = conn.execute("SELECT code FROM price_list WHERE kind='BASE' "
                           "AND status='ACTIVE'").fetchall()
    assert [r[0] for r in activas] == ["BASE02"]
    assert _estado(conn, vacia) == "INACTIVE"          # historial, no borrada


def test_una_base_vacia_no_reemplaza_a_la_vigente(conn):
    vigente = _crear(conn, code="BASE-OK")
    assert _precio(conn, vigente).success
    _publicar(conn, vigente)
    vacia = _lista_directa(conn, code="BASE-VACIA", status="APPROVED")

    r = _activar(conn, vacia)

    assert not r.success and r.error_code == "EMPTY_LIST"
    assert _estado(conn, vigente) == "ACTIVE"


def test_la_base_impide_dos_listas_base_activas(conn):
    _lista_directa(conn, code="BASE-A", status="ACTIVE")
    with pytest.raises(sqlite3.IntegrityError):
        _lista_directa(conn, code="BASE-B", status="ACTIVE")
    # Las inactivas (historial) no cuentan.
    _lista_directa(conn, code="BASE-C", status="INACTIVE")
    _lista_directa(conn, code="BASE-D", status="INACTIVE")


# ── 9. estados heredados y migraciones ───────────────────────────────────────
def test_backfill_legacy_traduce_activa_a_estados_canonicos(conn):
    conn.execute("CREATE TABLE listas_precio (id TEXT PRIMARY KEY, nombre TEXT, "
                 "descuento_global REAL, activa INTEGER)")
    conn.execute("INSERT INTO listas_precio VALUES ('L1','Mayoreo',0,1), "
                 "('L2','Vieja',0,0)")
    _150.run(conn)
    estados = dict(conn.execute("SELECT id, status FROM price_list "
                                "WHERE id IN ('L1','L2')").fetchall())
    assert estados == {"L1": "ACTIVE", "L2": "INACTIVE"}
    assert conn.execute("SELECT status FROM price_list WHERE code='BASE'"
                        ).fetchone()[0] == "ACTIVE"


def _sin_indice(conn):
    """Una base ANTERIOR a la 299 (sin índice único)."""
    conn.execute("DROP INDEX IF EXISTS ux_price_list_single_active_base")


def _cruda(conn, code, status, kind="BASE"):
    conn.execute("INSERT INTO price_list (id, code, name, kind, status) "
                 "VALUES (?,?,?,?,?)", (new_uuid(), code, code, kind, status))


def test_299_normaliza_variantes_inequivocas_y_no_adivina_las_demas(conn):
    _sin_indice(conn)
    _cruda(conn, "A", "active", kind="CHANNEL")
    _cruda(conn, "B", " Draft ", kind="promotional")
    _cruda(conn, "C", "activa", kind="CUSTOMER")

    _299.run(conn)

    filas = {r["code"]: (r["status"], r["kind"]) for r in conn.execute(
        "SELECT code, status, kind FROM price_list")}
    assert filas["A"] == ("ACTIVE", "CHANNEL")
    assert filas["B"] == ("DRAFT", "PROMOTIONAL")
    assert filas["C"] == ("activa", "CUSTOMER")      # intacto: no se adivina


def test_299_reaplica_una_sola_base_activa_y_crea_el_indice(conn):
    _sin_indice(conn)
    _cruda(conn, "ORIGIN-00001", "ACTIVE")
    _cruda(conn, "BASE", "active")                   # destapa una segunda activa

    _299.run(conn)
    _299.run(conn)                                   # idempotente

    activas = [r[0] for r in conn.execute(
        "SELECT code FROM price_list WHERE kind='BASE' AND status='ACTIVE'")]
    assert activas == ["BASE"]                       # regla de la 284
    assert conn.execute("SELECT COUNT(*) FROM price_list").fetchone()[0] == 2
    assert conn.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND "
                        "name='ux_price_list_single_active_base'").fetchone()


def test_estado_no_reconocido_se_informa_con_el_valor_real(conn):
    _cruda(conn, "RARA", "publicada", kind="PROMOTIONAL")
    lista = conn.execute("SELECT id FROM price_list WHERE code='RARA'").fetchone()[0]

    with pytest.raises(UnknownPriceListStatusError) as exc:
        PricingRepository(conn).get_list(lista)
    assert exc.value.raw_status == "publicada"

    for r in (_precio(conn, lista), _activar(conn, lista),
              DuplicatePriceListUseCase(_auth()).execute(
                  conn, actor_user_id="u1", source_list_id=lista, code="X",
                  name="X", operation_id=_op())):
        assert not r.success and r.error_code == "UNKNOWN_STATUS"
        assert "publicada" in r.message


# ── 10. lo que ve la pantalla ────────────────────────────────────────────────
def _presenter(conn):
    return PricingPresenter(read_service_factory=lambda: PricingReadService(conn))


def test_el_selector_separa_editables_solo_lectura_y_no_reconocidas(conn):
    borrador = _crear(conn, code="BORR")
    _lista_directa(conn, code="BASE01", status="ACTIVE")
    _cruda(conn, "RARA", "publicada", kind="PROMOTIONAL")

    state = _presenter(conn).price_list_capture_state()

    assert [i for i, _ in state.editable] == [borrador]
    assert [l["status"] for l in state.read_only] == ["ACTIVE"]
    assert [l["raw_status"] for l in state.unrecognized] == ["publicada"]


def test_sin_listas_editables_el_mensaje_dice_crear_o_duplicar(conn):
    _lista_directa(conn, code="BASE01", status="ACTIVE")
    _cruda(conn, "RARA", "publicada", kind="PROMOTIONAL")
    p = _presenter(conn)

    msg = p.no_editable_lists_message()

    assert p.price_list_options() == []
    assert "La lista BASE01" in msg and "(Activa)" in msg and "duplícala" in msg
    assert "Nueva lista" in msg
    assert "«publicada»" in msg and "no reconocido" in msg


def test_editar_un_precio_de_lista_activa_no_se_presenta_como_no_reconocida():
    msg = PricingPresenter.read_only_list_message(
        {"list_status": "ACTIVE", "list_name": "Base"})
    assert "Activa" in msg and "duplícala" in msg
    assert "no reconocid" not in msg


def test_estado_no_reconocido_se_dice_tal_cual():
    msg = PricingPresenter.read_only_list_message(
        {"list_status": "active", "list_name": "Base"})
    assert "no reconocido" in msg and "«active»" in msg
    assert PricingPresenter.read_only_list_message({"list_status": "DRAFT"}) is None


def test_etiquetas_de_estado_publicacion_y_vigencia():
    assert list_status_es("UNDER_REVIEW") == "En revisión"
    assert list_status_es("activa") == "No reconocido («activa»)"
    assert "SIN precios" in list_publication_es("ACTIVE", "BASE", 0)
    assert list_publication_es("ACTIVE", "BASE", 3) == "Publicada · rige como lista base"
    assert "no puede activarse" in list_publication_es("APPROVED", "BASE", 0)
    hoy = date(2026, 10, 3)
    assert validity_es(None, None, today=hoy) == "Siempre"
    assert validity_es("2026-11-01", None, today=hoy).startswith("Programado")
    assert validity_es(None, "2026-10-01", today=hoy).startswith("Vencido")
    assert validity_es("2026-10-01", "2026-10-31", today=hoy).startswith("Vigente")


def test_la_tabla_de_precios_muestra_estado_de_lista_y_vigencia():
    t = product_prices_table([{"id": "pp1", "product_id": "p1", "sale_price": "10",
                               "list_name": "Base", "list_status": "ACTIVE",
                               "effective_from": None, "effective_to": None}])
    assert t.rows[0][5:] == ["Activa", "Siempre"]


def test_lista_activa_vacia_se_ve_en_listas_y_en_el_resumen(conn):
    _lista_directa(conn, code="BASE01", status="ACTIVE")
    fila = PricingReadService(conn).list_price_lists()[0]
    assert fila["price_count"] == 0 and fila["status_recognized"] is True
    kpis = {k.key: k for k in _presenter(conn).overview_kpis()}
    assert kpis["lists_active_empty"].value == "1"
    assert kpis["lists_active_empty"].variant == "danger"


def test_sugerencia_de_codigo_para_la_copia(conn):
    _lista_directa(conn, code="BASE01", status="ACTIVE")
    _lista_directa(conn, code="BASE01-2", status="INACTIVE")
    assert _presenter(conn).suggest_copy_code("BASE01") == "BASE01-3"


# ── 11. POS: el precio de la lista base activa tras la activación ────────────
@pytest.fixture
def pos_conn():
    from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
    from backend.infrastructure.db.schema.products_schema import create_products_schema
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    create_pricing_schema(c)
    create_inventory_schema(c)
    # Lo que dejó la instalación: una lista llamada 'BASE', activa y vacía.
    c.execute("INSERT INTO price_list (id, code, name, kind, status, discount_pct) "
              "VALUES (?, 'BASE', 'Lista base', 'BASE', 'ACTIVE', '0')", (new_uuid(),))
    c.execute("INSERT INTO products (id, code, name, product_type, base_unit_id, "
              "lifecycle_status) VALUES ('p1','A-1','Arrachera','SIMPLE','PZA','ACTIVE')")
    c.execute("INSERT INTO products (id, code, name, product_type, base_unit_id, "
              "lifecycle_status) VALUES ('p2','A-2','Chorizo','SIMPLE','PZA','ACTIVE')")
    c.commit()
    yield c
    c.close()


def _catalogo(conn, branch="suc-1"):
    from backend.application.sales.queries.catalog_query_service import (
        SalesCatalogQueryService,
    )
    return {e.product_id: e for e in
            SalesCatalogQueryService(conn).search(branch_id=branch)}


def test_el_catalogo_del_pos_lee_la_lista_base_activa_no_la_llamada_base(pos_conn):
    """Sin precios por sucursal ni vigencias: sólo el criterio de lista."""
    nueva = _crear(pos_conn, code="BASE02")
    assert _precio(pos_conn, nueva, "p1", "120").success
    _publicar(pos_conn, nueva)

    assert _estado(pos_conn, nueva) == "ACTIVE"
    entrada = _catalogo(pos_conn)["p1"]
    assert entrada.priced and entrada.effective_price == Decimal("120")


def test_el_pos_cobra_y_muestra_el_precio_de_la_nueva_lista_base(pos_conn):
    antes = _catalogo(pos_conn)
    assert not antes["p1"].priced

    nueva = _crear(pos_conn, code="BASE02")
    assert _precio(pos_conn, nueva, "p1", "120").success
    assert _precio(pos_conn, nueva, "p1", "110", branch_id="suc-1").success
    assert _precio(pos_conn, nueva, "p2", "80", effective_from=MANANA).success
    _publicar(pos_conn, nueva)

    # Cobro (fachada canónica que usa Ventas).
    facade = PricingReadFacade(pos_conn)
    assert facade.sale_price("p1").price == Decimal("120")
    assert facade.sale_price("p1", branch_id="suc-1").price == Decimal("110")
    assert facade.sale_price("p2").price is None            # programado: aún no rige

    # Catálogo del POS: MISMO criterio. Antes leía la lista 'BASE' (ya
    # retirada y vacía) y seguía diciendo "Sin precio".
    catalogo = _catalogo(pos_conn)
    assert catalogo["p1"].priced and catalogo["p1"].effective_price == Decimal("110")
    assert _catalogo(pos_conn, branch="otra")["p1"].effective_price == Decimal("120")
    assert not catalogo["p2"].priced
