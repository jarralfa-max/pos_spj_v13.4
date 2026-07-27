from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional


class CartViewModel:
    """UI-focused cart state holder, independent from persistence/services."""

    def __init__(self, items: Optional[List[Dict[str, Any]]] = None):
        self._items: List[Dict[str, Any]] = []
        for it in (items or []):
            self.add_item(dict(it))

    @property
    def items(self) -> List[Dict[str, Any]]:
        return self._items

    def clear(self) -> None:
        self._items.clear()

    def add_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(item)
        out.setdefault('_uid', uuid.uuid4().hex)
        out.setdefault('cantidad', 0.0)
        out.setdefault('precio_unitario', 0.0)
        out.setdefault('descuento_pct', 0.0)
        out['total'] = float(out.get('total', float(out['cantidad']) * float(out['precio_unitario'])))
        self._items.append(out)
        return out

    def remove_by_uid(self, uid: str) -> bool:
        before = len(self._items)
        self._items = [it for it in self._items if it.get('_uid') != uid]
        return len(self._items) != before

    def update_quantity(self, uid: str, qty: float) -> bool:
        for it in self._items:
            if it.get('_uid') == uid:
                it['cantidad'] = float(qty)
                it['total'] = round(float(qty) * float(it.get('precio_unitario', 0.0)), 2)
                return True
        return False

    def selected(self, uid: str) -> Optional[Dict[str, Any]]:
        for it in self._items:
            if it.get('_uid') == uid:
                return it
        return None

    def to_item_carrito_payload(self) -> List[Dict[str, Any]]:
        return [
            {
                'producto_id': it.get('id'),
                'cantidad': float(it.get('cantidad', 0.0)),
                'precio_unit': float(it.get('precio_unitario', 0.0)),
                'nombre': it.get('nombre', ''),
                'es_compuesto': int(it.get('es_compuesto', 0) or 0),
            }
            for it in self._items
        ]
