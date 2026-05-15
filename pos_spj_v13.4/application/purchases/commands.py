"""
application/purchases/commands.py
──────────────────────────────────
Comandos (DTOs de entrada) para el módulo de Compras.

RegisterPurchaseCommand es el superconjunto de DatosCompraDTO:
  - Compatible hacia atrás con todos los campos de DatosCompraDTO
  - Agrega document_type para el flujo PR/PO (Phase 3)
  - Agrega po_id para recepciones vinculadas a PO (Phase 4)

La UI construye este comando y lo pasa a TraditionalPurchaseUC.execute().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from application.purchases.states import DocumentType


@dataclass
class PurchaseItemCommand:
    """Una partida de compra (producto + cantidad + costo)."""
    product_id: int
    qty:        float
    unit_cost:  float
    nombre:     str
    lote:       str = ""
    fecha_caducidad: str = ""

    @property
    def subtotal(self) -> float:
        return round(self.qty * self.unit_cost, 4)


@dataclass
class RegisterPurchaseCommand:
    """
    Comando para registrar una compra (directa, PR o PO).

    Phase 2: document_type siempre DIRECT — los tipos PR/PO se
    activarán en Phase 3 cuando se implementen las tablas.
    """
    # ── Datos del proveedor ──────────────────────────────────────────────────
    proveedor_id:     int
    proveedor_nombre: str

    # ── Datos organizacionales ───────────────────────────────────────────────
    sucursal_id: int
    usuario:     str

    # ── Partidas ─────────────────────────────────────────────────────────────
    items: list[PurchaseItemCommand]

    # ── Datos financieros ────────────────────────────────────────────────────
    metodo_pago:    str
    subtotal:       float
    iva_monto:      float
    total:          float
    condicion_pago: str   = "liquidado"
    plazo_dias:     int   = 0
    moneda:         str   = "MXN"

    # ── Datos documentales ───────────────────────────────────────────────────
    doc_ref:       str = ""
    notas:         str = ""

    # ── PR/PO (Phase 3+) ─────────────────────────────────────────────────────
    document_type: DocumentType = DocumentType.DIRECT
    po_id:         Optional[int] = None    # solo si document_type == PO

    def to_datos_compra_dto(self):
        """
        Convierte al DTO legacy DatosCompraDTO para delegar a RegistrarCompraUC.
        Preserva 100 % de compatibilidad hacia atrás.
        """
        from application.use_cases.registrar_compra_uc import (
            DatosCompraDTO, ItemCompraDTO,
        )
        return DatosCompraDTO(
            proveedor_id=self.proveedor_id,
            proveedor_nombre=self.proveedor_nombre,
            sucursal_id=self.sucursal_id,
            usuario=self.usuario,
            items=[
                ItemCompraDTO(
                    product_id=i.product_id,
                    qty=round(float(i.qty), 6),
                    unit_cost=round(float(i.unit_cost), 6),
                    nombre=i.nombre,
                )
                for i in self.items
            ],
            metodo_pago=self.metodo_pago,
            doc_ref=self.doc_ref,
            subtotal=self.subtotal,
            iva_monto=self.iva_monto,
            total=self.total,
            notas=self.notas,
            condicion_pago=self.condicion_pago,
            plazo_dias=self.plazo_dias,
            moneda=self.moneda,
        )
