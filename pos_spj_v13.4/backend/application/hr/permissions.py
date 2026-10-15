"""Permisos de RR. HH. (auditoría cebf67a HR-01): vocabulario ``RRHH.<accion>``.

El dominio declara los códigos (``HRPermission``) porque su política los
valida; este módulo los publica al catálogo central, que deriva sus entradas
de cada ``ALL_*_PERMISSIONS``. La clave ``RRHH`` ya existía (la exige el menú y
la siembra ``m000`` con sus acciones gruesas); la migración 335 siembra estas
acciones granulares en los roles que ya tenían RRHH.
"""

from __future__ import annotations

from backend.domain.hr.policies.authorization_policy import (
    HR_PERMISSIONS,
    HR_READ_PERMISSIONS,
    HRPermission,
)

HRPermissions = HRPermission

ALL_HR_PERMISSIONS = frozenset(HR_PERMISSIONS)

#: Lo que recibe un rol de consulta (``solo_lectura``).
HR_READ_ONLY_PERMISSIONS = frozenset(HR_READ_PERMISSIONS)
