"""Directorio de sucursales — lectura de `sucursales`.

Existe para que `SELECT nombre FROM sucursales WHERE id = ?` esté escrito UNA
vez. Estaba duplicado en `backend/bootstrap/application_context_builder.py` y
en `backend/security/provisioning/installation_summary_query.py`, y en el
primero además vivía dentro del bootstrap, que no es una capa que deba hablar
SQL (§12).

No confundir con `SqliteBranchProfileRepository`, que lee `branch_profiles`:
ésa es la ficha de configuración de una sucursal (horarios, ticket, mapa) y
sólo tiene filas cuando alguien la ha configurado en Configuración. `sucursales`
es el registro base y existe desde el esquema inicial, así que es la única
fuente que responde en una instalación recién creada — que es exactamente
cuando se construye el contexto del primer login.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.settings.base import SettingsRepositoryBase


class SqliteBranchDirectoryRepository(SettingsRepositoryBase):
    def name_for(self, branch_id: str) -> str:
        """Nombre de la sucursal, o cadena vacía si no existe.

        Cadena vacía y no `None`: el nombre de sucursal se muestra en la
        cabecera del shell y en el ticket, y ahí un `None` se imprimiría como
        "None". El llamador que necesite distinguir "sin sucursal" ya tiene el
        `branch_id`.
        """
        if not str(branch_id or "").strip():
            return ""
        row = self._query_one(
            "SELECT nombre FROM sucursales WHERE id = ?", (str(branch_id).strip(),))
        if row is None:
            return ""
        return row["nombre"] or ""
