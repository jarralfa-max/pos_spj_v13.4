# sync/domain_validators/base.py — SPJ POS v13.3
"""
Clase base abstracta para validadores de dominio en sync.

Un DomainValidator se ejecuta DESPUÉS de la resolución genérica
del ConflictResolver. Si validate() retorna un string (mensaje de error),
el conflicto se escala a MANUAL_REVIEW. Si retorna None, se acepta.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class DomainValidator(ABC):
    """
    Interfaz para validadores de dominio.

    Implementar validate() con las reglas de negocio específicas.
    El método recibe:
      - tabla:    nombre de la tabla SQL afectada
      - resolved: payload resultante de la resolución genérica
      - local:    payload local (antes del sync)
      - remote:   payload remoto (recibido del servidor)

    Retorna:
      - None:  validación exitosa, aceptar la resolución
      - str:   mensaje de error → escalar a MANUAL_REVIEW
    """

    @abstractmethod
    def validate(
        self,
        tabla: str,
        resolved: dict,
        local: dict,
        remote: dict,
    ) -> Optional[str]:
        ...
