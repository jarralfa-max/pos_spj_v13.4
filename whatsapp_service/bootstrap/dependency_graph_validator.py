# bootstrap/dependency_graph_validator.py — WA-4
"""
Valida que un `WhatsAppCompositionRoot` recién construido tenga todos los
servicios que él mismo declara requeridos (`composition_root.REQUIRED_SERVICES`)
— una guarda real, no decorativa: si una fase futura agrega un nombre a
`REQUIRED_SERVICES` pero olvida registrarlo en `_build()`, el arranque debe
fallar de forma clara en vez de que el primer consumidor real reciba un
`ServiceNotRegisteredError` confuso mucho más tarde, en medio de un
webhook.
"""
from __future__ import annotations

from typing import List


class CompositionRootValidationError(RuntimeError):
    """El CompositionRoot no registró uno o más servicios requeridos."""


def validate_composition_root(root) -> None:
    """Lanza `CompositionRootValidationError` si falta algún servicio de
    `composition_root.REQUIRED_SERVICES`. No retorna nada en éxito."""
    from bootstrap.composition_root import REQUIRED_SERVICES

    missing: List[str] = [name for name in REQUIRED_SERVICES if not root.registry.has(name)]
    if missing:
        raise CompositionRootValidationError(
            "WhatsAppCompositionRoot incompleto — faltan servicios requeridos: "
            + ", ".join(missing)
        )
