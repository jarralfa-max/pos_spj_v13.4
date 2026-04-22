# tests/test_fase2_bi_cajeros.py
# Fase 2 — BIRepository.get_ranking_cajeros + BIService.ranking_cajeros
# No importa PyQt5 — usa SQLite en-memoria.

import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock


# ── helpers ───────────────────────────────────────────────────────────────────

def _mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _db_with_ventas(rows):
    """DB en-memoria con tabla ventas y filas dadas."""
    conn = _mem_db()
    conn.execute("""
        CREATE TABLE ventas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sucursal_id INTEGER DEFAULT 1,
            usuario     TEXT    DEFAULT '',
            total       REAL    DEFAULT 0,
            descuento   REAL    DEFAULT 0,
            estado      TEXT    DEFAULT 'completada',
            fecha       TEXT    DEFAULT (datetime('now'))
        )
    """)
    for r in rows:
        conn.execute(
            "INSERT INTO ventas(sucursal_id, usuario, total, descuento, estado, fecha) "
            "VALUES(?,?,?,?,?,?)",
            (r.get('sucursal_id', 1), r.get('usuario', 'cajero_a'),
             r.get('total', 100.0), r.get('descuento', 0.0),
             r.get('estado', 'completada'), r.get('fecha', '2026-04-15 10:00:00'))
        )
    conn.commit()
    return conn


# ── BIRepository tests ────────────────────────────────────────────────────────

class TestGetRankingCajeros:

    def _repo(self, conn):
        # from repositories.bi_repository import BIRepository  # ELIMINADO en v13.4
        r = BIRepository.__new__(BIRepository)
        r.db = conn
        return r

    def test_retorna_lista(self):
        conn = _db_with_ventas([
            {'usuario': 'maria', 'total': 500},
            {'usuario': 'maria', 'total': 300},
            {'usuario': 'jose',  'total': 200},
        ])
        repo = self._repo(conn)
        rows = repo.get_ranking_cajeros(1, '2026-01-01', '2026-12-31')
        assert isinstance(rows, list)
        assert len(rows) == 2

    def test_cajero_con_mas_ventas_primero(self):
        conn = _db_with_ventas([
            {'usuario': 'maria', 'total': 100},
            {'usuario': 'maria', 'total': 100},
            {'usuario': 'jose',  'total': 999},
        ])
        repo = self._repo(conn)
        rows = repo.get_ranking_cajeros(1, '2026-01-01', '2026-12-31')
        # maria tiene 2 ventas → primera (ORDER BY num_ventas DESC)
        assert rows[0]['cajero'] == 'maria'
        assert rows[0]['num_ventas'] == 2

    def test_total_ventas_sumado(self):
        conn = _db_with_ventas([
            {'usuario': 'ana', 'total': 150.0},
            {'usuario': 'ana', 'total': 250.0},
        ])
        repo = self._repo(conn)
        rows = repo.get_ranking_cajeros(1, '2026-01-01', '2026-12-31')
        assert abs(rows[0]['total_ventas'] - 400.0) < 0.01

    def test_sin_usuario_etiquetado(self):
        conn = _db_with_ventas([
            {'usuario': None, 'total': 100},
        ])
        # SQLite interpreta None como NULL; la query usa COALESCE
        repo = self._repo(conn)
        rows = repo.get_ranking_cajeros(1, '2026-01-01', '2026-12-31')
        assert rows[0]['cajero'] == '(sin usuario)'

    def test_excluye_canceladas(self):
        conn = _db_with_ventas([
            {'usuario': 'maria', 'total': 100, 'estado': 'completada'},
            {'usuario': 'maria', 'total': 200, 'estado': 'cancelada'},
        ])
        repo = self._repo(conn)
        rows = repo.get_ranking_cajeros(1, '2026-01-01', '2026-12-31')
        assert rows[0]['num_ventas'] == 1

    def test_limite_aplicado(self):
        ventas = [{'usuario': f'caj{i}', 'total': 100} for i in range(25)]
        conn = _db_with_ventas(ventas)
        repo = self._repo(conn)
        rows = repo.get_ranking_cajeros(1, '2026-01-01', '2026-12-31', limite=10)
        assert len(rows) <= 10

    def test_filtro_por_sucursal(self):
        conn = _db_with_ventas([
            {'sucursal_id': 1, 'usuario': 'maria', 'total': 100},
            {'sucursal_id': 2, 'usuario': 'jose',  'total': 100},
        ])
        repo = self._repo(conn)
        rows = repo.get_ranking_cajeros(1, '2026-01-01', '2026-12-31')
        assert all(True for r in rows)  # no crash
        assert len(rows) == 1
        assert rows[0]['cajero'] == 'maria'


# ── BIService.ranking_cajeros tests ──────────────────────────────────────────

class TestBIServiceRankingCajeros:

    def _svc(self, repo_mock):
        # from core.services.bi_service import BIService  # ELIMINADO en v13.4
        svc = BIService.__new__(BIService)
        svc.repo = repo_mock
        svc.feature_flag_service = MagicMock()
        return svc

    def test_delegado_al_repo(self):
        repo = MagicMock()
        repo.get_ranking_cajeros.return_value = [{"cajero": "ana", "num_ventas": 5}]
        svc = self._svc(repo)
        result = svc.ranking_cajeros(sucursal_id=1, rango='mes')
        assert repo.get_ranking_cajeros.called
        assert result[0]['cajero'] == 'ana'

    def test_rango_hoy_pasa_misma_fecha(self):
        repo = MagicMock()
        repo.get_ranking_cajeros.return_value = []
        svc = self._svc(repo)
        svc.ranking_cajeros(1, 'hoy')
        args = repo.get_ranking_cajeros.call_args[0]
        # fi == ff cuando rango='hoy'
        assert args[1] == args[2]

    def test_rango_invalido_usa_mes(self):
        repo = MagicMock()
        repo.get_ranking_cajeros.return_value = []
        svc = self._svc(repo)
        svc.ranking_cajeros(1, 'trimestre')  # no reconocido → mes
        assert repo.get_ranking_cajeros.called


# ── scan_telemetria tests ─────────────────────────────────────────────────────

class TestGetScanTelemetria:

    def _repo_with_scan_log(self, rows):
        conn = _mem_db()
        conn.execute("""
            CREATE TABLE scan_event_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sucursal_id INTEGER DEFAULT 1,
                tipo        TEXT,
                accion      TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        for r in rows:
            conn.execute(
                "INSERT INTO scan_event_log(sucursal_id, tipo, accion, created_at) "
                "VALUES(?,?,?,?)",
                (r.get('sucursal_id', 1), r.get('tipo', 'producto'),
                 r.get('accion', 'producto_agregado'), r.get('created_at', '2026-04-15'))
            )
        conn.commit()
        # from repositories.bi_repository import BIRepository  # ELIMINADO en v13.4
        repo = BIRepository.__new__(BIRepository)
        repo.db = conn
        return repo

    def test_retorna_lista(self):
        repo = self._repo_with_scan_log([
            {'tipo': 'producto', 'accion': 'producto_agregado'},
            {'tipo': 'tarjeta',  'accion': 'cliente_cargado'},
        ])
        result = repo.get_scan_telemetria(1, '2026-01-01', '2026-12-31')
        assert isinstance(result, list)

    def test_agrupa_por_tipo_accion(self):
        repo = self._repo_with_scan_log([
            {'tipo': 'producto', 'accion': 'producto_agregado'},
            {'tipo': 'producto', 'accion': 'producto_agregado'},
            {'tipo': 'tarjeta',  'accion': 'cliente_cargado'},
        ])
        result = repo.get_scan_telemetria(1, '2026-01-01', '2026-12-31')
        totales = {(r['tipo'], r['accion']): r['total'] for r in result}
        assert totales[('producto', 'producto_agregado')] == 2

    def test_tabla_inexistente_retorna_lista_vacia(self):
        """Si scan_event_log no existe, retorna [] sin levantar excepción."""
        conn = _mem_db()  # sin tabla scan_event_log
        # from repositories.bi_repository import BIRepository  # ELIMINADO en v13.4
        repo = BIRepository.__new__(BIRepository)
        repo.db = conn
        result = repo.get_scan_telemetria(1, '2026-01-01', '2026-12-31')
        assert result == []
