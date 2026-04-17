# tests/test_fase1_printer_styles.py
# Fase 1 — PrinterService bitácora + spj_styles tooltips/scrollbars
import sys, os, sqlite3, time, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def print_db():
    """BD en memoria con tabla print_job_log."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE print_job_log (
            id          INTEGER  PRIMARY KEY AUTOINCREMENT,
            job_id      TEXT     NOT NULL,
            job_type    TEXT     NOT NULL DEFAULT 'ticket',
            plantilla   TEXT     DEFAULT '',
            impresora   TEXT     DEFAULT '',
            folio       TEXT     DEFAULT '',
            estado      TEXT     NOT NULL DEFAULT 'queued',
            reintentos  INTEGER  DEFAULT 0,
            total       REAL     DEFAULT 0,
            sucursal_id INTEGER  DEFAULT 1,
            usuario     TEXT     DEFAULT '',
            error_msg   TEXT     DEFAULT '',
            created_at  TEXT     NOT NULL DEFAULT (datetime('now')),
            finished_at TEXT
        );
        CREATE TABLE configuraciones_hardware (
            id INTEGER PRIMARY KEY, tipo TEXT, clave TEXT, valor TEXT
        );
        CREATE TABLE configuraciones (
            id INTEGER PRIMARY KEY, clave TEXT UNIQUE, valor TEXT
        );
    """)
    conn.commit()
    return conn


# ── Helpers AST (sin PyQt5) ───────────────────────────────────────────────────

def _leer_spj_styles():
    path = os.path.join(os.path.dirname(__file__), "..", "modulos", "spj_styles.py")
    return open(os.path.abspath(path)).read()


# ── Tests spj_styles (vía AST / búsqueda de texto) ───────────────────────────

def test_apply_spj_tooltips_definida():
    """apply_spj_tooltips está definida en spj_styles.py."""
    src = _leer_spj_styles()
    assert "def apply_spj_tooltips" in src


def test_apply_scrollbars_definida():
    """apply_scrollbars está definida en spj_styles.py."""
    src = _leer_spj_styles()
    assert "def apply_scrollbars" in src


def test_scrollbar_qss_tiene_vertical_y_horizontal():
    """SCROLLBAR_QSS cubre scrollbars vertical y horizontal."""
    src = _leer_spj_styles()
    assert "QScrollBar:vertical" in src
    assert "QScrollBar:horizontal" in src


def test_tooltip_map_no_vacio():
    """_TOOLTIP_MAP tiene al menos 10 entradas."""
    src = _leer_spj_styles()
    assert "_TOOLTIP_MAP" in src
    # Cuenta entradas con patrón "keyword": "tooltip text"
    import re
    entries = re.findall(r'"[^"]+"\s*:\s*"[^"]+"', src)
    assert len(entries) >= 10, f"Solo {len(entries)} entradas en _TOOLTIP_MAP"


def test_spj_styles_tiene_guardar_tooltip():
    """spj_styles.py incluye el tooltip para 'guardar'."""
    src = _leer_spj_styles()
    assert '"guardar"' in src or "'guardar'" in src


def test_tooltip_for_text_definida():
    """_tooltip_for_text está definida en spj_styles.py."""
    src = _leer_spj_styles()
    assert "def _tooltip_for_text" in src


# ── Tests PrintQueue._log_job_to_db ──────────────────────────────────────────

def test_print_queue_log_success(print_db):
    """PrintQueue registra trabajo exitoso en print_job_log."""
    from core.services.printer_service import (
        PrintQueue, PrintJob, PrintJobType, PrintJobStatus
    )
    q = PrintQueue()
    q._db = print_db

    job = PrintJob(
        id="PJ-TEST-01",
        job_type=PrintJobType.TICKET,
        data=b"",
        raw_data={"folio": "V-001", "totales": {"total_final": 99.50},
                  "plantilla": "ticket_venta"},
        destination="192.168.1.50:9100",
        status=PrintJobStatus.SUCCESS,
    )
    q._log_job_to_db(job, reintentos=1)

    row = print_db.execute(
        "SELECT * FROM print_job_log WHERE job_id=?", ("PJ-TEST-01",)
    ).fetchone()
    assert row is not None
    assert row["estado"] == "success"
    assert row["folio"] == "V-001"
    assert row["total"] == pytest.approx(99.50)
    assert row["impresora"] == "192.168.1.50:9100"


def test_print_queue_log_failed(print_db):
    """PrintQueue registra trabajo fallido con mensaje de error."""
    from core.services.printer_service import (
        PrintQueue, PrintJob, PrintJobType, PrintJobStatus
    )
    q = PrintQueue()
    q._db = print_db

    job = PrintJob(
        id="PJ-TEST-02",
        job_type=PrintJobType.TICKET,
        data=b"",
        raw_data={},
        destination="",
        status=PrintJobStatus.FAILED,
        error_msg="Connection refused",
    )
    q._log_job_to_db(job, reintentos=2)

    row = print_db.execute(
        "SELECT * FROM print_job_log WHERE job_id=?", ("PJ-TEST-02",)
    ).fetchone()
    assert row is not None
    assert row["estado"] == "failed"
    assert "refused" in row["error_msg"].lower()


def test_print_queue_log_sin_db_no_crash():
    """PrintQueue._log_job_to_db no falla si no hay DB."""
    from core.services.printer_service import (
        PrintQueue, PrintJob, PrintJobType, PrintJobStatus
    )
    q = PrintQueue()
    q._db = None  # Sin DB

    job = PrintJob(
        id="PJ-TEST-03",
        job_type=PrintJobType.TICKET,
        data=b"",
        status=PrintJobStatus.SUCCESS,
    )
    q._log_job_to_db(job, reintentos=1)  # No debe lanzar excepción


def test_printer_service_tiene_db_en_queue(print_db):
    """PrinterService inyecta la DB al PrintQueue._db."""
    from core.services.printer_service import PrinterService
    svc = PrinterService(db_conn=print_db, module_config=None)
    assert svc.queue._db is print_db
    svc.close()


# ── Tests migraciones ─────────────────────────────────────────────────────────

def test_migracion_056_crea_tabla():
    """Migración 056 crea print_job_log correctamente."""
    import importlib.util, pathlib
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    mig_path = pathlib.Path(__file__).parent.parent / "migrations" / "standalone" / "056_print_job_log.py"
    spec = importlib.util.spec_from_file_location("m056", mig_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.run(conn)
    conn.commit()
    rows = conn.execute("PRAGMA table_info(print_job_log)").fetchall()
    cols = {r[1] for r in rows}
    assert "job_id"    in cols
    assert "job_type"  in cols
    assert "plantilla" in cols
    assert "impresora" in cols
    assert "estado"    in cols
    assert "reintentos" in cols


def test_engine_tiene_056():
    """engine.py incluye la migración 056 en MIGRATIONS."""
    from migrations.engine import MIGRATIONS
    versions = [v for v, _ in MIGRATIONS]
    assert "056" in versions, "056 no está en MIGRATIONS de engine.py"
