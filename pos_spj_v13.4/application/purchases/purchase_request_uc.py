# application/purchases/purchase_request_uc.py — SPJ POS v13.4
"""
Use Case: Purchase Request (Solicitud de Compra).
Creates and manages purchase requests that can later be converted to
actual purchases.  Does NOT touch inventory, finance, or CxP.
"""
from __future__ import annotations
import logging
from datetime import datetime

logger = logging.getLogger("spj.purchases.pr_uc")


class PurchaseRequestUC:
    def __init__(self, db):
        from repositories.purchase_request_repository import PurchaseRequestRepository
        self._repo = PurchaseRequestRepository(db)

    def _assert_schema(self) -> None:
        if not self._repo.schema_ready():
            raise RuntimeError(
                "La tabla purchase_requests no existe. "
                "Ejecuta las migraciones (migration 077) antes de usar esta función."
            )

    def crear_pr(self, *, solicitante: str, sucursal_id: int,
                 items: list[dict],
                 proveedor_id: int | None = None,
                 notas: str = "") -> int:
        """
        Creates a new Purchase Request in estado='borrador'.

        items: list of dicts with keys:
            producto_id (int), cantidad (float),
            costo_estimado (float, optional), unidad (str, optional)

        Returns the new PR id.
        Raises RuntimeError if schema is not ready.
        """
        self._assert_schema()

        if not items:
            raise ValueError("Una solicitud de compra debe tener al menos un ítem.")

        folio = f"PR-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        total_est = sum(
            float(it.get("cantidad", 1)) * float(it.get("costo_estimado", 0))
            for it in items
        )

        pr_id = self._repo.create(
            folio=folio,
            solicitante=solicitante,
            sucursal_id=sucursal_id,
            proveedor_id=proveedor_id,
            notas=notas,
            total_est=total_est,
        )

        for it in items:
            self._repo.add_item(
                pr_id=pr_id,
                producto_id=int(it["producto_id"]),
                cantidad=float(it.get("cantidad", 1)),
                costo_estimado=float(it.get("costo_estimado", 0)),
                unidad=str(it.get("unidad", "pz")),
                notas=str(it.get("notas", "")),
            )

        self._repo.add_event(
            pr_id=pr_id,
            evento="CREADO",
            usuario=solicitante,
            detalle=f"PR creado con {len(items)} ítem(s), total estimado ${total_est:,.2f}",
        )

        logger.info("PR %s creado (id=%d, items=%d)", folio, pr_id, len(items))
        return pr_id

    def aprobar(self, pr_id: int, usuario: str) -> None:
        self._assert_schema()
        pr = self._repo.get(pr_id)
        if not pr:
            raise ValueError(f"PR {pr_id} no encontrado.")
        if pr["estado"] not in ("borrador", "pendiente"):
            raise ValueError(f"No se puede aprobar un PR en estado '{pr['estado']}'.")
        self._repo.update_estado(pr_id, "aprobado")
        self._repo.add_event(pr_id=pr_id, evento="APROBADO", usuario=usuario)
        logger.info("PR %d aprobado por %s", pr_id, usuario)

    def cancelar(self, pr_id: int, usuario: str, motivo: str = "") -> None:
        self._assert_schema()
        self._repo.update_estado(pr_id, "cancelado")
        self._repo.add_event(
            pr_id=pr_id, evento="CANCELADO", usuario=usuario, detalle=motivo
        )
        logger.info("PR %d cancelado por %s", pr_id, usuario)

    def listar(self, sucursal_id: int, estado: str | None = None) -> list[dict]:
        self._assert_schema()
        return self._repo.list_by_branch(sucursal_id, estado=estado)
