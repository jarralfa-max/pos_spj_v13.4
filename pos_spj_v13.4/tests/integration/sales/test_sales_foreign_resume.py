"""SDLC-ARQ-SESS-003 — una venta suspendida ajena no se toma en silencio.

Antes `ResumeSaleUseCase` dejaba reanudar a cualquiera con `POS.venta.reanudar`
y `cashier_user_id` no cambiaba: el efectivo que cobraba B caía en las ventas
de A. Decisión del responsable (2026-11-02): un supervisor sí puede reanudarla,
y otro cajero también, con autorización. En ambos casos el responsable pasa a
ser quien la reanuda y el traspaso queda auditado.

Los permisos vienen de un verificador por usuario, no de "conceder todo": lo
que se prueba es justo quién lo tiene y quién no.
"""
from __future__ import annotations

import inspect
import json
import sqlite3
from decimal import Decimal

import pytest

from backend.application.sales.authorization import SalesAuthorizationPolicy
from backend.application.sales.permissions import ALL_SALES_PERMISSIONS, SalesPermissions
from backend.application.sales.use_cases.cart_use_cases import AddSaleLineUseCase, StartSaleUseCase
from backend.application.sales.use_cases.lifecycle_use_cases import (
    ResumeSaleUseCase,
    SuspendSaleUseCase,
)
from backend.domain.sales.entities import Sale
from backend.domain.sales.enums import SaleStatus
from backend.domain.sales.exceptions import SaleResumeNotAllowedError
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid
from tests.integration._audit_trail_table import create_audit_logs_table
from tests.unit._canonical_stock import (
    allow_all_inventory,
    create_canonical_inventory,
    seed_available_stock,
)

ANA = new_uuid()              # dueña de la venta
BETO = new_uuid()             # otro cajero: reanuda, pero la ajena no
GERE = new_uuid()             # supervisor: tiene el permiso de tomar ajenas
BRANCH = new_uuid()

_CAJERO = set(ALL_SALES_PERMISSIONS) - {SalesPermissions.SALE_RESUME_FOREIGN}
_GRANTS = {ANA: _CAJERO, BETO: _CAJERO, GERE: set(ALL_SALES_PERMISSIONS)}


class _Grants:
    def has_permission(self, user_id, permission_code):
        return permission_code in _GRANTS.get(user_id, set())

    def can_access_branch(self, user_id, branch_id):
        return user_id in _GRANTS


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_canonical_inventory(c)
    create_audit_logs_table(c)
    yield c
    c.close()


@pytest.fixture
def auth():
    return SalesAuthorizationPolicy(_Grants())


@pytest.fixture
def suspended(conn, auth):
    """Una venta de Ana, suspendida por Ana."""
    product = new_uuid()
    seed_available_stock(conn, branch_id=BRANCH, product_id=product, quantity=10)
    sale_id = StartSaleUseCase(auth).execute(
        conn, branch_id=BRANCH, cashier_user_id=ANA, operation_id=new_uuid(),
        actor_user_id=ANA).entity_id
    AddSaleLineUseCase(auth).execute(
        conn, sale_id=sale_id, product_id=product, quantity=Decimal("1"),
        unit_price=Decimal("10.00"), actor_user_id=ANA, operation_id=new_uuid())
    result = SuspendSaleUseCase(auth, allow_all_inventory()).execute(
        conn, sale_id=sale_id, actor_user_id=ANA, operation_id=new_uuid(),
        max_suspended_sales=5)
    assert result.success is True, result.message
    return sale_id


def _resume(conn, auth, sale_id, actor, **kwargs):
    return ResumeSaleUseCase(auth).execute(
        conn, sale_id=sale_id, actor_user_id=actor, operation_id=new_uuid(), **kwargs)


def _audit_rows(conn):
    return conn.execute(
        "SELECT * FROM audit_logs WHERE accion='SALE_RESUME_TRANSFERRED'").fetchall()


class TestDominio:
    def _suspendida(self):
        sale = Sale.start(branch_id=BRANCH, cashier_user_id=ANA, operation_id=new_uuid())
        sale.status = SaleStatus.SUSPENDED
        sale.suspended_by_user_id = ANA
        return sale

    def test_por_defecto_solo_el_cajero_original_reanuda(self):
        sale = self._suspendida()
        with pytest.raises(SaleResumeNotAllowedError):
            sale.resume(resuming_user_id=BETO)
        assert sale.status is SaleStatus.SUSPENDED
        assert sale.cashier_user_id == ANA

    def test_el_cajero_original_reanuda_sin_traspaso(self):
        sale = self._suspendida()
        sale.resume(resuming_user_id=ANA)
        assert sale.status is SaleStatus.ACTIVE
        assert sale.cashier_user_id == ANA

    def test_el_traspaso_reasigna_al_responsable(self):
        sale = self._suspendida()
        sale.resume(resuming_user_id=BETO, allow_cross_user_resume=True)
        assert sale.cashier_user_id == BETO

    def test_el_traspaso_suelta_la_sesion_de_caja_del_cajero_anterior(self):
        sale = self._suspendida()
        sale.cash_session_id = new_uuid()
        sale.resume(resuming_user_id=BETO, allow_cross_user_resume=True)
        assert sale.cash_session_id is None

    def test_sin_quien_suspendio_tampoco_pasa_otro_usuario(self):
        """Antes `suspended_by_user_id or resuming_user_id` dejaba pasar a
        cualquiera cuando el dato venía vacío."""
        sale = self._suspendida()
        sale.suspended_by_user_id = None
        with pytest.raises(SaleResumeNotAllowedError):
            sale.resume(resuming_user_id=BETO)


class TestCasoDeUso:
    def test_el_llamador_no_puede_pedir_saltarse_la_regla(self):
        """La bandera era el hueco: ahora decide el permiso, no un argumento."""
        params = inspect.signature(ResumeSaleUseCase.execute).parameters
        assert "allow_cross_user_resume" not in params

    def test_el_cajero_original_reanuda_y_no_hay_traspaso(self, conn, auth, suspended):
        result = _resume(conn, auth, suspended, ANA)
        assert result.success is True, result.message
        sale = SaleRepository(conn).get(suspended)
        assert sale.status is SaleStatus.ACTIVE
        assert sale.cashier_user_id == ANA
        assert _audit_rows(conn) == []

    def test_otro_cajero_sin_autorizacion_no_reanuda(self, conn, auth, suspended):
        result = _resume(conn, auth, suspended, BETO)
        assert result.success is False
        assert result.error_code == "RESUME_AUTHORIZATION_REQUIRED"
        sale = SaleRepository(conn).get(suspended)
        assert sale.status is SaleStatus.SUSPENDED
        assert sale.cashier_user_id == ANA
        assert _audit_rows(conn) == []

    def test_el_supervisor_la_toma_y_queda_como_responsable(self, conn, auth, suspended):
        result = _resume(conn, auth, suspended, GERE)
        assert result.success is True, result.message
        sale = SaleRepository(conn).get(suspended)      # lo que quedó en la BD
        assert sale.status is SaleStatus.ACTIVE
        assert sale.cashier_user_id == GERE

    def test_otro_cajero_la_toma_con_autorizacion(self, conn, auth, suspended):
        result = _resume(conn, auth, suspended, BETO, authorizer_user_id=GERE,
                         reason="Ana salió a comer")
        assert result.success is True, result.message
        assert SaleRepository(conn).get(suspended).cashier_user_id == BETO

    def test_el_autorizador_debe_tener_el_permiso(self, conn, auth, suspended):
        result = _resume(conn, auth, suspended, BETO, authorizer_user_id=ANA,
                         reason="Yo le doy permiso")
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        assert SaleRepository(conn).get(suspended).cashier_user_id == ANA

    def test_nadie_se_autoriza_a_si_mismo(self, conn, auth, suspended):
        result = _resume(conn, auth, suspended, BETO, authorizer_user_id=BETO, reason="Yo")
        assert result.success is False
        assert result.error_code == "SEGREGATION_OF_DUTIES"
        assert SaleRepository(conn).get(suspended).cashier_user_id == ANA

    def test_la_autorizacion_exige_motivo(self, conn, auth, suspended):
        result = _resume(conn, auth, suspended, BETO, authorizer_user_id=GERE, reason="  ")
        assert result.success is False
        assert SaleRepository(conn).get(suspended).cashier_user_id == ANA


class TestAuditoria:
    def test_el_traspaso_autorizado_deja_quien_a_quien_y_por_que(self, conn, auth, suspended):
        _resume(conn, auth, suspended, BETO, authorizer_user_id=GERE, reason="Ana salió")
        filas = _audit_rows(conn)
        assert len(filas) == 1
        fila = filas[0]
        assert fila["usuario"] == BETO
        assert fila["entidad_id"] == suspended
        assert fila["sucursal_id"] == BRANCH
        assert json.loads(fila["valor_antes"]) == {"cashier_user_id": ANA}
        assert json.loads(fila["valor_despues"]) == {"cashier_user_id": BETO}
        detalle = json.loads(fila["detalles"])
        assert detalle["authorized_by"] == GERE
        assert detalle["reason"] == "Ana salió"

    def test_el_supervisor_tambien_queda_en_el_rastro(self, conn, auth, suspended):
        _resume(conn, auth, suspended, GERE)
        filas = _audit_rows(conn)
        assert len(filas) == 1
        assert json.loads(filas[0]["valor_despues"]) == {"cashier_user_id": GERE}

    def test_el_evento_lleva_el_traspaso(self, conn, auth, suspended):
        _resume(conn, auth, suspended, GERE)
        fila = conn.execute(
            "SELECT payload_json FROM sales_outbox WHERE event_name='SALE_RESUMED'").fetchone()
        payload = json.loads(fila["payload_json"])["payload"]
        assert payload["previous_cashier_user_id"] == ANA
        assert payload["cashier_user_id"] == GERE


class TestMigracion368:
    def _db(self):
        import importlib
        c = sqlite3.connect(":memory:")
        c.execute("CREATE TABLE roles (id TEXT PRIMARY KEY, nombre TEXT)")
        c.execute("CREATE TABLE rol_permisos (id TEXT PRIMARY KEY, rol_id TEXT, modulo TEXT,"
                  " accion TEXT, permitido INTEGER, UNIQUE(rol_id, modulo, accion))")
        for rol in ("system_owner", "admin", "gerente", "cajero"):
            c.execute("INSERT INTO roles VALUES (?,?)", (new_uuid(), rol))
        return c, importlib.import_module("migrations.standalone.368_pos_foreign_resume_permission")

    def _con_permiso(self, c):
        return {r[0] for r in c.execute(
            "SELECT r.nombre FROM rol_permisos p JOIN roles r ON r.id=p.rol_id"
            " WHERE p.modulo='POS' AND p.accion='venta.reanudar_ajena' AND p.permitido=1")}

    def test_el_gerente_lo_recibe_y_el_cajero_no(self):
        c, m = self._db()
        m.run(c)
        assert self._con_permiso(c) == {"system_owner", "admin", "gerente"}

    def test_es_idempotente_y_respeta_una_revocacion(self):
        c, m = self._db()
        m.run(c)
        c.execute("UPDATE rol_permisos SET permitido=0 WHERE rol_id="
                  "(SELECT id FROM roles WHERE nombre='gerente')")
        m.run(c)
        assert self._con_permiso(c) == {"system_owner", "admin"}

    def test_esta_registrada_en_el_motor(self):
        from migrations.engine import MIGRATIONS
        assert any(m.version == "368" for m in MIGRATIONS)


class TestPantalla:
    """La pantalla pide la autorización ANTES de apartar la venta en curso."""

    def _presenter(self, *, foreign):
        from frontend.desktop.modules.sales_pos.sales_pos_presenter import SalesPosPresenter
        from frontend.desktop.modules.sales_pos.view_models import SalesPosCapabilities
        presenter = SalesPosPresenter.__new__(SalesPosPresenter)
        presenter.current_user_id = lambda: BETO
        presenter.capabilities = lambda: SalesPosCapabilities(sale_resume_foreign=foreign)
        return presenter

    def test_la_venta_propia_no_pide_autorizacion(self):
        from types import SimpleNamespace
        presenter = self._presenter(foreign=False)
        assert presenter.resume_needs_authorization(
            SimpleNamespace(cashier_user_id=BETO)) is False

    def test_la_ajena_la_pide_salvo_al_supervisor(self):
        from types import SimpleNamespace
        ajena = SimpleNamespace(cashier_user_id=ANA)
        assert self._presenter(foreign=False).resume_needs_authorization(ajena) is True
        assert self._presenter(foreign=True).resume_needs_authorization(ajena) is False
