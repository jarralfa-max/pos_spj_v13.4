from __future__ import annotations

from typing import Any, Dict, List, Optional


class CustomerLookupService:
    """Read-only customer finder for POS."""

    def __init__(self, db_conn):
        self.db = db_conn

    def buscar_cliente(self, termino: str, limit: int = 12) -> List[Dict[str, Any]]:
        term = (termino or "").strip()
        if not term:
            return []
        like = f"%{term}%"
        rows = self.db.execute(
            "SELECT id, nombre, COALESCE(telefono,'') telefono, COALESCE(email,'') email, "
            "COALESCE(direccion,'') direccion, COALESCE(rfc,'') rfc, COALESCE(puntos,0) puntos, "
            "COALESCE(codigo_qr,'') codigo_qr, COALESCE(saldo,0) saldo "
            "FROM clientes WHERE COALESCE(activo,1)=1 AND "
            "(nombre LIKE ? OR telefono LIKE ? OR codigo_qr LIKE ?) "
            "ORDER BY nombre LIMIT ?",
            (like, like, like, int(limit)),
        ).fetchall()
        out = []
        for r in rows:
            get = (lambda k, i: r[k] if hasattr(r, 'keys') else r[i])
            out.append({
                'id': get('id', 0), 'nombre': get('nombre', 1), 'telefono': get('telefono', 2),
                'email': get('email', 3), 'direccion': get('direccion', 4), 'rfc': get('rfc', 5),
                'puntos': int(get('puntos', 6) or 0), 'codigo_qr': get('codigo_qr', 7),
                'saldo': float(get('saldo', 8) or 0),
            })
        return out

    def get_credit_balance(self, cliente_id: int) -> float:
        row = self.db.execute("SELECT COALESCE(saldo,0) FROM clientes WHERE id=?", (cliente_id,)).fetchone()
        if not row:
            return 0.0
        return float(row[0] if not hasattr(row, 'keys') else list(row)[0] or 0.0)

    def get_loyalty_status(self, cliente_id: int) -> Dict[str, Any]:
        row = self.db.execute(
            "SELECT COALESCE(puntos,0), COALESCE(nivel_fidelidad,'') FROM clientes WHERE id=?", (cliente_id,)
        ).fetchone()
        if not row:
            return {'puntos': 0, 'nivel': ''}
        if hasattr(row, 'keys'):
            vals = list(row)
            return {'puntos': int(vals[0] or 0), 'nivel': vals[1] or ''}
        return {'puntos': int(row[0] or 0), 'nivel': row[1] or ''}

    def get_by_loyalty_card(self, card_code: str) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            "SELECT c.id, c.nombre FROM clientes c "
            "JOIN tarjetas_fidelidad t ON t.id_cliente = c.id "
            "WHERE t.codigo = ? AND t.activa = 1 LIMIT 1",
            (card_code,),
        ).fetchone()
        if not row:
            return None
        return {
            'id': row['id'] if hasattr(row, 'keys') else row[0],
            'nombre': row['nombre'] if hasattr(row, 'keys') else row[1],
        }
