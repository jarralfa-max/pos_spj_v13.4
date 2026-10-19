"""Un despiece REVERSIBLE por los casos de uso reales de Productos.

Desde la Fase 7 (2026-09-19) la fuente de la reconstrucción inversa es el
esquema de corte (decisión del usuario): el mismo despiece que ejecuta Cárnico.
Crear → enviar → aprobar → activar → permitir armar con partes.
"""
from __future__ import annotations

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_cutting_commands import (
    CreateCuttingSchemeCommand,
    CuttingVersionTransitionCommand,
    SetCuttingReverseReconstructionCommand,
)
from backend.application.products.use_cases.product_cutting_use_cases import (
    ActivateCuttingVersionUseCase,
    ApproveCuttingVersionUseCase,
    CreateCuttingSchemeUseCase,
    SetCuttingReverseReconstructionUseCase,
    SubmitCuttingVersionUseCase,
)
from backend.shared.ids import new_uuid


class _Todo:
    def has_permission(self, user_id, code):
        return True


def reversible_cutting_scheme(conn, *, product_id: str, outputs: list[dict],
                              reversible: bool = True, activate: bool = True,
                              species_id: str = "pollo") -> tuple[str, str]:
    """`outputs`: dicts con product_id, quantity (por unidad de entrada),
    output_type y unit_id. Devuelve (scheme_id, version_id)."""
    auth = ProductsAuthorizationPolicy(_Todo())
    filas = [{"measure_kind": "BY_WEIGHT", **o} for o in outputs]
    creado = CreateCuttingSchemeUseCase(conn, auth).execute(CreateCuttingSchemeCommand(
        operation_id=new_uuid(), input_product_id=product_id, species_id=species_id,
        name="Despiece", cut_level="PRIMARY", outputs=filas, user_id="alice"))
    assert creado.success, creado.message
    scheme_id, version_id = creado.scheme_id, creado.version_id
    if activate:
        for caso, quien in ((SubmitCuttingVersionUseCase, "alice"),
                            (ApproveCuttingVersionUseCase, "bob"),
                            (ActivateCuttingVersionUseCase, "bob")):
            r = caso(conn, auth).execute(CuttingVersionTransitionCommand(
                operation_id=new_uuid(), version_id=version_id, user_id=quien))
            assert r.success, r.message
    if reversible:
        r = SetCuttingReverseReconstructionUseCase(conn, auth).execute(
            SetCuttingReverseReconstructionCommand(
                operation_id=new_uuid(), scheme_id=scheme_id, allowed=True, user_id="bob"))
        assert r.success, r.message
    return scheme_id, version_id


def active_yield_profile(conn, *, product_id: str, outputs: list[dict],
                         species_id: str = "pollo") -> str:
    """Perfil de rendimiento ACTIVO por los casos de uso reales de Productos.
    `outputs`: dicts con product_id, output_type, expected_yield_pct y unit_id.
    Desde la auditoría de Producción 32cfbf (2026-10-16) el perfil MANDA en el
    despiece: sin él una orden no se prepara. La tolerancia se fija a lo que
    las salidas se apartan de 100 % (las pruebas no siempre suman 100)."""
    from decimal import Decimal

    from backend.application.products.commands.product_yield_commands import (
        CreateYieldProfileCommand,
        YieldVersionTransitionCommand,
    )
    from backend.application.products.use_cases.product_yield_use_cases import (
        ActivateYieldVersionUseCase,
        ApproveYieldVersionUseCase,
        CreateYieldProfileUseCase,
        SubmitYieldVersionUseCase,
    )

    auth = ProductsAuthorizationPolicy(_Todo())
    total = sum((Decimal(str(o["expected_yield_pct"])) for o in outputs), Decimal("0"))
    creado = CreateYieldProfileUseCase(conn, auth).execute(CreateYieldProfileCommand(
        operation_id=new_uuid(), input_product_id=product_id, name="Rendimiento",
        tolerance_pct=str(abs(Decimal("100") - total)), outputs=outputs, user_id="alice",
        species_id=species_id))
    assert creado.success, creado.message
    for caso, quien in ((SubmitYieldVersionUseCase, "alice"),
                        (ApproveYieldVersionUseCase, "bob"),
                        (ActivateYieldVersionUseCase, "bob")):
        r = caso(conn, auth).execute(YieldVersionTransitionCommand(
            operation_id=new_uuid(), version_id=creado.version_id, user_id=quien))
        assert r.success, r.message
    return creado.version_id
