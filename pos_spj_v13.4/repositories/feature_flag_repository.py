
# repositories/feature_flag_repository.py
import logging

logger = logging.getLogger(__name__)

class FeatureFlagRepository:
    """
    Capa de acceso a datos para Feature Toggles por Sucursal.
    Define qué módulos del ERP están encendidos o apagados.
    """
    def __init__(self, db_conn):
        self.db = db_conn

    def get_flags_by_branch(self, branch_id: int) -> dict:
        """
        Devuelve un diccionario con los flags de una sucursal.
        Ejemplo: {'delivery': True, 'loyalty': False}
        Compatible con dos schemas:
          - Nuevo: (feature_name, enabled, branch_id)
          - Legacy: (clave, activo)  — sin branch_id diferenciado
        """
        # Detectar schema real de la tabla
        try:
            cols = {r[1] for r in self.db.execute("PRAGMA table_info(feature_flags)").fetchall()}
        except Exception:
            cols = set()

        has_new_schema = "feature_name" in cols and "enabled" in cols
        has_branch_col = "branch_id" in cols or "sucursal_id" in cols
        branch_col     = "branch_id" if "branch_id" in cols else "sucursal_id"

        try:
            if has_new_schema and has_branch_col:
                rows = self.db.execute(
                    f"SELECT feature_name, enabled FROM feature_flags "
                    f"WHERE {branch_col} IN (?, 0) ORDER BY {branch_col} DESC",
                    (branch_id,)
                ).fetchall()
                result = {}
                for r in rows:
                    if r['feature_name'] not in result:  # branch_id específico tiene prioridad
                        result[r['feature_name']] = bool(r['enabled'])
                return result
            elif "clave" in cols:
                # Schema legacy: flags globales (sin branch_id)
                rows = self.db.execute(
                    "SELECT clave, COALESCE(activo, 0) as activo FROM feature_flags"
                ).fetchall()
                return {r['clave']: bool(r['activo']) for r in rows}
            else:
                return {}
        except Exception as e:
            logger.error(f"Error al leer feature flags para sucursal {branch_id}: {e}")
            return {}

    def set_flag(self, feature_name: str, branch_id: int, enabled: bool) -> None:
        """Activa o desactiva un flag para una sucursal específica."""
        try:
            cols = {r[1] for r in self.db.execute("PRAGMA table_info(feature_flags)").fetchall()}
            has_branch = "branch_id" in cols or "sucursal_id" in cols
            branch_col = "branch_id" if "branch_id" in cols else "sucursal_id"

            if "feature_name" in cols and has_branch:
                self.db.execute(
                    f"INSERT INTO feature_flags(feature_name, enabled, {branch_col}) "
                    f"VALUES(?,?,?) ON CONFLICT(feature_name, {branch_col}) "
                    f"DO UPDATE SET enabled=excluded.enabled",
                    (feature_name, int(enabled), branch_id)
                )
            else:
                self.db.execute(
                    "INSERT OR REPLACE INTO feature_flags(clave, activo) VALUES(?,?)",
                    (feature_name, int(enabled))
                )
            self.db.commit()
        except Exception as e:
            logger.error(f"set_flag {feature_name}: {e}")