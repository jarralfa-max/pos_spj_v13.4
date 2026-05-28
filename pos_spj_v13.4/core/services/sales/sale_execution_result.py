from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SaleExecutionItem:
    product_id: int
    nombre: str
    cantidad: float
    precio_unitario: float
    subtotal: float
    descuento: float
    total: float
    es_compuesto: int = 0


@dataclass
class SalePaymentResult:
    forma_pago: str
    total_pagado: float
    efectivo_recibido: float
    tarjeta: float
    transferencia: float
    credito: float
    mercado_pago: float
    cambio: float
    saldo_credito: float
    lineas: Dict[str, float] = field(default_factory=dict)


@dataclass
class SaleLoyaltyResult:
    cliente_id: Optional[int]
    puntos_canjeados: int
    descuento_puntos: float
    puntos_ganados: int
    puntos_totales: int
    nivel: str
    mensaje: str
    operation_id: str


@dataclass
class SaleExecutionResult:
    ok: bool
    venta_id: int
    folio: str
    operation_id: str
    subtotal: float
    descuento_total: float
    total: float
    items: List[SaleExecutionItem] = field(default_factory=list)
    payment: Optional[SalePaymentResult] = None
    loyalty: Optional[SaleLoyaltyResult] = None
    ticket_payload: Dict[str, Any] = field(default_factory=dict)
    ticket_html: str = ""
    warnings: List[str] = field(default_factory=list)
    error: str = ""
