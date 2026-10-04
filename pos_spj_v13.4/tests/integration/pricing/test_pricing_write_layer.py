"""Capa de ESCRITURA de Precios: ciclo de vida de listas, precios y RBAC.

Este paquete de casos de uso no existía. El contexto tenía dominio, autorización
y repositorio completos, pero ni un solo caso de uso los usaba: los `save_*` no
tenían llamadores fuera del propio repositorio y la UI era de sólo lectura — el
módulo se abría y no se podía ejecutar nada.

Lo más importante que se fija aquí es la **segregación de funciones**: existía
implementada y probada en aislamiento, pero `price_list` no guardaba al creador,
así que ninguna ruta real podía pasarle el dato y NO podía dispararse nunca.
"""

import sqlite3
from types import SimpleNamespace

import pytest

from backend.application.pricing.authorization.policy import PricingAuthorizationPolicy
from backend.application.security.authorizer_permission_checker import (
    AuthorizerPermissionChecker,
)
from backend.application.pricing.permissions import PricingPermissions
from backend.application.pricing.session_authorization import (
    PricingSessionPermissionChecker,
)
from backend.application.pricing.use_cases import (
    ActivatePriceListUseCase,
    ApplyPriceToSelectionUseCase,
    ApprovePriceListUseCase,
    CreatePriceListUseCase,
    DeactivatePriceListUseCase,
    DuplicatePriceListUseCase,
    SetProductPriceUseCase,
    SetVolumePriceUseCase,
    SubmitPriceListUseCase,
)
from backend.infrastructure.db.repositories.pricing.pricing_repository import (
    PricingRepository,
)
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.shared.ids import new_uuid


class _Session:
    def __init__(self, *, user_id="u1", granted=True, active=True, branch="b1"):
        self.is_active = active
        self.user_id = user_id
        self.active_branch_id = branch
        self._granted = granted

    def tiene_permiso(self, _code: str) -> bool:
        return self._granted


def _auth(session) -> PricingAuthorizationPolicy:
    return PricingAuthorizationPolicy(PricingSessionPermissionChecker(session))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_pricing_schema(c)
    c.commit()
    yield c
    c.close()


class _Concede:
    """Verificador con permisos EXACTOS.

    `_Session` concede todo o nada, así que no puede distinguir `PRICE_EDIT` de
    `BRANCH_PRICE_MANAGE` — y esa distinción es justo lo que hay que probar en
    la aplicación en lote acotada a una sucursal.
    """

    def __init__(self, *codes):
        self._codes = set(codes)

    def has_permission(self, _user_id, code):
        return code in self._codes


class _BusquedaFalsa:
    """Puerto de búsqueda de productos. Guarda el criterio recibido para poder
    afirmar que Precios sólo AÑADE restricciones al contrato compartido."""

    def __init__(self, *product_ids):
        self._ids = list(product_ids)
        self.criterio = None

    def __call__(self):
        return self

    def search(self, criteria):
        self.criterio = criteria
        return [SimpleNamespace(product_id=pid) for pid in self._ids]


def _lista(conn, actor="u1", *, code="BASE-1", kind="BASE"):
    return CreatePriceListUseCase(_auth(_Session(user_id=actor))).execute(
        conn, actor_user_id=actor, code=code, name="Lista", kind=kind,
        operation_id=new_uuid())


def _precio(conn, lista_id, product_id, precio="100", actor="u1"):
    return SetProductPriceUseCase(_auth(_Session(user_id=actor))).execute(
        conn, actor_user_id=actor, price_list_id=lista_id, product_id=product_id,
        sale_price=precio, operation_id=new_uuid())


# ── ciclo de vida ─────────────────────────────────────────────────────────
def test_crear_registra_al_creador(conn):
    """Sin creador persistido la segregación de funciones no puede evaluarse."""
    creada = _lista(conn)
    assert creada.success, creada.message
    assert PricingRepository(conn).get_list(creada.entity_id).created_by_user_id == "u1"


def test_quien_crea_no_aprueba(conn):
    creada = _lista(conn, "capturista")
    SubmitPriceListUseCase(_auth(_Session(user_id="capturista"))).execute(
        conn, actor_user_id="capturista", price_list_id=creada.entity_id,
        operation_id=new_uuid())

    propio = ApprovePriceListUseCase(_auth(_Session(user_id="capturista"))).execute(
        conn, actor_user_id="capturista", price_list_id=creada.entity_id,
        operation_id=new_uuid())

    assert not propio.success
    assert propio.error_code == "SEGREGATION_OF_DUTIES"


def test_otro_usuario_si_aprueba_y_activa(conn):
    creada = _lista(conn, "capturista")
    _precio(conn, creada.entity_id, "p1", actor="capturista")
    SubmitPriceListUseCase(_auth(_Session(user_id="capturista"))).execute(
        conn, actor_user_id="capturista", price_list_id=creada.entity_id,
        operation_id=new_uuid())

    aprobador = _auth(_Session(user_id="jefe"))
    aprobada = ApprovePriceListUseCase(aprobador).execute(
        conn, actor_user_id="jefe", price_list_id=creada.entity_id,
        operation_id=new_uuid())
    activada = ActivatePriceListUseCase(aprobador).execute(
        conn, actor_user_id="jefe", price_list_id=creada.entity_id,
        operation_id=new_uuid())

    assert aprobada.success and activada.success
    assert PricingRepository(conn).get_list(creada.entity_id).status.value == "ACTIVE"


def test_una_transicion_invalida_no_revienta(conn):
    """Activar un BORRADOR es un error de estado, no una excepción."""
    creada = _lista(conn)
    r = ActivatePriceListUseCase(_auth(_Session(user_id="otro"))).execute(
        conn, actor_user_id="otro", price_list_id=creada.entity_id,
        operation_id=new_uuid())
    assert not r.success and r.error_code == "INVALID_STATE"


def test_lista_inexistente(conn):
    r = SubmitPriceListUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", price_list_id=new_uuid(), operation_id=new_uuid())
    assert not r.success and r.error_code == "NOT_FOUND"


# ── precios ───────────────────────────────────────────────────────────────
def test_fijar_precio_con_vigencia_y_auditoria(conn):
    creada = _lista(conn)
    r = SetProductPriceUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", price_list_id=creada.entity_id, product_id="p1",
        sale_price="100.50", min_price="90", operation_id=new_uuid(),
        effective_from="2026-10-01", effective_to="2026-12-31")

    assert r.success, r.message
    guardado = PricingRepository(conn).get_price(
        price_list_id=creada.entity_id, product_id="p1", branch_id=None)
    assert guardado.effective_from == "2026-10-01"
    # El cambio queda auditado: `log_cost_change` fijaba `field='cost'` y no
    # había manera de registrar un cambio de PRECIO.
    assert conn.execute(
        "SELECT COUNT(*) FROM price_change_log WHERE field='sale_price'"
    ).fetchone()[0] == 1


def test_una_lista_activa_es_inmutable(conn):
    creada = _lista(conn, "capturista")
    _precio(conn, creada.entity_id, "p0", actor="capturista")
    SubmitPriceListUseCase(_auth(_Session(user_id="capturista"))).execute(
        conn, actor_user_id="capturista", price_list_id=creada.entity_id,
        operation_id=new_uuid())
    jefe = _auth(_Session(user_id="jefe"))
    ApprovePriceListUseCase(jefe).execute(
        conn, actor_user_id="jefe", price_list_id=creada.entity_id,
        operation_id=new_uuid())
    ActivatePriceListUseCase(jefe).execute(
        conn, actor_user_id="jefe", price_list_id=creada.entity_id,
        operation_id=new_uuid())

    r = SetProductPriceUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", price_list_id=creada.entity_id, product_id="p1",
        sale_price="10", operation_id=new_uuid())

    assert not r.success and r.error_code == "IMMUTABLE_LIST"


def test_bajo_el_minimo_exige_autorizacion(conn):
    creada = _lista(conn)
    r = SetProductPriceUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", price_list_id=creada.entity_id, product_id="p1",
        sale_price="80", min_price="90", operation_id=new_uuid())
    assert not r.success and r.error_code == "BELOW_MINIMUM"


def test_el_verificador_de_sesion_por_si_solo_no_autoriza_en_caliente(conn):
    """POR QUÉ la composición inyecta DOS políticas y no una.

    Vender bajo el mínimo exige que OTRO usuario (el gerente) autorice. Pero
    `PricingSessionPermissionChecker` —igual que los de Compras y
    Transferencias— sólo concede si el usuario consultado ES el de la sesión, y
    el autorizador es por definición otro. Con un único verificador de sesión
    la autorización en caliente se deniega SIEMPRE: la capacidad existía en el
    dominio y era inalcanzable en la práctica.

    Este test fija ese comportamiento —que sigue siendo el correcto cuando no
    se inyecta nada más, porque deniega en vez de aparentar que concedió— y el
    siguiente prueba el camino que hoy cablea `shell_registration.py`: una
    segunda política, respaldada por `rol_permisos`, usada SÓLO para validar al
    autorizador.
    """
    creada = _lista(conn)
    r = SetProductPriceUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", price_list_id=creada.entity_id, product_id="p1",
        sale_price="80", min_price="90", operation_id=new_uuid(),
        authorized_by="gerente", authorization_reason="cliente de mayoreo")

    assert not r.success
    assert "gerente" in r.message


# ── duplicar una lista ────────────────────────────────────────────────────
def test_duplicar_copia_la_cabecera_y_los_precios(conn):
    origen = _lista(conn)
    _precio(conn, origen.entity_id, "p1", "100")
    _precio(conn, origen.entity_id, "p2", "250")

    copia = DuplicatePriceListUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", source_list_id=origen.entity_id,
        code="BASE-COPIA", name="Copia", operation_id=new_uuid())

    assert copia.success, copia.message
    precios = PricingRepository(conn).prices_of_list(copia.entity_id)
    assert {p.product_id for p in precios} == {"p1", "p2"}
    assert copia.data["copied_prices"] == 2


def test_la_copia_nace_en_borrador_y_es_editable(conn):
    origen = _lista(conn)
    copia = DuplicatePriceListUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", source_list_id=origen.entity_id,
        code="BASE-COPIA", name="Copia", operation_id=new_uuid())

    lista = PricingRepository(conn).get_list(copia.entity_id)
    assert lista.status.value == "DRAFT"
    assert lista.is_editable


def test_duplicar_es_el_camino_para_cambiar_una_lista_inmutable(conn):
    """Motivo de existir de la acción: una lista APROBADA no se edita, y sin
    duplicar no habría forma de partir de ella."""
    origen = _lista(conn)
    _precio(conn, origen.entity_id, "p1", "100")
    SubmitPriceListUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", price_list_id=origen.entity_id,
        operation_id=new_uuid())
    ApprovePriceListUseCase(_auth(_Session(user_id="u2"))).execute(
        conn, actor_user_id="u2", price_list_id=origen.entity_id,
        operation_id=new_uuid())

    copia = DuplicatePriceListUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", source_list_id=origen.entity_id,
        code="BASE-COPIA", name="Copia", operation_id=new_uuid())

    assert copia.success, copia.message
    assert PricingRepository(conn).get_list(copia.entity_id).is_editable


def test_el_creador_de_la_copia_es_quien_duplica(conn):
    """Heredar el creador del origen dejaría que quien duplica aprobara su
    propia lista, y la segregación de funciones volvería a ser decorativa."""
    origen = _lista(conn, actor="u1")

    copia = DuplicatePriceListUseCase(_auth(_Session(user_id="u2"))).execute(
        conn, actor_user_id="u2", source_list_id=origen.entity_id,
        code="BASE-COPIA", name="Copia", operation_id=new_uuid())

    assert PricingRepository(conn).get_list(copia.entity_id).created_by_user_id == "u2"


def test_duplicar_sin_copiar_precios(conn):
    origen = _lista(conn)
    _precio(conn, origen.entity_id, "p1", "100")

    copia = DuplicatePriceListUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", source_list_id=origen.entity_id,
        code="BASE-COPIA", name="Copia", operation_id=new_uuid(),
        copy_prices=False)

    assert copia.data["copied_prices"] == 0
    assert PricingRepository(conn).prices_of_list(copia.entity_id) == []


def test_duplicar_una_lista_inexistente_falla(conn):
    r = DuplicatePriceListUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", source_list_id=new_uuid(),
        code="X", name="X", operation_id=new_uuid())

    assert not r.success and r.error_code == "NOT_FOUND"


# ── aplicar un precio en lote ─────────────────────────────────────────────
def test_aplicar_en_lote_a_productos_explicitos(conn):
    creada = _lista(conn)
    r = ApplyPriceToSelectionUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", price_list_id=creada.entity_id,
        sale_price="99", product_ids=["p1", "p2", "p3"], operation_id=new_uuid())

    assert r.success, r.message
    assert r.data["applied"] == 3
    assert len(PricingRepository(conn).prices_of_list(creada.entity_id)) == 3


def test_la_seleccion_por_categoria_usa_el_contrato_compartido(conn):
    """Precios sólo AÑADE restricciones —activo + categoría— sobre el contrato
    compartido; no trae una consulta propia del catálogo."""
    creada = _lista(conn)
    busqueda = _BusquedaFalsa("p1", "p2")

    r = ApplyPriceToSelectionUseCase(_auth(_Session()), busqueda).execute(
        conn, actor_user_id="u1", price_list_id=creada.entity_id,
        sale_price="50", category_id="cat-1", operation_id=new_uuid())

    assert r.success and r.data["applied"] == 2
    assert busqueda.criterio.category_id == "cat-1"
    assert busqueda.criterio.active_only is True


def test_sin_productos_en_la_seleccion_no_se_aplica_nada(conn):
    creada = _lista(conn)
    r = ApplyPriceToSelectionUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", price_list_id=creada.entity_id,
        sale_price="50", category_id="cat-1", operation_id=new_uuid())

    assert not r.success and r.error_code == "EMPTY_SELECTION"


def test_el_lote_por_sucursal_exige_su_propio_permiso(conn):
    """`BRANCH_PRICE_MANAGE` estaba declarado y no lo exigía ningún caso de uso."""
    creada = _lista(conn)
    solo_editar = PricingAuthorizationPolicy(_Concede(PricingPermissions.PRICE_EDIT))

    r = ApplyPriceToSelectionUseCase(solo_editar).execute(
        conn, actor_user_id="u1", price_list_id=creada.entity_id,
        sale_price="50", product_ids=["p1"], branch_id="suc-1",
        operation_id=new_uuid())

    assert not r.success and r.error_code == "PERMISSION_DENIED"


def test_con_el_permiso_de_sucursal_el_lote_se_aplica(conn):
    creada = _lista(conn)
    completo = PricingAuthorizationPolicy(
        _Concede(PricingPermissions.PRICE_EDIT,
                 PricingPermissions.BRANCH_PRICE_MANAGE))

    r = ApplyPriceToSelectionUseCase(completo).execute(
        conn, actor_user_id="u1", price_list_id=creada.entity_id,
        sale_price="50", product_ids=["p1"], branch_id="suc-1",
        operation_id=new_uuid())

    assert r.success, r.message
    guardado = PricingRepository(conn).get_price(
        price_list_id=creada.entity_id, product_id="p1", branch_id="suc-1")
    assert guardado.branch_id == "suc-1"


def test_el_lote_no_autoriza_precios_bajo_el_minimo(conn):
    """Conceder una autorización en caliente para un lote entero convertiría
    una excepción puntual en barra libre."""
    creada = _lista(conn)
    r = ApplyPriceToSelectionUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", price_list_id=creada.entity_id,
        sale_price="80", min_price="90", product_ids=["p1"],
        operation_id=new_uuid())

    assert not r.success and r.error_code == "BELOW_MINIMUM"


def test_el_lote_respeta_la_inmutabilidad_de_la_lista(conn):
    creada = _lista(conn)
    _precio(conn, creada.entity_id, "p0")
    SubmitPriceListUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", price_list_id=creada.entity_id,
        operation_id=new_uuid())
    ApprovePriceListUseCase(_auth(_Session(user_id="u2"))).execute(
        conn, actor_user_id="u2", price_list_id=creada.entity_id,
        operation_id=new_uuid())

    r = ApplyPriceToSelectionUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", price_list_id=creada.entity_id,
        sale_price="50", product_ids=["p1"], operation_id=new_uuid())

    assert not r.success and r.error_code == "IMMUTABLE_LIST"


def _seed_seguridad(conn, *, user_id="gerente", role="gerente_precios", grants=()):
    """Las tres tablas REALES contra las que resuelve el ERP entero.

    Se crean de verdad en vez de simularse porque `permission_codes_for_user`
    las consulta directamente: a diferencia de `usuario_permisos` y
    `usuario_sucursal_permisos` —que sí están guardadas con `sqlite_master` por
    ser posteriores al esquema base— aquí no hay degradación elegante, y un
    esquema sin ellas no es una instalación antigua sino un error.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS usuarios (id TEXT PRIMARY KEY, rol TEXT);
        CREATE TABLE IF NOT EXISTS roles (id TEXT PRIMARY KEY, nombre TEXT);
        CREATE TABLE IF NOT EXISTS rol_permisos (
            rol_id TEXT, modulo TEXT, accion TEXT, permitido INTEGER);
        """)
    role_id = new_uuid()
    conn.execute("INSERT INTO usuarios (id, rol) VALUES (?,?)", (user_id, role))
    conn.execute("INSERT INTO roles (id, nombre) VALUES (?,?)", (role_id, role))
    conn.executemany(
        "INSERT INTO rol_permisos (rol_id, modulo, accion, permitido) VALUES (?,?,?,1)",
        [(role_id, modulo, accion) for modulo, accion in grants])
    conn.commit()


def _caso_con_autorizador(conn):
    """Igual que lo compone `shell_registration.py`: sesión para operar,
    `rol_permisos` para autorizar."""
    return SetProductPriceUseCase(
        _auth(_Session()),
        PricingAuthorizationPolicy(AuthorizerPermissionChecker(conn)))


def _bajo_el_minimo(caso, conn, creada, *, autorizador="gerente"):
    return caso.execute(
        conn, actor_user_id="u1", price_list_id=creada.entity_id, product_id="p1",
        sale_price="80", min_price="90", operation_id=new_uuid(),
        authorized_by=autorizador, authorization_reason="cliente de mayoreo")


def test_el_autorizador_se_valida_contra_rol_permisos(conn):
    """El camino real: el gerente NO tiene la sesión abierta —la tiene `u1`—
    y aun así autoriza, porque sus permisos se resuelven desde la base."""
    _seed_seguridad(conn, grants=(("PRECIOS", "precio.minimo.excepcion"),))
    creada = _lista(conn)

    r = _bajo_el_minimo(_caso_con_autorizador(conn), conn, creada)

    assert r.success, r.message
    fila = conn.execute(
        "SELECT authorized_by, reason FROM price_change_log WHERE field='sale_price'"
    ).fetchone()
    assert fila["authorized_by"] == "gerente"
    assert fila["reason"] == "cliente de mayoreo"


def test_un_autorizador_sin_el_permiso_de_excepcion_no_autoriza(conn):
    """Tener permisos en Precios no basta: hace falta EL de la excepción."""
    _seed_seguridad(conn, grants=(("PRECIOS", "ver"), ("PRECIOS", "precio.editar")))
    creada = _lista(conn)

    r = _bajo_el_minimo(_caso_con_autorizador(conn), conn, creada)

    assert not r.success
    assert "gerente" in r.message


def test_un_autorizador_desconocido_no_autoriza(conn):
    """Falla cerrado: un usuario que no existe en `usuarios` no hereda nada."""
    _seed_seguridad(conn, grants=(("PRECIOS", "precio.minimo.excepcion"),))
    creada = _lista(conn)

    r = _bajo_el_minimo(_caso_con_autorizador(conn), conn, creada,
                        autorizador="fantasma")

    assert not r.success


def test_el_comodin_de_modulo_autoriza(conn):
    """`PRECIOS.*` concede, con las mismas reglas que `PermissionEvaluator`:
    si aquí no aplicaran, un rol otorgado por comodín operaría en todo el ERP
    salvo en la autorización de precios."""
    _seed_seguridad(conn, grants=(("PRECIOS", "*"),))
    creada = _lista(conn)

    assert _bajo_el_minimo(_caso_con_autorizador(conn), conn, creada).success


def test_el_administrador_autoriza_por_comodin_global(conn):
    _seed_seguridad(conn, role="admin", grants=())
    creada = _lista(conn)

    assert _bajo_el_minimo(_caso_con_autorizador(conn), conn, creada).success


def test_con_un_verificador_que_valida_a_cualquier_usuario_si_autoriza(conn):
    """El mismo caso de uso SÍ autoriza cuando el verificador puede validar al
    autorizador — prueba de que la lógica está bien y lo que falta es el
    cableado del verificador, no el caso de uso."""
    class _ChequeaCualquiera:
        def has_permission(self, user_id, code):
            return user_id == "gerente" or user_id == "u1"

    politica = PricingAuthorizationPolicy(_ChequeaCualquiera())
    creada = CreatePriceListUseCase(politica).execute(
        conn, actor_user_id="u1", code="BASE-2", name="Lista", kind="BASE",
        operation_id=new_uuid())

    r = SetProductPriceUseCase(politica).execute(
        conn, actor_user_id="u1", price_list_id=creada.entity_id, product_id="p1",
        sale_price="80", min_price="90", operation_id=new_uuid(),
        authorized_by="gerente", authorization_reason="cliente de mayoreo")

    assert r.success, r.message
    fila = conn.execute(
        "SELECT authorized_by, reason FROM price_change_log WHERE field='sale_price'"
    ).fetchone()
    assert fila["authorized_by"] == "gerente"
    assert fila["reason"] == "cliente de mayoreo"


def test_el_autorizador_no_puede_ser_el_solicitante(conn):
    """Autoautorizarse se DEVUELVE como fallo, no se lanza.

    `SegregationOfDutiesError` hereda de `PricingDomainError`, así que el caso
    de uso la convierte en resultado — que es lo correcto: la pantalla puede
    explicarlo en vez de mostrar un "error inesperado".
    """
    creada = _lista(conn)
    r = SetProductPriceUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", price_list_id=creada.entity_id, product_id="p1",
        sale_price="80", min_price="90", operation_id=new_uuid(),
        authorized_by="u1", authorization_reason="me autorizo solo")

    assert not r.success
    assert "autorizador" in r.message.lower() or "solicitante" in r.message.lower()


def test_escala_por_volumen(conn):
    creada = _lista(conn)
    precio = SetProductPriceUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", price_list_id=creada.entity_id, product_id="p1",
        sale_price="100", operation_id=new_uuid())

    r = SetVolumePriceUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", product_price_id=precio.entity_id,
        min_quantity="10", price="95", operation_id=new_uuid())

    assert r.success, r.message
    assert len(PricingRepository(conn).volume_tiers(precio.entity_id)) == 1


# ── RBAC ──────────────────────────────────────────────────────────────────
def test_sin_permiso_se_deniega(conn):
    r = CreatePriceListUseCase(_auth(_Session(granted=False))).execute(
        conn, actor_user_id="u1", code="X-1", name="X", kind="BASE",
        operation_id=new_uuid())
    assert not r.success and r.error_code == "PERMISSION_DENIED"


@pytest.mark.parametrize("sesion", [
    None, _Session(active=False), _Session(branch=""),
])
def test_sesion_invalida_deniega(sesion):
    checker = PricingSessionPermissionChecker(sesion)
    assert checker.has_permission("u1", PricingPermissions.LIST_CREATE) is False


def test_usuario_distinto_al_de_la_sesion_deniega():
    checker = PricingSessionPermissionChecker(_Session(user_id="u1"))
    assert checker.has_permission("otro", PricingPermissions.LIST_CREATE) is False


def test_desactivar_cierra_el_ciclo(conn):
    creada = _lista(conn)
    r = DeactivatePriceListUseCase(_auth(_Session())).execute(
        conn, actor_user_id="u1", price_list_id=creada.entity_id,
        operation_id=new_uuid())
    assert r.success, r.message
    assert PricingRepository(conn).get_list(creada.entity_id).status.value == "INACTIVE"
