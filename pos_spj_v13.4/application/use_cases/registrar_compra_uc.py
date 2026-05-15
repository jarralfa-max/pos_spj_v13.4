"""
application/use_cases/registrar_compra_uc.py
────────────────────────────────────────────
Caso de uso: Registrar una Compra a Proveedor.

Orquesta:  PurchaseService → RecipeEngine → AuditService
Sin dependencias de UI (PyQt5), DB directa ni SQL embebido.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("spj.uc.registrar_compra")


# ── DTOs ─────────────────────────────────────────────────────────────────────

@dataclass
class ItemCompraDTO:
    product_id: int
    qty: float
    unit_cost: float
    nombre: str


@dataclass
class DatosCompraDTO:
    proveedor_id: int
    proveedor_nombre: str
    sucursal_id: int
    usuario: str
    items: list[ItemCompraDTO]
    metodo_pago: str
    doc_ref: str
    subtotal: float
    iva_monto: float
    total: float
    notas: str = ""
    condicion_pago: str = "liquidado"
    plazo_dias: int = 0
    moneda: str = "MXN"


@dataclass
class ResultadoCompraDTO:
    ok: bool
    folio: str = ""
    error: str = ""
    recetas_procesadas: list[str] = field(default_factory=list)
    audit_before: dict = field(default_factory=dict)
    audit_after:  dict = field(default_factory=dict)


# ── Use Case ─────────────────────────────────────────────────────────────────

class RegistrarCompraUC:
    """
    Registro de compra a proveedor.

    Uso desde la UI:
        uc = RegistrarCompraUC(self.container)
        resultado = uc.execute(datos)
        if not resultado.ok:
            QMessageBox.critical(...)
    """

    def __init__(self, container: Any):
        self._container = container

    # ── Public API ────────────────────────────────────────────────────────────

    def execute(self, datos: DatosCompraDTO) -> ResultadoCompraDTO:
        svc = getattr(self._container, 'purchase_service', None)
        if not svc:
            return ResultadoCompraDTO(
                ok=False,
                error="PurchaseService no disponible. Reinicia la aplicación.",
            )

        try:
            items_svc = [
                {
                    'product_id': i.product_id,
                    'qty':        i.qty,
                    'unit_cost':  i.unit_cost,
                    'nombre':     i.nombre,
                }
                for i in datos.items
            ]

            notes = datos.doc_ref
            if datos.iva_monto > 0:
                notes = f"{datos.doc_ref} | IVA:{datos.iva_monto:.2f}"

            folio = svc.register_purchase(
                provider_id=datos.proveedor_id,
                branch_id=datos.sucursal_id,
                user=datos.usuario,
                items=items_svc,
                payment_method=datos.metodo_pago,
                amount_paid=(datos.total if datos.metodo_pago != "CREDITO" else 0),
                notes=notes,
            )

            # Persist payment condition fields (added in migration 071)
            try:
                self._container.db.execute(
                    "UPDATE compras SET condicion_pago=?, plazo_dias=?, moneda=? WHERE folio=?",
                    (datos.condicion_pago, datos.plazo_dias, datos.moneda, folio),
                )
            except Exception as _e:
                logger.warning("condicion_pago UPDATE skipped: %s", _e)

            recetas = self._procesar_recetas(datos)
            after   = self._build_audit_after(datos, folio)
            self._escribir_auditoria(datos, folio, after)

            return ResultadoCompraDTO(
                ok=True,
                folio=folio,
                recetas_procesadas=recetas,
                audit_before={},
                audit_after=after,
            )

        except Exception as e:
            logger.error("RegistrarCompraUC.execute: %s", e)
            return ResultadoCompraDTO(ok=False, error=str(e))

    # ── Private helpers ───────────────────────────────────────────────────────

    def _procesar_recetas(self, datos: DatosCompraDTO) -> list[str]:
        engine = getattr(self._container, 'recipe_engine', None)
        nombres: list[str] = []
        for item in datos.items:
            try:
                if engine and hasattr(engine, 'ejecutar_receta'):
                    engine.ejecutar_receta(
                        producto_id=item.product_id,
                        cantidad=item.qty,
                        usuario=datos.usuario,
                        sucursal_id=datos.sucursal_id,
                    )
                    nombres.append(item.nombre)
            except Exception as e:
                logger.warning("_procesar_recetas %s: %s", item.nombre, e)
        return nombres

    @staticmethod
    def _build_audit_after(datos: DatosCompraDTO, folio: str) -> dict:
        return {
            "folio":        folio,
            "proveedor_id": datos.proveedor_id,
            "sucursal_id":  datos.sucursal_id,
            "subtotal":     datos.subtotal,
            "iva_monto":    datos.iva_monto,
            "total":        datos.total,
            "metodo_pago":  datos.metodo_pago,
            "items_count":  len(datos.items),
        }

    def _escribir_auditoria(self, datos: DatosCompraDTO,
                             folio: str, after: dict) -> None:
        try:
            from core.services.auto_audit import audit_write
            detalles = (
                f"Folio {folio} | {datos.proveedor_nombre} | "
                f"${datos.total:.2f} | {datos.metodo_pago}"
            )
            if datos.iva_monto > 0:
                detalles += f" | IVA ${datos.iva_monto:.2f}"
            audit_write(
                self._container,
                modulo="COMPRAS",
                accion="COMPRA_REGISTRADA",
                entidad="compras",
                entidad_id=folio,
                usuario=datos.usuario,
                detalles=detalles,
                before={},
                after=after,
                sucursal_id=datos.sucursal_id,
            )
        except Exception as e:
            logger.debug("audit_write: %s", e)
