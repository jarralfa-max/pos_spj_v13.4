"""Permisos del contexto de CALIDAD (`CALIDAD.accion`).

Calidad es dueña de la inspección y de la liberación. Procesamiento sólo puede
SOLICITAR una inspección (concesión de integración); decidir exige
`CALIDAD.inspeccion.decidir`, que se siembra a gerente/admin/system_owner y NO
al rol que produce. Además, a nivel de usuario, quien produjo nunca decide.
"""

from __future__ import annotations


class QualityPermissions:
    INSPECTION_VIEW = "CALIDAD.inspeccion.ver"
    INSPECTION_REQUEST = "CALIDAD.inspeccion.solicitar"
    INSPECTION_DECIDE = "CALIDAD.inspeccion.decidir"


ALL_QUALITY_PERMISSIONS = frozenset(
    value for name, value in vars(QualityPermissions).items()
    if not name.startswith("_") and isinstance(value, str)
)
