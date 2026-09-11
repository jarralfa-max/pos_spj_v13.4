"""Consultas de sólo lectura para los interruptores de módulo.

DOS MODELOS DE BANDERAS, Y ESTE LEE EL VIEJO. El modelo canónico es
`ff_flags`/`ff_rules` (SET-21), con alcance por usuario/sucursal y despliegue por
porcentaje, y se consulta con `BranchFeatureFlagsQuery` — es lo que usa el
arranque de la aplicación.

La tabla `feature_flags` de este servicio existe además en DOS formas según la
antigüedad de la instalación, y hay que distinguirlas en tiempo de ejecución:

    clave / activo                      global, sin sucursal (esquema base)
    feature_name / enabled / branch_id  por sucursal, con fila '0' de omisión

No es una precaución teórica: ambas están fijadas por pruebas, así que ambas
existen en instalaciones reales. Dar por muerta la segunda —como hice al
reescribir esto la primera vez— deja sin banderas a las instalaciones que la
tienen, y sin ningún error: `get_branch_feature_flags` devuelve un diccionario
vacío y los módulos aparecen todos apagados.

Este servicio no se repunta a ese modelo a propósito: su contrato ES leer la
tabla vieja, donde una instalación en marcha tiene banderas reales puestas. El
día que esas filas se migren a `ff_flags`, este archivo sobra entero.

Su consumidor era `modulos/config_modules.py`, que ya no existe; hoy no lo llama
nadie en `backend/` ni en `frontend/`. Se conserva porque la tabla que lee sigue
teniendo datos, no porque esté en uso.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.infrastructure.db.repositories.settings.user_directory_repository import (
    SqliteUserDirectoryRepository,
)

logger = logging.getLogger("spj.module_settings.query")


class ModuleSettingsQueryService:
    """Selectores de sucursal y banderas de módulo, sin SQL en la interfaz."""

    def __init__(self, db_conn: Any) -> None:
        self._db = db_conn

    def list_active_branch_options(self) -> list[tuple[str, str]]:
        """`(id, nombre)` de las sucursales activas, ordenadas por nombre.

        Delega en el directorio canónico en lugar de repetir la consulta: ése
        además descarta las identidades corruptas (`'None'`, `'null'`), que esta
        versión dejaba pasar al desplegable como si fueran sucursales reales.
        """
        try:
            return SqliteUserDirectoryRepository(self._db).active_branches_for_selector()
        except Exception:
            logger.exception("No se pudieron cargar las sucursales activas")
            return []

    def get_branch_feature_flags(self, branch_id: Any) -> dict[str, bool]:
        """`{nombre: encendida}` para una sucursal, sea cual sea la forma de la tabla.

        Se decide mirando las columnas reales, no adivinando por la versión de
        la instalación. Un `branch_id` vacío devuelve vacío: "no hay sucursal
        seleccionada" no es lo mismo que "esta sucursal no tiene banderas", y
        en la forma global el parámetro se valida aunque no filtre.
        """
        normalized = self._normalize_branch_id(branch_id)
        if normalized is None:
            return {}
        try:
            columnas = {
                row[1] for row in self._db.execute("PRAGMA table_info(feature_flags)")}
            if {"feature_name", "enabled"} <= columnas:
                return self._flags_by_branch(normalized, columnas)
            if "clave" in columnas:
                return self._global_flags()
            return {}
        except Exception:
            logger.exception("No se pudieron cargar las banderas de sucursal=%s", branch_id)
            return {}

    def _flags_by_branch(self, branch_id: str, columnas: set[str]) -> dict[str, bool]:
        """Forma por sucursal. La fila de la sucursal gana sobre la global.

        El `ORDER BY ... DESC` con el primer valor que entra al diccionario es
        lo que implementa esa precedencia: la fila específica llega antes que la
        `'0'` de omisión y la posterior no la pisa.
        """
        columna = "branch_id" if "branch_id" in columnas else "sucursal_id"
        rows = self._db.execute(
            f"SELECT feature_name, enabled FROM feature_flags"
            f" WHERE {columna} IN (?, '0') ORDER BY {columna} DESC",
            (branch_id,)).fetchall()
        resuelto: dict[str, bool] = {}
        for nombre, encendida in rows:
            if nombre not in resuelto:
                resuelto[str(nombre)] = bool(encendida)
        return resuelto

    def _global_flags(self) -> dict[str, bool]:
        """Forma global del esquema base: sin sucursal, la bandera vale para todos."""
        rows = self._db.execute(
            "SELECT clave, COALESCE(activo, 0) FROM feature_flags").fetchall()
        return {str(clave): bool(activo) for clave, activo in rows}

    @staticmethod
    def _normalize_branch_id(branch_id: Any) -> str | None:
        """La identidad de sucursal es UUIDv7 TEXT: se propaga tal cual, nunca
        se convierte a entero (REGLA CERO)."""
        if branch_id in (None, ""):
            return None
        return str(branch_id).strip()
