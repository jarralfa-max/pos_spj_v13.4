# state/priority_queue.py — Cola de prioridad para pedidos
"""
Prioriza pedidos por: hora entrega, tipo cliente, urgencia.
"""
from __future__ import annotations
import heapq
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any

logger = logging.getLogger("wa.queue")


@dataclass(order=True)
class PedidoEnCola:
    priority: int = field(compare=True)       # Menor = más urgente
    timestamp: float = field(compare=True)
    pedido_data: Dict[str, Any] = field(compare=False)
    phone: str = field(compare=False, default="")
    sucursal_id: int = field(compare=False, default=1)


class PedidoPriorityQueue:
    """Cola de prioridad thread-safe para pedidos entrantes."""

    # Prioridades (menor número = más urgente)
    PRIORIDAD_URGENTE = 1         # Pedido para hoy, cliente VIP
    PRIORIDAD_NORMAL = 5          # Pedido estándar
    PRIORIDAD_PROGRAMADO = 10     # Pedido programado a futuro

    def __init__(self):
        self._heap: List[PedidoEnCola] = []
        self._counter = 0

    def calcular_prioridad(self, fecha_entrega: str,
                           cliente_tipo: str = "normal",
                           es_urgente: bool = False) -> int:
        """Calcula prioridad numérica del pedido."""
        base = self.PRIORIDAD_NORMAL

        # Urgencia
        if es_urgente:
            base = self.PRIORIDAD_URGENTE
        elif fecha_entrega:
            try:
                fecha = datetime.fromisoformat(fecha_entrega)
                horas_hasta = (fecha - datetime.now()).total_seconds() / 3600
                if horas_hasta <= 2:
                    base = self.PRIORIDAD_URGENTE
                elif horas_hasta <= 24:
                    base = self.PRIORIDAD_NORMAL
                else:
                    base = self.PRIORIDAD_PROGRAMADO
            except Exception:
                pass

        # Tipo de cliente
        if cliente_tipo in ("vip", "mayorista", "credito"):
            base = max(1, base - 2)

        return base

    def push(self, pedido_data: dict, phone: str,
             sucursal_id: int, prioridad: int):
        """Agrega un pedido a la cola."""
        item = PedidoEnCola(
            priority=prioridad,
            timestamp=datetime.now().timestamp(),
            pedido_data=pedido_data,
            phone=phone,
            sucursal_id=sucursal_id,
        )
        heapq.heappush(self._heap, item)
        logger.info("Pedido en cola: %s, prioridad=%d, sucursal=%d",
                     phone, prioridad, sucursal_id)

    def pop(self) -> Optional[PedidoEnCola]:
        """Saca el pedido de mayor prioridad."""
        if self._heap:
            return heapq.heappop(self._heap)
        return None

    def size(self) -> int:
        return len(self._heap)

    def pending_for_sucursal(self, sucursal_id: int) -> int:
        return sum(1 for p in self._heap if p.sucursal_id == sucursal_id)
