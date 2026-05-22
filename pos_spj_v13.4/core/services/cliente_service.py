# core/services/cliente_service.py
"""Servicio de administración para el módulo Clientes."""
from __future__ import annotations
import logging
from typing import Dict, List, Optional

from repositories.cliente_repository import ClienteRepository

logger = logging.getLogger("spj.service.clientes")


class ClienteService:
    """Fachada para operaciones de clientes. UI llama solo a este servicio."""

    def __init__(self, db):
        self._repo = ClienteRepository(db)

    # ── Consultas ─────────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        """Devuelve estadísticas agregadas: total, activos, con tarjeta, puntos."""
        return self._repo.get_stats_aggregate()

    def get_filtered(self, filtro: str = "todos") -> List[Dict]:
        """Get clientes with state filter: activos, inactivos, todos."""
        return self._repo.get_filtered(filtro)

    def search(self, termino: str, filtro: str = "todos") -> List[Dict]:
        """Search clientes by name, phone, id or QR."""
        if not termino.strip():
            return self.get_filtered(filtro)
        return self._repo.buscar_por_termino(termino.strip(), filtro)

    def get_by_id(self, cliente_id: int) -> Optional[Dict]:
        """Get complete client data by ID."""
        return self._repo.get_by_id(cliente_id)

    def get_historial(self, cliente_id: int) -> List[Dict]:
        """Get purchase history for a client."""
        return self._repo.get_historial_compras(cliente_id)

    def get_movimientos_puntos(self, cliente_id: int) -> List[Dict]:
        """Get loyalty points movements for a client."""
        return self._repo.get_movimientos_puntos(cliente_id)

    # ── Mutaciones ────────────────────────────────────────────────────────

    def crear(self, nombre: str, telefono: str = "", email: str = "",
              direccion: str = "", notas: str = "") -> int:
        """Create a new client."""
        return self._repo.crear(nombre, telefono, email, direccion, notas)

    def actualizar(self, cliente_id: int, **campos) -> bool:
        """Update client fields."""
        return self._repo.actualizar(cliente_id, **campos)

    def dar_de_baja(self, cliente_id: int) -> bool:
        """Soft-delete: mark inactive, preserve history."""
        return self._repo.dar_de_baja(cliente_id)

    def actualizar_puntos(self, cliente_id: int, nuevos_puntos: float) -> bool:
        """Update loyalty points balance."""
        return self._repo.actualizar_puntos(cliente_id, nuevos_puntos)
