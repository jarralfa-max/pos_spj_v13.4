# sync/domain_validators/__init__.py — SPJ POS v13.3
"""
Validadores de dominio para resolución de conflictos de sync.

Cada validador implementa reglas de negocio específicas que
la estrategia genérica (LWW, ADDITIVE, SERVER_AUTH) no cubre.

Uso:
    from sync.domain_validators import get_default_validators
    resolver = ConflictResolver(db, validators=get_default_validators())
"""
from sync.domain_validators.base import DomainValidator
from sync.domain_validators.inventory_validator import InventoryValidator
from sync.domain_validators.sales_validator import SalesValidator
from sync.domain_validators.production_validator import ProductionValidator


def get_default_validators(allow_negative_stock: bool = False) -> list:
    """Retorna el set estándar de validadores para SPJ POS."""
    return [
        InventoryValidator(allow_negative=allow_negative_stock),
        SalesValidator(),
        ProductionValidator(),
    ]


__all__ = [
    "DomainValidator",
    "InventoryValidator",
    "SalesValidator",
    "ProductionValidator",
    "get_default_validators",
]
