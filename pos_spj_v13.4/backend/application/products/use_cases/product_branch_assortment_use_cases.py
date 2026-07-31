"""Branch/channel assignment use cases (§10) — habilitación por sucursal y surtido.

Un producto existe una sola vez y se **habilita** por sucursal (`branch_product`) y
se incluye en **surtidos por canal** (`assortments`/`assortment_products`) — nunca
se duplica por sucursal ni lleva precio/existencia aquí. Toda mutación exige
autorización (`ProductsAuthorizationPolicy.require`) y es transaccional (el caso de
uso hace commit; la UI nunca).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.permissions import ProductPermissions
from backend.domain.products.channel_enums import SalesChannel
from backend.domain.products.entities.assortment import Assortment, AssortmentProduct
from backend.domain.products.entities.branch_product import BranchProduct
from backend.domain.products.exceptions import ProductsDomainError
from backend.infrastructure.db.repositories.products.branch_assortment_repository import (
    BranchAssortmentRepository,
)

logger = logging.getLogger("spj.products.branch_assortment_uc")


@dataclass(frozen=True)
class BranchAssortmentResult:
    success: bool
    message: str
    entity_id: str | None = None


class _Base:
    permission: str = ""

    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = BranchAssortmentRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy()

    def _commit(self) -> None:
        self._conn.commit()

    def _rollback(self) -> None:
        rb = getattr(self._conn, "rollback", None)
        if rb is not None:
            rb()


class SetBranchProductUseCase(_Base):
    """Habilita/deshabilita un producto en una sucursal (idempotente por par)."""
    permission = ProductPermissions.BRANCH_ASSIGNMENT_MANAGE

    def execute(self, *, product_id: str, branch_id: str, enabled: bool,
                user_id: str, notes: str | None = None) -> BranchAssortmentResult:
        self._auth.require(user_id or "", self.permission)
        try:
            bp = BranchProduct(product_id=product_id, branch_id=branch_id,
                               enabled=bool(enabled), notes=notes)
        except ProductsDomainError as exc:
            return BranchAssortmentResult(False, str(exc))
        try:
            self._repo.set_branch_product(bp)
            self._commit()
        except Exception:
            self._rollback()
            logger.exception("set_branch_product failed pid=%s branch=%s",
                             product_id, branch_id)
            raise
        return BranchAssortmentResult(
            True, "BRANCH_PRODUCT_ENABLED" if enabled else "BRANCH_PRODUCT_DISABLED",
            bp.id)


class CreateAssortmentUseCase(_Base):
    """Crea un surtido para un canal (opcionalmente por sucursal)."""
    permission = ProductPermissions.ASSORTMENT_MANAGE

    def execute(self, *, name: str, channel: str, user_id: str,
                branch_id: str | None = None) -> BranchAssortmentResult:
        self._auth.require(user_id or "", self.permission)
        try:
            a = Assortment(name=name, channel=SalesChannel(channel),
                           branch_id=branch_id)
        except (ProductsDomainError, ValueError) as exc:
            return BranchAssortmentResult(False, str(exc))
        try:
            self._repo.save_assortment(a)
            self._commit()
        except Exception:
            self._rollback()
            logger.exception("create_assortment failed name=%s", name)
            raise
        return BranchAssortmentResult(True, "ASSORTMENT_CREATED", a.id)


class SetAssortmentProductUseCase(_Base):
    """Incluye/excluye un producto de un surtido (canal)."""
    permission = ProductPermissions.ASSORTMENT_MANAGE

    def execute(self, *, assortment_id: str, product_id: str, enabled: bool,
                user_id: str) -> BranchAssortmentResult:
        self._auth.require(user_id or "", self.permission)
        if self._repo.get_assortment(assortment_id) is None:
            return BranchAssortmentResult(False, "El surtido no existe")
        try:
            item = AssortmentProduct(assortment_id=assortment_id,
                                     product_id=product_id, enabled=bool(enabled))
        except ProductsDomainError as exc:
            return BranchAssortmentResult(False, str(exc))
        try:
            self._repo.add_to_assortment(item)
            self._commit()
        except Exception:
            self._rollback()
            logger.exception("set_assortment_product failed a=%s p=%s",
                             assortment_id, product_id)
            raise
        return BranchAssortmentResult(
            True, "ASSORTMENT_PRODUCT_ENABLED" if enabled else "ASSORTMENT_PRODUCT_DISABLED",
            item.id)
