"""Ciclo de vida comercial completo del proveedor + RBAC real.

Tres cosas que antes no existían por encima del dominio:

1. **Baja y reactivación.** `Supplier.deactivate()` estaba en la entidad desde
   el principio, pero sin caso de uso, sin evento y sin permiso: la transición
   a INACTIVO no era alcanzable. Y `activate()` sólo admitía SUSPENDED/BLOCKED,
   así que un proveedor dado de baja no tenía vuelta atrás salvo crear otro
   registro — duplicando el historial que la baja existe para preservar.
2. **Información mínima al activar.** Activar no es marcar un booleano.
3. **Autorización real.** La política sin checker PERMITE todo; el checker
   traduce los códigos planos al vocabulario grueso que la base sí concede.
"""

import sqlite3

import pytest

from backend.application.suppliers.authorization import SupplierAuthorizationPolicy
from backend.application.suppliers.permissions import SupplierPermissions
from backend.application.suppliers.session_authorization import (
    SupplierSessionPermissionChecker,
)
from backend.application.suppliers.use_cases.lifecycle_use_cases import (
    ActivateSupplierUseCase,
    ApproveSupplierUseCase,
    CreateSupplierUseCase,
    DeactivateSupplierUseCase,
    SubmitSupplierForApprovalUseCase,
)
from backend.domain.suppliers.entities import Supplier
from backend.domain.suppliers.enums import SupplierStatus
from backend.domain.suppliers.exceptions import InvalidSupplierStateError
from backend.domain.suppliers.policies import SupplierActivationPolicy
from backend.domain.suppliers.value_objects import SupplierCode, TaxIdentifier
from backend.infrastructure.db.repositories.suppliers.unit_of_work import (
    SupplierUnitOfWork,
)
from backend.infrastructure.db.schema.supplier_schema import create_supplier_schema
from backend.shared.ids import new_uuid

_ALL_COARSE = {"PROVEEDORES.ver", "PROVEEDORES.crear", "PROVEEDORES.editar",
               "PROVEEDORES.eliminar", "PROVEEDORES.exportar"}


class _Session:
    def __init__(self, granted=_ALL_COARSE, *, user_id="user-1",
                 branch="branch-1", active=True):
        self.is_active = active
        self.user_id = user_id
        self.active_branch_id = branch
        self._granted = set(granted)

    def tiene_permiso(self, code: str) -> bool:
        return code in self._granted


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_supplier_schema(c)
    c.commit()
    yield c
    c.close()


def _supplier(status=SupplierStatus.ACTIVE, *, rfc="DVA010203XY1") -> Supplier:
    s = Supplier.create(
        SupplierCode.from_sequence(1), "Distribuidora del Valle SA de CV",
        tax_identifier=TaxIdentifier(rfc) if rfc else None,
        created_by_user_id="creador")
    s.status = status
    return s


# ── dominio: baja con motivo y reactivación ───────────────────────────────
def test_la_baja_registra_el_motivo():
    s = _supplier()
    s.deactivate("Dejó de surtir en tiempo")
    assert s.status is SupplierStatus.INACTIVE
    assert "[Baja] Dejó de surtir en tiempo" in s.notes


def test_un_borrador_no_se_da_de_baja():
    with pytest.raises(InvalidSupplierStateError):
        _supplier(SupplierStatus.DRAFT).deactivate("x")


def test_un_proveedor_dado_de_baja_puede_reactivarse():
    """Antes era imposible: `activate()` sólo admitía SUSPENDED/BLOCKED."""
    s = _supplier(SupplierStatus.INACTIVE)
    s.activate()
    assert s.status is SupplierStatus.ACTIVE


def test_desde_borrador_sigue_sin_poder_activarse():
    with pytest.raises(InvalidSupplierStateError):
        _supplier(SupplierStatus.DRAFT).activate()


# ── política: información mínima ──────────────────────────────────────────
def test_activar_exige_identificador_fiscal():
    politica = SupplierActivationPolicy()
    with pytest.raises(InvalidSupplierStateError, match="RFC"):
        politica.enforce_can_activate(_supplier(SupplierStatus.SUSPENDED, rfc=None))


def test_activar_pasa_con_informacion_minima():
    SupplierActivationPolicy().enforce_can_activate(_supplier(SupplierStatus.SUSPENDED))


# ── checker: traducción al vocabulario grueso ─────────────────────────────
def test_activar_se_traduce_a_editar():
    checker = SupplierSessionPermissionChecker(_Session({"PROVEEDORES.editar"}))
    assert checker.has_permission("user-1", SupplierPermissions.ACTIVATE) is True


def test_bloquear_exige_el_permiso_mas_privilegiado():
    """Sacar a un proveedor de operación no queda al alcance de quien edita."""
    solo_edita = SupplierSessionPermissionChecker(_Session({"PROVEEDORES.editar"}))
    assert solo_edita.has_permission("user-1", SupplierPermissions.BLOCK) is False
    assert solo_edita.has_permission("user-1", SupplierPermissions.VERIFY_BANK) is False

    con_eliminar = SupplierSessionPermissionChecker(_Session({"PROVEEDORES.eliminar"}))
    assert con_eliminar.has_permission("user-1", SupplierPermissions.BLOCK) is True


def test_los_codigos_sin_contrapartida_deniegan():
    """Los de sólo lectura sensibles no se mapean: traducirlos a `ver`
    expondría datos bancarios a cualquiera que abra el módulo."""
    checker = SupplierSessionPermissionChecker(_Session())
    assert checker.has_permission("user-1", SupplierPermissions.VIEW_BANK) is False
    assert checker.has_permission("user-1", SupplierPermissions.VIEW_FINANCIAL) is False


@pytest.mark.parametrize("sesion", [
    None,
    _Session(active=False),
    _Session(branch=""),
])
def test_sesion_invalida_deniega(sesion):
    checker = SupplierSessionPermissionChecker(sesion)
    assert checker.has_permission("user-1", SupplierPermissions.ACTIVATE) is False


def test_un_usuario_distinto_al_de_la_sesion_deniega():
    checker = SupplierSessionPermissionChecker(_Session())
    assert checker.has_permission("otro-usuario", SupplierPermissions.ACTIVATE) is False


# ── extremo a extremo: alta → aprobar → baja → reactivar ──────────────────
def _auth(session) -> SupplierAuthorizationPolicy:
    return SupplierAuthorizationPolicy(SupplierSessionPermissionChecker(session))


def test_el_ciclo_completo_pasa_por_casos_de_uso(conn):
    capturista = _Session(user_id="capturista")
    aprobador = _Session(user_id="aprobador")

    creado = CreateSupplierUseCase(_auth(capturista)).execute(
        conn, actor_user_id="capturista", legal_name="Distribuidora del Valle",
        tax_identifier="DVA010203XY1", operation_id=new_uuid())
    assert creado.success, creado.message
    supplier_id = creado.entity_id

    enviado = SubmitSupplierForApprovalUseCase(_auth(capturista)).execute(
        conn, actor_user_id="capturista", supplier_id=supplier_id,
        operation_id=new_uuid())
    assert enviado.success, enviado.message

    # Segregación de funciones: la aprueba OTRO usuario. Sigue viva aunque el
    # permiso de aprobar se traduzca al mismo `editar` que el de capturar.
    aprobado = ApproveSupplierUseCase(_auth(aprobador)).execute(
        conn, actor_user_id="aprobador", supplier_id=supplier_id,
        operation_id=new_uuid())
    assert aprobado.success, aprobado.message

    baja = DeactivateSupplierUseCase(_auth(aprobador)).execute(
        conn, actor_user_id="aprobador", supplier_id=supplier_id,
        operation_id=new_uuid(), reason="Fin de relación comercial")
    assert baja.success, baja.message
    with SupplierUnitOfWork(conn) as uow:
        assert uow.suppliers.get(supplier_id).status is SupplierStatus.INACTIVE

    reactivado = ActivateSupplierUseCase(_auth(aprobador)).execute(
        conn, actor_user_id="aprobador", supplier_id=supplier_id,
        operation_id=new_uuid())
    assert reactivado.success, reactivado.message
    with SupplierUnitOfWork(conn) as uow:
        assert uow.suppliers.get(supplier_id).status is SupplierStatus.ACTIVE


def test_el_mismo_usuario_no_captura_y_aprueba(conn):
    """La segregación de funciones no depende del permiso, sino de la identidad
    — y era justo lo que el actor literal "desktop" rompía."""
    sesion = _Session(user_id="unico")
    creado = CreateSupplierUseCase(_auth(sesion)).execute(
        conn, actor_user_id="unico", legal_name="Alfa SA",
        tax_identifier="AAA010203XY1", operation_id=new_uuid())
    SubmitSupplierForApprovalUseCase(_auth(sesion)).execute(
        conn, actor_user_id="unico", supplier_id=creado.entity_id,
        operation_id=new_uuid())

    aprobado = ApproveSupplierUseCase(_auth(sesion)).execute(
        conn, actor_user_id="unico", supplier_id=creado.entity_id,
        operation_id=new_uuid())

    assert not aprobado.success
    assert "separación de funciones" in aprobado.message.lower()


def test_sin_permiso_la_operacion_se_deniega(conn):
    sin_permisos = _Session(granted=set())
    resultado = CreateSupplierUseCase(_auth(sin_permisos)).execute(
        conn, actor_user_id="user-1", legal_name="Beta SA",
        tax_identifier="BBB010203XY1", operation_id=new_uuid())
    assert not resultado.success and resultado.error_code == "PERMISSION_DENIED"
