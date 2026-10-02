"""Vocabulario de permisos de Logística, publicado para el catálogo canónico.

`LogisticsPermissions` vive en `authorization.py` (junto a la política que lo
exige); aquí sólo se exporta `ALL_LOGISTICS_PERMISSIONS` con la forma que
`backend/application/security/permission_catalog.py` deriva. Sin este archivo
LOGISTICA no aparecía en Configuración → Seguridad → Permisos y nadie que no
fuera administrador podía recibir un embarque.
"""

from __future__ import annotations

from backend.application.logistics.authorization import LogisticsPermissions

ALL_LOGISTICS_PERMISSIONS = frozenset(
    value for key, value in vars(LogisticsPermissions).items()
    if not key.startswith("_") and isinstance(value, str)
)
