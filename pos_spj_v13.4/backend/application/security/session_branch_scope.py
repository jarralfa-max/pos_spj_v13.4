"""Las sucursales ASIGNADAS de una sesión, leídas de un solo modo (Fase 10).

`ApplicationContext.assigned_branch_ids` se empezó a poblar el 2026-09-17
(`usuarios_sucursales`) precisamente porque los contextos de ejecución de
Inventario, Mermas y Cárnico leen ese nivel de alcance. Pero sus composition
roots seguían construyéndolo como `frozenset({branch})`: la asignación se
escribía y NADIE la leía, así que `VIEW_ASSIGNED_BRANCHES` no concedía nada y
un gerente asignado a una segunda sucursal no podía aprobar ahí.

Medido el 2026-09-21 en copia de la base real: Corregidora tiene un solo
usuario, así que ninguna orden de despiece suya podía aprobarse jamás —quien
crea no aprueba— aunque se asignara otro usuario a la sucursal.

Un solo lector, no uno por módulo. Vacío NO significa "ninguna sucursal":
significa "sin asignaciones explícitas", y entonces manda la sucursal propia.
"""

from __future__ import annotations


def assigned_branch_ids(session, active_branch_id: str) -> frozenset[str]:
    """Sucursales de alcance de la sesión: la activa más las asignadas.

    Acepta los dos nombres que exponen los objetos de sesión
    (`assigned_branch_ids` en inglés y `sucursales_asignadas` en español).
    """
    activa = str(active_branch_id or "").strip()
    asignadas: set[str] = {activa} if activa else set()
    for nombre in ("assigned_branch_ids", "sucursales_asignadas"):
        valor = getattr(session, nombre, None)
        if not valor:
            continue
        for sucursal in valor:
            texto = str(sucursal or "").strip()
            if texto:
                asignadas.add(texto)
    return frozenset(asignadas)
