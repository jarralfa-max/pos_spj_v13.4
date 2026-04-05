
# repositories/config_repository.py
import logging

logger = logging.getLogger(__name__)

class ConfigRepository:
    """Acceso a datos para Sucursales y Configuraciones del Sistema."""
    def __init__(self, db_conn):
        self.db = db_conn

    # --- SUCURSALES ---
    def get_all_branches(self) -> list:
        cursor = self.db.cursor()
        rows = cursor.execute("SELECT * FROM sucursales WHERE activa = 1").fetchall()
        return [dict(row) for row in rows]

    def create_branch(self, nombre: str, direccion: str, telefono: str):
        cursor = self.db.cursor()
        cursor.execute("""
            INSERT INTO sucursales (nombre, direccion, telefono, activa)
            VALUES (?, ?, ?, 1)
        """, (nombre, direccion, telefono))
        return cursor.lastrowid

    def update_branch(self, branch_id: int, nombre: str, direccion: str, telefono: str):
        cursor = self.db.cursor()
        cursor.execute("""
            UPDATE sucursales SET nombre = ?, direccion = ?, telefono = ? WHERE id = ?
        """, (nombre, direccion, telefono, branch_id))

    def disable_branch(self, branch_id: int):
        """Soft Delete para sucursales."""
        cursor = self.db.cursor()
        cursor.execute("UPDATE sucursales SET activa = 0 WHERE id = ?", (branch_id,))

    # --- AJUSTES GLOBALES (Key-Value) ---
    def get_setting(self, key: str, default_value: str = "") -> str:
        cursor = self.db.cursor()
        row = cursor.execute("SELECT valor FROM configuraciones WHERE clave = ?", (key,)).fetchone()
        return row['valor'] if row else default_value

    def save_setting(self, key: str, value: str):
        cursor = self.db.cursor()
        cursor.execute("""
            INSERT INTO configuraciones (clave, valor) VALUES (?, ?)
            ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor
        """, (key, str(value)))
        
    def get_all_settings(self) -> dict:
        """
        Obtiene todas las configuraciones de la base de datos 
        y las devuelve como un diccionario para la RAM.
        """
        try:
            cursor = self.db.cursor()
            rows = cursor.execute("SELECT clave, valor FROM configuraciones").fetchall()
            return {row['clave']: row['valor'] for row in rows}
        except Exception as e:
            # Si la tabla no existe aún (por ejemplo en el primer arranque),
            # no crasheamos, simplemente devolvemos un diccionario vacío.
            logger.warning(f"No se pudieron cargar las configuraciones: {e}")
            return {}