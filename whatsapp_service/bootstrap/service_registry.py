# bootstrap/service_registry.py — WA-4
"""
Registro de servicios construidos por el `WhatsAppCompositionRoot` (§8 del
prompt maestro). Separa "quién construye" (`composition_root.py`) de
"quién expone" (este módulo) — los flows/routers deben pedir un servicio
puntual por nombre (o vía los accesores tipados del CompositionRoot),
nunca recibir el `CompositionRoot` completo como dependencia (regla
explícita de §8: "No exponer un contenedor completo a flows").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


class ServiceNotRegisteredError(KeyError):
    """Se pidió un servicio que el CompositionRoot todavía no construye.

    Ver la tabla de servicios pendientes por fase en
    `composition_root.py` antes de asumir que es un bug — puede ser
    simplemente una capacidad que otra fase (WA-N) todavía no construyó.
    """


@dataclass
class ServiceRegistry:
    """Contenedor simple nombre → instancia. Sin resolución perezosa ni
    inyección automática por tipo — el CompositionRoot decide el orden de
    construcción explícitamente; este registro solo almacena el resultado."""

    _services: Dict[str, Any] = field(default_factory=dict)

    def register(self, name: str, instance: Any) -> None:
        if not name:
            raise ValueError("El nombre del servicio no puede estar vacío")
        if instance is None:
            raise ValueError(f"No se puede registrar None como servicio '{name}'")
        self._services[name] = instance

    def get(self, name: str) -> Any:
        try:
            return self._services[name]
        except KeyError:
            raise ServiceNotRegisteredError(
                f"Servicio '{name}' no registrado en este proceso."
            ) from None

    def has(self, name: str) -> bool:
        return name in self._services

    def names(self) -> List[str]:
        return sorted(self._services.keys())
