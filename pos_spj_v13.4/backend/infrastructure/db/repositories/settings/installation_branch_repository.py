"""Sucursal anclada a ESTA instalación.

Una instalación del punto de venta atiende a UNA sucursal. Esa elección se
guarda en `configuraciones` bajo una única clave y es la que fija la sucursal
activa de la sesión al iniciar sesión.

Se guarda el id de la sucursal, no su nombre: un local puede renombrarse y el
ancla tiene que seguir apuntando al mismo sitio.

No confundir con `SqliteInstallationRepository` (`backend/security/
provisioning/`), que administra el ciclo de vida del aprovisionamiento —en qué
estado está la instalación—, ni con `SqliteBranchProfileRepository`, que guarda
la ficha de configuración de una sucursal. Esto responde sólo a "¿qué sucursal
es ésta?".
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.settings.base import SettingsRepositoryBase
from backend.shared.ids import validate_uuidv7

#: Clave en `configuraciones`. Se mantiene el nombre histórico a propósito: las
#: instalaciones existentes ya tienen su fila guardada bajo esta clave, y
#: renombrarla las dejaría sin sucursal anclada — arrancarían pidiendo
#: configuración inicial como si fueran nuevas.
INSTALLATION_BRANCH_KEY = "sucursal_instalacion_id"


class SqliteInstallationBranchRepository(SettingsRepositoryBase):
    def get(self) -> tuple[str, str] | None:
        """`(id, nombre)` de la sucursal anclada, o `None` si no hay ninguna.

        El JOIN contra `sucursales` es deliberado: si la clave apunta a una
        sucursal que ya no existe, esto devuelve `None` —"no hay ancla"— en vez
        de un id huérfano que el resto del arranque trataría como válido.
        """
        row = self._query_one(
            """
            SELECT s.id, s.nombre
            FROM sucursales s
            JOIN configuraciones c ON c.clave = ? AND c.valor = s.id
            LIMIT 1
            """,
            (INSTALLATION_BRANCH_KEY,),
        )
        return (str(row["id"]), str(row["nombre"])) if row else None

    def set(self, branch_id: str) -> tuple[str, str]:
        """Ancla la instalación a una sucursal existente y ACTIVA.

        Exigir que esté activa no es un capricho: anclar a una sucursal dada de
        baja dejaría la instalación sin poder abrir sesión, y el mensaje de
        error aparecería en el login, lejos de la pantalla donde se cometió el
        fallo.
        """
        branch_uuid = validate_uuidv7(branch_id)
        row = self._query_one(
            "SELECT id, nombre FROM sucursales WHERE id = ? AND COALESCE(activa, 1) = 1",
            (branch_uuid,),
        )
        if row is None:
            raise ValueError("La sucursal debe existir y estar activa.")

        self._execute(
            "INSERT INTO configuraciones (clave, valor) VALUES (?, ?)"
            " ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            (INSTALLATION_BRANCH_KEY, str(row["id"])),
        )
        return str(row["id"]), str(row["nombre"])
