# models/context.py — Contexto de conversación persistente
"""
Cada teléfono tiene un contexto que persiste entre mensajes.
Estado de la conversación, sucursal, pedido en curso, etc.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class FlowState(str, Enum):
    """Estados posibles de la conversación."""
    IDLE = "idle"                                  # Sin flujo activo
    # Sucursal
    SELECTING_BRANCH = "selecting_branch"          # Esperando selección de sucursal
    # Pedido
    PEDIDO_CATEGORIA = "pedido_categoria"           # Eligiendo categoría
    PEDIDO_PRODUCTO = "pedido_producto"             # Eligiendo producto
    PEDIDO_CANTIDAD = "pedido_cantidad"             # Indicando cantidad
    PEDIDO_MAS_PRODUCTOS = "pedido_mas_productos"  # ¿Agregar más?
    PEDIDO_TIPO_ENTREGA = "pedido_tipo_entrega"    # Sucursal o domicilio
    PEDIDO_DIRECCION = "pedido_direccion"           # Capturando dirección
    PEDIDO_FECHA = "pedido_fecha"                   # Fecha de entrega
    PEDIDO_CONFIRMACION = "pedido_confirmacion"     # Confirmar pedido
    # Cotización
    COTIZACION_ARMANDO = "cotizacion_armando"
    COTIZACION_CONFIRMACION = "cotizacion_confirmacion"
    # Pago
    PAGO_METODO = "pago_metodo"                    # Eligiendo método de pago
    PAGO_ESPERANDO = "pago_esperando"              # Esperando confirmación
    # Registro
    REGISTRO_NOMBRE = "registro_nombre"            # Capturando nombre
    REGISTRO_CONFIRMACION = "registro_confirmacion"
    # Estado de pedido
    CONSULTA_FOLIO = "consulta_folio"


@dataclass
class PedidoItem:
    """Un item dentro del pedido en curso."""
    producto_id: int
    nombre: str
    cantidad: float
    unidad: str = "kg"
    precio_unitario: float = 0.0

    @property
    def subtotal(self) -> float:
        return self.cantidad * self.precio_unitario

    def to_dict(self) -> dict:
        return {
            "producto_id": self.producto_id,
            "nombre": self.nombre,
            "cantidad": self.cantidad,
            "unidad": self.unidad,
            "precio_unitario": self.precio_unitario,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PedidoItem":
        return cls(**d)


@dataclass
class ConversationContext:
    """Contexto completo de una conversación."""
    phone: str
    state: FlowState = FlowState.IDLE
    sucursal_id: Optional[int] = None
    sucursal_nombre: str = ""
    cliente_id: Optional[int] = None
    cliente_nombre: str = ""

    # Pedido en curso
    pedido_items: List[PedidoItem] = field(default_factory=list)
    pedido_tipo_entrega: str = ""          # "sucursal" | "domicilio"
    pedido_direccion: str = ""
    pedido_fecha_entrega: str = ""         # ISO date
    pedido_programado: bool = False

    # Cotización en curso
    cotizacion_items: List[PedidoItem] = field(default_factory=list)

    # Temporal: producto seleccionado esperando cantidad
    _producto_temp: Optional[Dict] = field(default_factory=lambda: None)

    # Control
    failed_intents: int = 0
    last_activity: datetime = field(default_factory=datetime.now)
    numero_tipo: str = ""                  # Tipo del número que recibió el msg

    def reset_flow(self):
        """Limpia el flujo actual pero mantiene sucursal y cliente."""
        self.state = FlowState.IDLE
        self.pedido_items = []
        self.pedido_tipo_entrega = ""
        self.pedido_direccion = ""
        self.pedido_fecha_entrega = ""
        self.pedido_programado = False
        self.cotizacion_items = []
        self._producto_temp = None
        self.failed_intents = 0

    def total_pedido(self) -> float:
        return sum(i.subtotal for i in self.pedido_items)

    def resumen_pedido(self) -> str:
        if not self.pedido_items:
            return "Carrito vacío"
        lines = []
        for it in self.pedido_items:
            lines.append(f"• {it.nombre}: {it.cantidad} {it.unidad} — ${it.subtotal:.2f}")
        lines.append(f"\n*Total: ${self.total_pedido():.2f}*")
        return "\n".join(lines)
