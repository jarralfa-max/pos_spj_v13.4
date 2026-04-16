import os
import sys
import sqlite3
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE configuraciones (
            clave TEXT PRIMARY KEY,
            valor TEXT
        );
        """
    )
    conn.commit()
    return conn


def test_theme_engine_alias_dark_light():
    from ui.themes import theme_engine

    with patch.object(theme_engine, "_get_temas", return_value={"Oscuro": "QWidget{a:1;}", "Claro": "QWidget{a:2;}"}):
        assert "a:1" in theme_engine.get_qss("Dark")
        assert "a:2" in theme_engine.get_qss("Light")


def test_load_saved_theme_respeta_tema_persistido():
    from ui.themes import theme_engine

    conn = _make_conn()
    conn.execute("INSERT INTO configuraciones (clave, valor) VALUES ('tema', 'Light')")
    conn.commit()

    with patch("core.db.connection.get_connection", return_value=conn), \
         patch.object(theme_engine, "_get_temas", return_value={"Oscuro": "QWidget{a:1;}", "Claro": "QWidget{a:2;}"}):
        tema = theme_engine.load_saved_theme(None)
        assert tema == "Light"
        assert theme_engine.get_current_theme() == "Light"
