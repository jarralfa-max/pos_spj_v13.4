
# repositories/settings_repository.py
import logging

logger = logging.getLogger(__name__)

class SettingsRepository:
    """
    Capa de acceso a datos para la Configuración Central.
    Maneja configuraciones de UI, Hardware y Feature Toggles.
    """
    def __init__(self, db_conn):
        self.db = db_conn

    def get_all_settings(self) -> dict:
        """
        Extrae todas las configuraciones de la base de datos.
        """
        query = "SELECT clave, valor, tipo_dato FROM system_settings"
        try:
            rows = self.db.execute(query).fetchall()
            settings = {}
            for row in rows:
                clave = row['clave']
                valor_crudo = row['valor']
                tipo = row['tipo_dato'] # 'bool', 'int', 'float', 'str'
                
                # Casteo automático según el tipo de dato
                if tipo == 'bool':
                    settings[clave] = str(valor_crudo).lower() in ('true', '1', 'yes')
                elif tipo == 'int':
                    settings[clave] = int(valor_crudo)
                elif tipo == 'float':
                    settings[clave] = float(valor_crudo)
                else:
                    settings[clave] = str(valor_crudo)
                    
            return settings
        except Exception as e:
            logger.error(f"Error cargando configuraciones: {str(e)}")
            return {}

    def update_setting(self, clave: str, valor: str):
        """
        Guarda un valor de configuración con UPSERT en ambas tablas.
        No emite commit — el caller es dueño de la transacción.
        """
        v = str(valor)
        # Primary store: configuraciones table
        try:
            self.db.execute("""
                INSERT INTO configuraciones (clave, valor)
                VALUES (?, ?)
                ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor
            """, (clave, v))
        except Exception as _e1:
            import logging; logging.getLogger(__name__).debug("upsert configuraciones: %s", _e1)
        # Legacy store: system_settings
        try:
            affected = self.db.execute(
                "UPDATE system_settings SET valor=? WHERE clave=?", (v, clave)
            ).rowcount
            if affected == 0:
                self.db.execute(
                    "INSERT OR IGNORE INTO system_settings (clave, valor, tipo_dato) VALUES (?,?,?)",
                    (clave, v, 'str'))
        except Exception as _e2:
            import logging; logging.getLogger(__name__).debug("update system_settings: %s", _e2)