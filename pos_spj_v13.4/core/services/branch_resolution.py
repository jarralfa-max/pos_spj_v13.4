# core/services/branch_resolution.py — SPJ POS v13.4
"""
Resolución canónica de la sucursal de instalación de la terminal.

Fuente de verdad: `configuraciones.sucursal_instalacion_id`.

Contrato de 3 estados (sin fallback silencioso a 'Principal'):
  1. Clave presente y VÁLIDA (UUID de sucursal activa)
       → {'id': uuid, 'nombre': ..., 'configured': True,  'pending': False}
  2. Clave presente pero INVÁLIDA ("None"/""/"null" o sucursal
     inexistente/inactiva)
       → {'id': None, 'nombre': '',  'configured': False, 'pending': False,
          'error': ...}   (warning fuerte; NUNCA se cae a otra sucursal)
  3. Clave AUSENTE (bootstrap inicial)
       → primera sucursal activa con UUID válido, marcada como instalación
         PENDIENTE de configurar:
         {'id': uuid, 'nombre': ..., 'configured': False, 'pending': True}

Única ruta compartida por el diálogo de login y el contenedor de la app.
"""
import logging

logger = logging.getLogger(__name__)

INSTALLATION_BRANCH_KEY = "sucursal_instalacion_id"

# Filtro canónico de identidad válida para sucursales.
VALID_BRANCH_ID_SQL = (
    "id IS NOT NULL AND TRIM(id) != '' "
    "AND LOWER(TRIM(id)) NOT IN ('none','null')"
)


def is_invalid_identity(value) -> bool:
    """True si el valor no puede ser una identidad UUID válida."""
    return value is None or str(value).strip().lower() in ("", "none", "null")


def resolve_installation_branch(conn) -> dict:
    """Resuelve la sucursal de ESTA terminal desde `configuraciones`.

    Nunca lanza: ante error devuelve el estado inválido (configured=False).
    """
    invalido = {
        'id': None, 'nombre': '', 'configured': False, 'pending': False,
        'error': 'Sucursal de instalación no configurada o inválida',
    }
    try:
        row = conn.execute(
            "SELECT valor FROM configuraciones WHERE clave=?",
            (INSTALLATION_BRANCH_KEY,),
        ).fetchone()

        if row is not None:
            stored = str(row[0]).strip() if row[0] is not None else ""
            if is_invalid_identity(stored):
                logger.warning(
                    "CONFIGURACIÓN INVÁLIDA: %s=%r. NO se aplicará fallback. "
                    "Corrige la sucursal de la terminal en Configuración → "
                    "Empresa (o ejecuta tools/fix_invalid_branch_identity.py).",
                    INSTALLATION_BRANCH_KEY, stored,
                )
                return dict(invalido)
            suc_row = conn.execute(
                f"SELECT id, nombre FROM sucursales WHERE {VALID_BRANCH_ID_SQL} "
                "AND id=? AND COALESCE(activa,1)=1",
                (stored,),
            ).fetchone()
            if suc_row:
                return {'id': str(suc_row[0]), 'nombre': str(suc_row[1] or ''),
                        'configured': True, 'pending': False, 'error': ''}
            logger.warning(
                "CONFIGURACIÓN INVÁLIDA: %s=%r apunta a una sucursal "
                "inexistente o inactiva. NO se aplicará fallback.",
                INSTALLATION_BRANCH_KEY, stored,
            )
            return dict(invalido)

        # Clave AUSENTE: bootstrap inicial — primera sucursal activa VÁLIDA,
        # registrada como instalación pendiente de configurar.
        first = conn.execute(
            f"SELECT id, nombre FROM sucursales WHERE {VALID_BRANCH_ID_SQL} "
            "AND COALESCE(activa,1)=1 ORDER BY fecha_alta LIMIT 1"
        ).fetchone()
        if first:
            logger.warning(
                "Instalación PENDIENTE de configurar: no existe la clave "
                "'%s'; usando primera sucursal activa '%s' de forma "
                "provisional. Configura la terminal en Configuración → Empresa.",
                INSTALLATION_BRANCH_KEY, first[1],
            )
            return {'id': str(first[0]), 'nombre': str(first[1] or ''),
                    'configured': False, 'pending': True, 'error': ''}
        return dict(invalido)
    except Exception as exc:
        logger.error("resolve_installation_branch: %s", exc)
        return dict(invalido)
