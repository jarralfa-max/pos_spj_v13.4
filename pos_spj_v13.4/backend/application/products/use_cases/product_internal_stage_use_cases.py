"""SetInternalStageUseCase (PROD-6, §13) — transiciona la etapa interna de un
producto (NONE/INTERNAL_ONLY/WORK_IN_PROGRESS/SEMI_FINISHED/PROCESS_INTERMEDIATE).

`internal_product_policy.is_transformation()` existía desde antes con
cobertura de tests unitarios, pero CERO llamadores reales (confirmado por
grep) — nada en la aplicación podía ni siquiera fijar `internal_stage` en
primer lugar (`ProductMasterRepository.create/update` no incluían la columna
en su SQL). Este caso de uso es el primer punto real donde la regla de §13 se
hace cumplir: mover a una etapa que representa una transformación real
(WIP → semi-terminado → terminado) exige un producto distinto con una
relación técnica explícita — nunca mutar la identidad existente. Un cambio
que NO es transformación (p. ej. NONE → INTERNAL_ONLY, o mismo stage) se
permite en el lugar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.application.products.audit import record_product_audit_entry
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_internal_stage_commands import (
    SetInternalStageCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.domain.products.internal_enums import INTERNAL_STAGES, InternalStage
from backend.domain.products.policies.internal_product_policy import is_transformation

logger = logging.getLogger("spj.products.internal_stage_use_cases")


@dataclass(frozen=True)
class InternalStageResult:
    success: bool
    product_id: str | None
    message: str


class SetInternalStageUseCase:
    name = "SetInternalStageUseCase"

    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._auth = authorization or ProductsAuthorizationPolicy.permissive_for_tests()

    def execute(self, command: SetInternalStageCommand) -> InternalStageResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.INTERNAL_EDIT)
        row = self._conn.execute(
            "SELECT internal_stage, sellable FROM products WHERE id=?",
            (command.product_id,)).fetchone()
        if row is None:
            return InternalStageResult(False, None, "El producto no existe")
        try:
            from_stage = InternalStage(row["internal_stage"] or "NONE")
            to_stage = InternalStage(command.stage)
        except ValueError as exc:
            return InternalStageResult(False, None, str(exc))
        if is_transformation(from_stage, to_stage):
            return InternalStageResult(
                False, None,
                f"{from_stage.value} → {to_stage.value} es una transformación real "
                "(§13): requiere un producto distinto y una relación técnica "
                "explícita, no puede mutarse en el mismo producto")
        # §13: entrar a una etapa interna fuerza internal_only=True — igual que
        # Product.__post_init__ — y eso es incompatible con sellable=True.
        if to_stage in INTERNAL_STAGES and bool(row["sellable"]):
            return InternalStageResult(
                False, None,
                "No se puede mover a una etapa interna: el producto es vendible "
                "(§13, un producto interno no puede ser vendible)")
        try:
            self._conn.execute(
                "UPDATE products SET internal_stage=?, "
                "internal_only=CASE WHEN ? THEN 1 ELSE internal_only END, "
                "updated_at=datetime('now') WHERE id=?",
                (to_stage.value, to_stage in INTERNAL_STAGES, command.product_id))
            record_product_audit_entry(
                self._conn, action="PRODUCT_INTERNAL_STAGE_CHANGED",
                entity_id=command.product_id, user_id=command.user_id,
                operation_id=command.operation_id,
                before={"internal_stage": from_stage.value},
                after={"internal_stage": to_stage.value})
            self._conn.commit()
        except Exception:
            rb = getattr(self._conn, "rollback", None)
            if rb is not None:
                rb()
            logger.exception("set internal stage failed op=%s", command.operation_id)
            raise
        return InternalStageResult(True, command.product_id,
                                   "PRODUCT_INTERNAL_STAGE_CHANGED")
