"""§2/§25 — una versión NUEVA de la receta en Productos no cambia una orden ya
liberada. Mezcla de carne molida (formulación): la v1 lleva res y cerdo 70/30;
después se activa la v2 (50/50, por el flujo real enviar → aprobar → activar) y
la orden liberada sigue consumiendo y reservando la v1.
"""
from __future__ import annotations

from decimal import Decimal

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_recipe_commands import (
    RecipeVersionTransitionCommand,
)
from backend.application.products.use_cases.product_recipe_use_cases import (
    ActivateRecipeVersionUseCase,
    ApproveRecipeVersionUseCase,
    SubmitRecipeVersionUseCase,
)
from backend.domain.meat_processing.enums import ProcessType
from backend.domain.products.entities.recipe_component import RecipeComponent
from backend.domain.products.entities.recipe_version import RecipeVersion
from backend.domain.products.recipe_enums import RecipeVersionStatus
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.infrastructure.db.repositories.products.recipe_repository import RecipeRepository
from backend.shared.ids import new_uuid
from tests.integration.meat_processing._generic_plant import KG, Planta, _Todo, build_db


def _activate_v2(conn, v1_id, componentes):
    """Productos no tiene todavía un caso de uso "nueva versión"; la v2 se crea
    con su propio repositorio y entidad, y recorre el flujo real de activación
    (que sustituye a la v1)."""
    repo = RecipeRepository(conn)
    v1 = repo.get_version(v1_id)
    v2 = RecipeVersion(recipe_id=v1.recipe_id, version_number=2,
                       status=RecipeVersionStatus.DRAFT, created_by="carol",
                       components=[RecipeComponent(component_product_id=p, quantity=Decimal(q),
                                                   unit_id=KG) for p, q in componentes])
    repo.save_version(v2)
    conn.commit()
    auth = ProductsAuthorizationPolicy(_Todo())
    for caso, quien in ((SubmitRecipeVersionUseCase, "carol"),
                        (ApproveRecipeVersionUseCase, "dave"),
                        (ActivateRecipeVersionUseCase, "dave")):
        r = caso(conn, auth).execute(RecipeVersionTransitionCommand(
            operation_id=new_uuid(), version_id=v2.id, user_id=quien))
        assert r.success, r.message
    assert repo.get_version(v1_id).status is RecipeVersionStatus.SUPERSEDED
    return v2.id


def test_a_new_active_recipe_version_does_not_touch_the_released_order():
    conn = build_db()
    p = Planta(conn)
    res = p.producto("Carne de res para moler", lote=True)
    cerdo = p.producto("Carne de cerdo para moler", lote=True)
    mezcla = p.producto("Mezcla molida res-cerdo", lote=True)
    v1 = p.receta(mezcla, [(res, "0.7"), (cerdo, "0.3")])
    p.existencia(res, "50", lote="RES-1"); p.existencia(cerdo, "50", lote="CER-1")

    oid = p.lista(ProcessType.MIXING, mezcla, "10")
    assert (p.reservado(res), p.reservado(cerdo)) == (Decimal("7"), Decimal("3"))

    v2 = _activate_v2(conn, v1, [(res, "0.5"), (cerdo, "0.5")])

    foto = MeatProcessingUnitOfWork(conn).recipe_snapshots.get_by_order(oid)
    assert foto.recipe_version_id == v1 and foto.recipe_version_id != v2
    assert {i.product_id: i.quantity_per_basis for i in foto.inputs} == {
        res: Decimal("0.7"), cerdo: Decimal("0.3")}

    p.costo(res, "120"); p.costo(cerdo, "90")
    r = p.ejecutar(oid, {mezcla: "10"})
    assert r.success, r.message
    # Consumió lo reservado por la v1, no lo que diría la v2.
    assert (p.saldo(res), p.saldo(cerdo)) == (Decimal("43"), Decimal("47"))


def test_an_order_prepared_after_the_change_freezes_the_new_version():
    conn = build_db()
    p = Planta(conn)
    res = p.producto("Carne de res para moler")
    cerdo = p.producto("Carne de cerdo para moler")
    mezcla = p.producto("Mezcla molida res-cerdo")
    v1 = p.receta(mezcla, [(res, "0.7"), (cerdo, "0.3")])
    p.existencia(res, "50"); p.existencia(cerdo, "50")
    v2 = _activate_v2(conn, v1, [(res, "0.5"), (cerdo, "0.5")])

    oid = p.lista(ProcessType.MIXING, mezcla, "10")
    foto = MeatProcessingUnitOfWork(conn).recipe_snapshots.get_by_order(oid)
    assert foto.recipe_version_id == v2
    assert (p.reservado(res), p.reservado(cerdo)) == (Decimal("5"), Decimal("5"))
