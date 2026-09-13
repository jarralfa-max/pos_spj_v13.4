"""La pantalla de dispositivos sólo ofrece lo que el backend aceptará.

EL FALLO QUE ESTO FIJA
-----------------------
Pulsar "Activar" reventaba la aplicación entera:

    LookupError: Dispositivo no encontrado o fuera de alcance

La lectura no estaba acotada y la escritura sí. `CashDeviceRepository.
list_devices(kind)` devolvía los dispositivos de TODAS las sucursales —la tabla
hasta tiene columna "Sucursal"—, mientras `SetCashDeviceStatusUseCase` exige
`device["branch_id"] == branch_id`, y el presenter manda siempre la sucursal de
la sesión.

O sea: la pantalla dejaba seleccionar dispositivos que el backend iba a
rechazar SIEMPRE. No era un caso raro, era todo lo que no fuera de tu sucursal.

Y el aviso tampoco llegaba: `_run` capturaba
`(CashRegisterError, RuntimeError, ValueError)`, y `LookupError` no está en esa
familia, así que en vez de un diálogo se caía el arranque.

LAS DOS MITADES SE PRUEBAN POR SEPARADO
-----------------------------------------
Acotar la lista y capturar el error son arreglos independientes: con sólo el
primero, cualquier otra ruta al mismo `LookupError` seguiría tumbando la app;
con sólo el segundo, la pantalla seguiría ofreciendo botones inútiles. Hay
pruebas para cada uno.
"""
from __future__ import annotations

import importlib
import sqlite3

import pytest

from backend.application.cash_register.device_query_service import CashDeviceQueryService
from backend.application.cash_register.device_use_cases import (
    CreateCashDeviceUseCase,
    SetCashDeviceStatusUseCase,
)
from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.infrastructure.db.repositories.cash_register.repositories import (
    CashDeviceRepository,
)
from backend.shared.ids import new_uuid


class _Permisos:
    def has_permission(self, user_id, permission_code):
        return True


class _Alcances:
    def can_access_branch(self, *, user_id, branch_id):
        return True


@pytest.fixture(scope="module")
def app():
    """QApplication de modulo. Crearla dentro del cuerpo de la prueba mataba el
    proceso entero sin imprimir nada —la firma de una violacion de acceso de
    Qt—, que es como fallan aqui las pruebas de widgets."""
    from PyQt5.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


@pytest.fixture
def db():
    c = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.175_cash_register_bounded_context_schema").run(c)
    yield c
    c.close()


@pytest.fixture
def auth():
    return CashAuthorizationPolicy(_Permisos(), _Alcances())


@pytest.fixture
def dos_sucursales(db, auth):
    """Una caja en la sucursal del usuario y otra en una sucursal ajena."""
    mia, ajena, actor = new_uuid(), new_uuid(), new_uuid()
    propia = CreateCashDeviceUseCase(auth).execute(
        db, kind="register", branch_id=mia, name="Caja mostrador",
        actor_user_id=actor, operation_id=new_uuid())
    otra = CreateCashDeviceUseCase(auth).execute(
        db, kind="register", branch_id=ajena, name="Caja sucursal norte",
        actor_user_id=actor, operation_id=new_uuid())
    db.commit()
    return {"mia": mia, "ajena": ajena, "actor": actor,
            "propia": propia.entity_id, "otra": otra.entity_id}


def _consulta(db):
    return CashDeviceQueryService(CashDeviceRepository(db))


# -- la mitad de la lectura ------------------------------------------------
def test_the_listing_scoped_to_a_branch_hides_the_others(db, dos_sucursales):
    """Lo que la pantalla pide ahora."""
    filas = _consulta(db).list_devices("register", branch_id=dos_sucursales["mia"])

    assert [f.id for f in filas] == [dos_sucursales["propia"]]


def test_the_unscoped_listing_still_returns_everything(db, dos_sucursales):
    """El filtro es OPCIONAL a proposito: listar sin acotar sigue siendo una
    capacidad legitima del repositorio. Lo que no puede es usarlo una pantalla
    que ofrezca acciones."""
    filas = _consulta(db).list_devices("register")

    assert {f.id for f in filas} == {dos_sucursales["propia"], dos_sucursales["otra"]}


# -- el fallo original, reproducido ----------------------------------------
def test_acting_on_another_branch_device_is_refused(db, auth, dos_sucursales):
    """La traza exacta que se veia: el backend rechaza el dispositivo ajeno.

    Esto NO cambia —y no deberia—: el rechazo es correcto. Lo que estaba mal
    era ofrecerlo.
    """
    with pytest.raises(LookupError):
        SetCashDeviceStatusUseCase(auth).execute(
            db, kind="register", device_id=dos_sucursales["otra"],
            branch_id=dos_sucursales["mia"], activate=True,
            actor_user_id=dos_sucursales["actor"], operation_id=new_uuid())


def test_acting_on_its_own_branch_device_works(db, auth, dos_sucursales):
    """La otra mitad: sin esto, "acotar la lista" podria estar escondiendolo
    todo y las pruebas de arriba pasarian igual."""
    resultado = SetCashDeviceStatusUseCase(auth).execute(
        db, kind="register", device_id=dos_sucursales["propia"],
        branch_id=dos_sucursales["mia"], activate=True,
        actor_user_id=dos_sucursales["actor"], operation_id=new_uuid())

    assert resultado.entity_id == dos_sucursales["propia"]


# -- la mitad de la pantalla -----------------------------------------------
def test_the_page_lists_only_its_own_branch_and_survives_the_refusal(
        app, db, dos_sucursales, monkeypatch):
    """La pantalla trae SOLO los dispositivos de su sucursal."""
    from frontend.desktop.modules.cash_register import cash_devices_page as modulo

    avisos = []
    monkeypatch.setattr(modulo.CashDevicesPage, "_show_error",
                        lambda self, mensaje: avisos.append(mensaje))

    class _Capacidades:
        hardware_manage = True
        hardware_diagnose = True
        drawer_open_without_sale = True

    class _Presenter:
        def capabilities(self):
            return _Capacidades()

        def active_branch_id(self):
            return dos_sucursales["mia"]

        def set_cash_device_status(self, **_kwargs):
            raise LookupError("Dispositivo no encontrado o fuera de alcance")

    pagina = modulo.CashDevicesPage(_consulta(db), presenter=_Presenter())

    tabla = pagina._tables["register"]
    assert tabla.rowCount() == 1, "la tabla trajo dispositivos de otra sucursal"
    assert tabla.item(0, 0).text() == "Caja mostrador"


def test_a_refusal_becomes_a_warning_instead_of_killing_the_app(
        app, db, dos_sucursales, monkeypatch):
    """La otra mitad, separada a proposito.

    Acotar la lista y capturar el error son arreglos independientes: aunque la
    pantalla ya no ofrezca dispositivos ajenos, cualquier otra ruta al mismo
    `LookupError` —datos que cambian entre el refresco y el clic, por ejemplo—
    seguiria tumbando la aplicacion si `_run` no lo capturara.

    Separadas, un fallo dice CUAL de las dos mitades se rompio.
    """
    from frontend.desktop.modules.cash_register import cash_devices_page as modulo

    avisos = []
    monkeypatch.setattr(modulo.CashDevicesPage, "_show_error",
                        lambda self, mensaje: avisos.append(mensaje))

    class _Capacidades:
        hardware_manage = True
        hardware_diagnose = True
        drawer_open_without_sale = True

    class _Presenter:
        def capabilities(self):
            return _Capacidades()

        def active_branch_id(self):
            return dos_sucursales["mia"]

        def set_cash_device_status(self, **_kwargs):
            raise LookupError("Dispositivo no encontrado o fuera de alcance")

    pagina = modulo.CashDevicesPage(_consulta(db), presenter=_Presenter())

    pagina._run(lambda: pagina._presenter.set_cash_device_status(), "ok")

    assert avisos, "el LookupError no se convirtio en aviso: tumbaria la app"


def test_the_page_shows_nothing_without_an_active_branch(app, db, dos_sucursales,
                                                         monkeypatch):
    """Fail-closed: sin sucursal no se puede operar ningun dispositivo, asi que
    no se ensena ninguno.

    Ademas la pantalla tiene que ABRIR: `refresh()` corre desde el `__init__`,
    y dejar escapar el `CashContextError` la dejaria sin construirse —el mismo
    patron que ya rompio Usuarios y Roles—.
    """
    from frontend.desktop.modules.cash_register import cash_devices_page as modulo
    from frontend.desktop.modules.cash_register.cash_register_presenter import (
        CashContextError,
    )

    monkeypatch.setattr(modulo.CashDevicesPage, "_show_error",
                        lambda self, mensaje: None)

    class _Capacidades:
        hardware_manage = True
        hardware_diagnose = True
        drawer_open_without_sale = True

    class _SinSucursal:
        def capabilities(self):
            return _Capacidades()

        def active_branch_id(self):
            raise CashContextError(
                "Contexto de Caja requerido no disponible: sucursal activa")

    pagina = modulo.CashDevicesPage(_consulta(db), presenter=_SinSucursal())

    assert pagina._tables["register"].rowCount() == 0
