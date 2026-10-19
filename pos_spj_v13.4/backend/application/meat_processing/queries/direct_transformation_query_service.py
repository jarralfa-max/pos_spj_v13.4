"""Transformación directa — qué se puede despiezar y qué se espera
(auditoría de Producción cárnica 32cfbf, 2026-10-16).

Origen: los LOTES ya recibidos y disponibles en el almacén de producción de la
sucursal, de productos con perfil de rendimiento activo. Nunca se vuelve a
registrar la compra ni se transforma mercancía pendiente de Calidad: esos lotes
se muestran, pero con el motivo por el que no se pueden usar.

Lo esperado sale de la MISMA foto que congela «Preparar»
(`ProductsRecipeSnapshotAdapter` + la estrategia de ejecución): el perfil de
rendimiento manda, así que kg esperados = entrada × % / 100 y el % mostrado es
ese mismo. No hay un segundo cálculo que pueda contradecir a la orden.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal

from backend.domain.meat_processing.enums import ProcessType

logger = logging.getLogger("spj.meat_processing.direct_transformation_query")

_KG = Decimal("0.001")
_HUNDRED = Decimal("100")
_NON_STOCK = ("WASTE", "LOSS")
_QUALITY_LABELS = {
    "RELEASED": "Liberado", "PENDING_INSPECTION": "Pendiente de inspección en Calidad",
    "QUARANTINED": "En cuarentena", "BLOCKED": "Bloqueado", "REJECTED": "Rechazado",
}
OUTPUT_TYPE_LABELS = {
    "MAIN_PRODUCT": "Principal", "CO_PRODUCT": "Coproducto", "BY_PRODUCT": "Subproducto",
    "WASTE": "Merma", "LOSS": "Pérdida", "SEMI_FINISHED": "Semiterminado",
    "REWORKABLE": "Reprocesable",
}


@dataclass(frozen=True)
class DirectTransformationLot:
    lot_id: str
    product_id: str
    product_name: str
    warehouse_id: str
    warehouse_name: str
    available_kg: Decimal
    receipt_folio: str
    supplier_name: str
    received_at: str
    expiration_date: str
    quality_label: str
    #: Motivo por el que NO se puede transformar (vacío = se puede).
    blocked_reason: str = ""

    @property
    def eligible(self) -> bool:
        return not self.blocked_reason


@dataclass(frozen=True)
class DirectTransformationPreviewRow:
    product_id: str
    product_name: str
    output_type: str
    type_label: str
    expected_pct: Decimal
    expected_kg: Decimal
    goes_to_stock: bool


@dataclass(frozen=True)
class DirectTransformationPreview:
    problem: str | None
    rows: tuple[DirectTransformationPreviewRow, ...] = ()
    total_pct: Decimal = Decimal("0")
    #: Lo que el perfil no asigna a ninguna salida (100 % − suma): se clasifica
    #: como diferencia técnica, nunca se inventaría como producto.
    unassigned_kg: Decimal = Decimal("0")
    tolerance_pct: Decimal | None = None
    effective_version: str = ""
    names: dict = field(default_factory=dict)


class DirectTransformationQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── origen ──────────────────────────────────────────────────────────────
    def production_warehouses(self, branch_id: str) -> list[str]:
        from backend.application.logistics.warehouse_directory import (
            WarehouseDirectoryQueryService,
        )
        return WarehouseDirectoryQueryService(self._conn).warehouses_for_purpose(
            branch_id, "PRODUCTION")

    def products_with_active_yield(self) -> set[str]:
        try:
            filas = self._conn.execute(
                "SELECT DISTINCT yp.input_product_id FROM yield_profiles yp"
                " JOIN yield_profile_versions v ON v.yield_profile_id = yp.id"
                " WHERE COALESCE(yp.active, 1) = 1 AND v.status = 'ACTIVE'").fetchall()
        except sqlite3.OperationalError:
            return set()
        return {str(r[0]) for r in filas}

    def unavailable_reason(self, branch_id: str) -> str | None:
        """Por qué no hay nada que transformar, o None."""
        if not branch_id:
            return "La sesión no tiene sucursal activa."
        if not self.production_warehouses(branch_id):
            return ("La sucursal no tiene un almacén habilitado para producción. Márcalo en "
                    "Inventario → Almacenes (casilla «Producción»).")
        if not self.products_with_active_yield():
            return ("Ningún producto tiene un perfil de rendimiento ACTIVO. Créalo y actívalo "
                    "en Productos → Rendimientos.")
        if not self.lots(branch_id):
            return ("No hay existencia con lote de los productos con perfil de rendimiento en "
                    "el almacén de producción.")
        return None

    def lots(self, branch_id: str) -> list[DirectTransformationLot]:
        almacenes = self.production_warehouses(branch_id)
        productos = self.products_with_active_yield()
        if not almacenes or not productos:
            return []
        marcas_a = ",".join("?" for _ in almacenes)
        marcas_p = ",".join("?" for _ in productos)
        try:
            filas = self._conn.execute(
                "SELECT b.lot_id, b.product_id, p.name, b.warehouse_id, w.name,"
                " SUM(CAST(b.quantity AS REAL) - CAST(b.reserved_quantity AS REAL)),"
                " l.quality_status, l.expiration_date, l.created_at, l.origin_document_id"
                " FROM inventory_balances b"
                " JOIN inventory_lots l ON l.id = b.lot_id"
                " JOIN products p ON p.id = b.product_id"
                " LEFT JOIN warehouses w ON w.id = b.warehouse_id"
                f" WHERE b.branch_id = ? AND b.warehouse_id IN ({marcas_a})"
                f" AND b.product_id IN ({marcas_p}) AND b.inventory_status = 'AVAILABLE'"
                " AND COALESCE(b.lot_id, '') <> ''"
                " GROUP BY b.lot_id, b.product_id, b.warehouse_id"
                " ORDER BY l.created_at", (branch_id, *almacenes, *productos)).fetchall()
        except sqlite3.OperationalError:
            logger.exception("lotes para transformación directa no disponibles")
            return []
        resultado = []
        for (lot_id, pid, nombre, almacen, almacen_nombre, disponible, calidad, caducidad,
             creado, documento) in filas:
            kg = Decimal(str(disponible or 0)).quantize(_KG)
            if kg <= 0:
                continue
            folio, proveedor = self._receipt(documento)
            motivo = ""
            if calidad != "RELEASED":
                motivo = (f"Lote {_QUALITY_LABELS.get(calidad, calidad).lower()}: Calidad debe "
                          "liberarlo antes de transformarlo.")
            resultado.append(DirectTransformationLot(
                lot_id=str(lot_id), product_id=str(pid), product_name=str(nombre or ""),
                warehouse_id=str(almacen), warehouse_name=str(almacen_nombre or ""),
                available_kg=kg, receipt_folio=folio, supplier_name=proveedor,
                received_at=str(creado or "")[:10], expiration_date=str(caducidad or ""),
                quality_label=_QUALITY_LABELS.get(calidad, str(calidad or "")),
                blocked_reason=motivo))
        return resultado

    def lot(self, branch_id: str, lot_id: str) -> DirectTransformationLot | None:
        return next((x for x in self.lots(branch_id) if x.lot_id == lot_id), None)

    def _receipt(self, document_id) -> tuple[str, str]:
        """(folio de la recepción, proveedor) del documento que creó el lote."""
        if not document_id:
            return "", ""
        try:
            fila = self._conn.execute(
                "SELECT document_number, supplier_id FROM goods_receipts WHERE id=?",
                (document_id,)).fetchone()
        except sqlite3.OperationalError:
            return "", ""
        if fila is None:
            return "", ""
        return str(fila[0] or ""), self._supplier_name(fila[1])

    def _supplier_name(self, supplier_id) -> str:
        if not supplier_id:
            return ""
        for consulta in ("SELECT COALESCE(NULLIF(trade_name, ''), legal_name)"
                         " FROM supplier_master WHERE id=?",
                         "SELECT nombre FROM proveedores WHERE id=?"):
            try:
                fila = self._conn.execute(consulta, (supplier_id,)).fetchone()
            except sqlite3.OperationalError:
                continue
            if fila and fila[0]:
                return str(fila[0])
        return ""

    # ── lo esperado ─────────────────────────────────────────────────────────
    def preview(self, product_id: str, input_kg) -> DirectTransformationPreview:
        from backend.application.meat_processing.integrations.products_recipe_snapshot_adapter import (
            ProductsRecipeSnapshotAdapter,
        )
        from backend.domain.meat_processing.policies.master_data_requirement_policy import (
            ProcessingMasterDataRequirementPolicy,
        )
        from backend.domain.meat_processing.services.processing_execution_strategy import (
            strategy_for,
        )

        entrada = Decimal(str(input_kg or 0))
        snapshot = ProductsRecipeSnapshotAdapter(self._conn).resolve(
            target_product_id=product_id, process_type=ProcessType.DISASSEMBLY)
        chequeo = ProcessingMasterDataRequirementPolicy().check(
            ProcessType.DISASSEMBLY, snapshot)
        if not chequeo.ok:
            return DirectTransformationPreview(problem=chequeo.message())
        nombres = self._names([o.product_id for o in snapshot.outputs])
        filas = []
        total_pct = Decimal("0")
        for e in strategy_for(snapshot).expected_outputs(snapshot, entrada):
            total_pct += e.expected_yield_pct
            filas.append(DirectTransformationPreviewRow(
                product_id=e.product_id, product_name=nombres.get(e.product_id, ""),
                output_type=e.output_type,
                type_label=OUTPUT_TYPE_LABELS.get(e.output_type, e.output_type),
                expected_pct=e.expected_yield_pct, expected_kg=e.expected_weight,
                goes_to_stock=e.goes_to_stock))
        sin_asignar = ((_HUNDRED - total_pct) * entrada / _HUNDRED).quantize(_KG)
        return DirectTransformationPreview(
            problem=None, rows=tuple(filas), total_pct=total_pct, unassigned_kg=sin_asignar,
            tolerance_pct=snapshot.tolerance_pct, effective_version=snapshot.effective_version,
            names=nombres)

    def _names(self, product_ids) -> dict[str, str]:
        ids = sorted(set(product_ids))
        if not ids:
            return {}
        try:
            filas = self._conn.execute(
                f"SELECT id, name FROM products WHERE id IN ({','.join('?' for _ in ids)})",
                tuple(ids)).fetchall()
        except sqlite3.OperationalError:
            return {}
        return {str(r[0]): str(r[1] or "") for r in filas}
