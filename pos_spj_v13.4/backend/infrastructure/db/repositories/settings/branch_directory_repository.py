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


#: Asignaciones usuario↔sucursal. Nace en la migración 047, así que una
#: instalación anterior puede no tenerla: SIEMPRE se comprueba antes de leerla.
_ASSIGNMENTS_TABLE = "usuarios_sucursales"


class SqliteBranchDirectoryRepository(SettingsRepositoryBase):
    def _table_exists(self, name: str) -> bool:
        """`SettingsRepositoryBase` no trae esta ayuda (sí la trae
        `SecurityRepositoryBase`). Acepta `view` además de `table` a propósito:
        filtrar sólo por `table` haría invisible una vista con ese nombre y el
        alcance se perdería en silencio — que en este archivo significaría
        enseñar sucursales de más o de menos."""
        return self._query_one(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
            (name,)) is not None

    def _has_column(self, table: str, column: str) -> bool:
        return any(row["name"] == column
                   for row in self._query(f"PRAGMA table_info({table})"))

    def supports_branch_code(self) -> bool:
        """Si esta instalación registra códigos de sucursal.

        Público a propósito: la capa de aplicación necesita saberlo para
        EXPLICAR una búsqueda vacía, y hacerlo leyendo un privado del
        repositorio era una filtración de capa. El esquema base de `sucursales`
        (id, nombre, direccion, telefono, rfc_empresa, activa, fecha_alta) no
        tiene `codigo`; esto deja de ser cierto si una migración la añade.
        """
        return self._has_column("sucursales", "codigo")

    def assigned_branch_ids(self, user_id: str) -> tuple[str, ...]:
        """Sucursales ASIGNADAS al usuario. Vacío si la tabla no existe."""
        user_id = str(user_id or "").strip()
        if not user_id or not self._table_exists(_ASSIGNMENTS_TABLE):
            return ()
        rows = self._query(
            f"SELECT sucursal_id FROM {_ASSIGNMENTS_TABLE} WHERE usuario_id = ?",
            (user_id,))
        return tuple(
            str(row["sucursal_id"]).strip() for row in rows
            if str(row["sucursal_id"] or "").strip())

    def own_branch_id(self, user_id: str) -> str:
        """Sucursal propia (`usuarios.sucursal_id`) — el RESPALDO.

        Hoy es el único camino vivo: `usuarios_sucursales` existe pero está
        vacía en la instalación real, mientras que los 4 usuarios sí tienen
        `sucursal_id`. Por eso la asignación no puede ser la única fuente.
        """
        user_id = str(user_id or "").strip()
        if not user_id or not self._table_exists("usuarios"):
            # Se degrada en vez de reventar: hay bases mínimas y fixtures por
            # todo el proyecto que montan sólo las tablas que su caso necesita.
            # Un `OperationalError` aquí tumbaría al llamador; devolver "" lo
            # deja resolver alcance vacío, que es fallar cerrado.
            return ""
        row = self._query_one(
            "SELECT sucursal_id FROM usuarios WHERE id = ?", (user_id,))
        return "" if row is None else str(row["sucursal_id"] or "").strip()

    def search(self, *, branch_ids, text=None, code=None, active_only=True,
               limit=50, offset=0) -> list[dict]:
        """Sucursales del conjunto permitido que casan con el texto.

        `branch_ids=None` significa SIN restricción (alcance global, ya
        autorizado por quien llama). Una tupla VACÍA devuelve `[]` y no "todas":
        un usuario sin alcance no puede descubrir sucursales buscándolas.
        """
        if branch_ids is not None and not branch_ids:
            return []

        where, params = ["1=1"], []
        if active_only:
            where.append("COALESCE(activa, 1) = 1")
        if branch_ids is not None:
            marcas = ",".join("?" * len(branch_ids))
            where.append(f"id IN ({marcas})")
            params.extend(str(b) for b in branch_ids)
        if text and str(text).strip():
            where.append("LOWER(nombre) LIKE ?")
            params.append(f"%{str(text).strip().lower()}%")
        if code and str(code).strip():
            # `sucursales` NO tiene columna `codigo` en el esquema base. Se
            # degrada en vez de reventar, y filtrando a CERO en vez de ignorar
            # el criterio: ignorarlo devolvería resultados que el llamador no
            # pidió, que en una búsqueda con alcance es una fuga.
            if self._has_column("sucursales", "codigo"):
                where.append("LOWER(codigo) = ?")
                params.append(str(code).strip().lower())
            else:
                where.append("1=0")

        params.extend([int(limit), int(offset)])
        return self._query(
            "SELECT id, nombre, COALESCE(activa, 1) AS activa FROM sucursales "
            f"WHERE {' AND '.join(where)} ORDER BY nombre LIMIT ? OFFSET ?",
            tuple(params))

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
