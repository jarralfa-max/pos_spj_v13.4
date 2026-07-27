from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SaleExecutionItem:
    product_id: str  # UUIDv7 TEXT identity
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
    amount_paid_real: float = 0.0


@dataclass
class SaleLoyaltyResult:
    cliente_id: Optional[str]  # UUIDv7 TEXT identity
    puntos_canjeados: int
    descuento_puntos: float
    puntos_ganados: Optional[int]
    puntos_totales: Optional[int]
    nivel: Optional[str]
    mensaje: str
    operation_id: str
    available: bool = False


@dataclass
class SaleExecutionResult:
    ok: bool
    venta_id: str  # UUIDv7 TEXT identity
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
