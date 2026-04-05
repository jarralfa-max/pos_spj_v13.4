
# repositories/finance_repository.py
import logging

logger = logging.getLogger(__name__)

class FinanceRepository:
    """
    Repositorio para gestionar los Turnos de Caja, Movimientos y Cortes Z.
    """
    def __init__(self, db_conn):
        self.db = db_conn

    def get_current_shift(self, branch_id: int, user: str) -> dict:
        """Obtiene el turno de caja abierto actualmente para un usuario en una sucursal."""
        cursor = self.db.cursor()
        query = """
            SELECT * FROM caja_turnos 
            WHERE sucursal_id = ? AND usuario = ? AND estado = 'abierto'
            ORDER BY id DESC LIMIT 1
        """
        row = cursor.execute(query, (branch_id, user)).fetchone()
        return dict(row) if row else None

    def open_shift(self, branch_id: int, user: str, initial_cash: float) -> int:
        """Abre un nuevo turno de caja."""
        cursor = self.db.cursor()
        cursor.execute("""
            INSERT INTO caja_turnos (sucursal_id, usuario, fondo_inicial, fecha_apertura, estado)
            VALUES (?, ?, ?, datetime('now'), 'abierto')
        """, (branch_id, user, initial_cash))
        return cursor.lastrowid

    def register_movement(self, turno_id: int, branch_id: int, user: str, 
                          amount: float, type_mov: str, category: str, 
                          payment_method: str, description: str, ref_id: str):
        """Registra un movimiento de entrada o salida (Ej. Ventas, Gastos)."""
        cursor = self.db.cursor()
        cursor.execute("""
            INSERT INTO caja_movimientos (turno_id, sucursal_id, usuario, tipo, categoria, 
                                          monto, metodo_pago, descripcion, referencia_id, fecha)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (turno_id, branch_id, user, type_mov, category, amount, payment_method, description, str(ref_id)))

    def get_shift_totals(self, turno_id: int) -> dict:
        """Suma todas las entradas y salidas de un turno específico."""
        cursor = self.db.cursor()
        query = """
            SELECT 
                SUM(CASE WHEN tipo = 'ENTRADA' THEN monto ELSE 0 END) as total_entradas,
                SUM(CASE WHEN tipo = 'SALIDA' THEN monto ELSE 0 END) as total_salidas
            FROM caja_movimientos
            WHERE turno_id = ? AND forma_pago = 'Efectivo'
        """
        row = cursor.execute(query, (turno_id,)).fetchone()
        return {
            "entradas_efectivo": row['total_entradas'] or 0.0,
            "salidas_efectivo": row['total_salidas'] or 0.0
        }

    def close_shift(self, turno_id: int, expected_cash: float, actual_cash: float, difference: float):
        """Cierra el turno de caja y guarda los totales."""
        cursor = self.db.cursor()
        cursor.execute("""
            UPDATE caja_turnos 
            SET fecha_cierre = datetime('now'), estado = 'cerrado',
                efectivo_esperado = ?, efectivo_contado = ?, diferencia = ?
            WHERE id = ?
        """, (expected_cash, actual_cash, difference, turno_id))