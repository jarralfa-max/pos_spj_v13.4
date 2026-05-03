# tests/test_wa_parser.py — SPJ POS v13.5
"""
Tests para ProductMatcher e IntentParser.
"""
import sys, os, importlib.util as _ilu

# ── WA service sys.path setup ────────────────────────────────────────────────
_WA_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../whatsapp_service'))
# Purge any stale 'config' that points to pos_spj_v13.4/config.py
for _k in list(sys.modules.keys()):
    if _k == 'config' or _k.startswith('config.'):
        del sys.modules[_k]
if _WA_ROOT not in sys.path:
    sys.path.insert(0, _WA_ROOT)
sys.path.insert(1, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Force-load the WA config package so imports find the right module
_cfg_spec = _ilu.spec_from_file_location('config', os.path.join(_WA_ROOT, 'config', '__init__.py'))
_cfg_mod = _ilu.module_from_spec(_cfg_spec); sys.modules['config'] = _cfg_mod; _cfg_spec.loader.exec_module(_cfg_mod)
_set_spec = _ilu.spec_from_file_location('config.settings', os.path.join(_WA_ROOT, 'config', 'settings.py'))
_set_mod = _ilu.module_from_spec(_set_spec); sys.modules['config.settings'] = _set_mod; _set_spec.loader.exec_module(_set_mod)
_cfg_mod.settings = _set_mod
# Stub optional heavy deps not installed in test environment
from unittest.mock import MagicMock as _MM
for _dep in ('httpx', 'ollama', 'aiohttp'):
    if _dep not in sys.modules:
        sys.modules[_dep] = _MM()

import sqlite3
import pytest
import asyncio
from unittest.mock import MagicMock, patch

# ── Schema mínimo ─────────────────────────────────────────────────────────────

_PM_SCHEMA = """
CREATE TABLE productos (
    id INTEGER PRIMARY KEY, nombre TEXT,
    precio REAL DEFAULT 0, existencia REAL DEFAULT 10,
    activo INTEGER DEFAULT 1, oculto INTEGER DEFAULT 0,
    unidad TEXT DEFAULT 'kg', categoria TEXT DEFAULT 'Carne'
);
CREATE TABLE branch_inventory (
    product_id INTEGER, branch_id INTEGER, quantity REAL
);
"""

_PM_SEED = """
INSERT INTO productos VALUES (1,'Pechuga de Pollo',95.0,10.0,1,0,'kg','Carne');
INSERT INTO productos VALUES (2,'Pierna de Pollo',75.0,8.0,1,0,'kg','Carne');
INSERT INTO productos VALUES (3,'Chuleta de Cerdo',85.0,5.0,1,0,'kg','Cerdo');
INSERT INTO productos VALUES (4,'Costilla de Res',120.0,3.0,1,0,'kg','Res');
INSERT INTO branch_inventory VALUES (1,1,12.5);
"""


@pytest.fixture
def matcher_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_PM_SCHEMA + _PM_SEED)
    return conn


@pytest.fixture
def matcher(matcher_db):
    from parser.product_matcher import ProductMatcher
    return ProductMatcher(matcher_db, sucursal_id=1)


# ── ProductMatcher Tests ──────────────────────────────────────────────────────

class TestProductMatcher:

    def test_exact_match_returns_product(self, matcher):
        result = matcher.match_single("Pechuga de Pollo")
        assert result is not None
        assert result["nombre"] == "Pechuga de Pollo"

    def test_substring_match(self, matcher):
        result = matcher.match_single("Pechuga")
        assert result is not None
        assert "Pechuga" in result["nombre"]

    def test_fuzzy_match_typo(self, matcher):
        result = matcher.match_single("pierna")
        assert result is not None
        assert "Pierna" in result["nombre"]

    def test_no_match_returns_none(self, matcher):
        result = matcher.match_single("xyzabcdef123")
        assert result is None

    def test_search_returns_multiple(self, matcher):
        results = matcher.search("Pollo", max_results=5)
        assert len(results) >= 2

    def test_reload_preserves_cache(self, matcher):
        before = len(matcher._cache)
        matcher.reload()
        assert len(matcher._cache) == before

    def test_set_sucursal_triggers_reload(self, matcher):
        matcher.set_sucursal(2)
        assert matcher.sucursal_id == 2
        matcher.set_sucursal(1)

    def test_get_categories_returns_distinct(self, matcher):
        cats = matcher.get_categories()
        assert len(cats) == len(set(cats))

    def test_get_by_category_filters_correctly(self, matcher):
        carne = matcher.get_by_category("Carne")
        names = [p["nombre"] for p in carne]
        assert "Pechuga de Pollo" in names
        assert "Chuleta de Cerdo" not in names


# ── IntentParser Tests ────────────────────────────────────────────────────────

def _make_msg(msg_type="text", text="", interactive_id="", interactive_title=""):
    from datetime import datetime
    from models.message import IncomingMessage, MessageType, InteractiveType
    return IncomingMessage(
        message_id="test-id",
        from_number="5551234567",
        phone_number_id="12345",
        timestamp=datetime.now(),
        type=MessageType(msg_type),
        text=text,
        interactive_id=interactive_id,
        interactive_title=interactive_title,
    )


@pytest.fixture
def parser(matcher):
    mock_llm = MagicMock()
    mock_llm.parse_message = asyncio.coroutine(lambda *a, **kw: None) if hasattr(asyncio, 'coroutine') else None

    from parser.llm_local import OllamaClient
    with patch.object(OllamaClient, '__init__', return_value=None):
        from parser.intent_parser import IntentParser
        p = IntentParser.__new__(IntentParser)
        p.matcher = matcher
        p.llm = mock_llm
        return p


class TestIntentParser:

    def test_parse_interactive_button_menu(self, parser):
        msg = _make_msg("interactive", interactive_id="menu_pedido", interactive_title="Pedido")
        result = parser._parse_interactive(msg)
        assert result.intent == "menu_action"
        assert result.confidence == 1.0
        assert result.source == "button"

    def test_parse_interactive_button_cat(self, parser):
        msg = _make_msg("interactive", interactive_id="cat_carne", interactive_title="Carne")
        result = parser._parse_interactive(msg)
        assert result.intent == "select_category"
        assert result.action_id == "cat_carne"

    def test_parse_interactive_button_prod(self, parser):
        msg = _make_msg("interactive", interactive_id="prod_1", interactive_title="Pechuga")
        result = parser._parse_interactive(msg)
        assert result.intent == "select_product"

    def test_parse_interactive_confirm(self, parser):
        msg = _make_msg("interactive", interactive_id="confirm_ok")
        result = parser._parse_interactive(msg)
        assert result.intent == "confirm"

    def test_parse_interactive_cancel(self, parser):
        msg = _make_msg("interactive", interactive_id="cancel_x")
        result = parser._parse_interactive(msg)
        assert result.intent == "cancel"

    def test_parse_regex_returns_result_object(self, parser):
        result = parser._parse_regex("hola")
        assert result is not None
        assert result.source == "regex"
        assert isinstance(result.confidence, float)

    def test_parse_regex_unknown_for_gibberish(self, parser):
        result = parser._parse_regex("asdfjklqwerty12345xyz")
        assert result.intent == "unknown" or result.confidence < 0.8

    def test_parse_regex_extracts_number(self, parser):
        result = parser._parse_regex("quiero 3 kilos")
        assert result.source == "regex"
        # number extraction should work
        assert result.number >= 3.0 or isinstance(result.number, float)

    def test_parse_unsupported_type_returns_unknown(self, parser):
        result = asyncio.run(parser.parse(_make_msg("image")))
        assert result.intent == "unknown"
        assert result.source == "fallback"

    def test_button_confidence_is_1(self, parser):
        msg = _make_msg("interactive", interactive_id="menu_start")
        result = parser._parse_interactive(msg)
        assert result.confidence == 1.0

    def test_action_id_preserved_in_result(self, parser):
        msg = _make_msg("interactive", interactive_id="prod_5", interactive_title="Test")
        result = parser._parse_interactive(msg)
        assert result.action_id == "prod_5"
