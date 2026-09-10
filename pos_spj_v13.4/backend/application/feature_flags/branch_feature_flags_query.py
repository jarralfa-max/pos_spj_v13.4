"""Qué capacidades están encendidas para una sucursal, al iniciar sesión.

Devuelve `{codigo: bool}` para todos los flags activos del catálogo, que es lo
que `FeatureContext.from_flags_dict()` espera. La decisión por flag NO se toma
aquí: se delega en `resolve_flag_value()`
(`backend/domain/feature_flags/policies/feature_flag_evaluation_policy.py`),
que es la única que sabe de precedencia por alcance (USUARIO > SUCURSAL >
GLOBAL) y de despliegue por porcentaje.

Se consulta sobre el modelo canónico `ff_flags`/`ff_rules` (SET-21), no sobre
la tabla `feature_flags` del esquema base. Son dos modelos distintos: el viejo
sólo guardaba un booleano por clave y sus únicos consumidores
(`modulos/config_modules.py`, `modulos/delivery.py`) ya no existen. La
migración 221 documenta que el nombre `ff_` se eligió precisamente para no
chocar con esa tabla mientras ambas convivían.

`user_id` se pasa aunque el contexto sea de sucursal porque las reglas de
alcance USUARIO son más específicas que las de SUCURSAL: omitirlo haría que un
flag dirigido a una persona concreta se resolviera como si no existiera.
"""

from __future__ import annotations

from backend.domain.feature_flags.policies.feature_flag_evaluation_policy import (
    resolve_flag_value,
)


class BranchFeatureFlagsQuery:
    def __init__(self, flag_repository, rule_repository) -> None:
        self._flags = flag_repository
        self._rules = rule_repository

    def flags_for(self, branch_id: str, *, user_id: str = "") -> dict[str, bool]:
        """`{codigo_flag: encendido}` para los flags activos del catálogo.

        Un flag inactivo no aparece: `FeatureContext` sólo guarda los
        encendidos, y un flag retirado del catálogo no debe seguir apareciendo
        como apagado y ocupando sitio en el contexto.
        """
        resolved: dict[str, bool] = {}
        for flag in self._flags.list_active():
            rules = self._rules.list_for_flag(flag.id)
            resolved[flag.code] = resolve_flag_value(
                flag, rules,
                branch_id=branch_id or None,
                user_id=user_id or None,
                # La clave de despliegue por porcentaje es la sucursal: así el
                # mismo local cae siempre del mismo lado del rollout en vez de
                # encender y apagar entre sesiones.
                evaluation_key=branch_id or "",
            )
        return resolved
