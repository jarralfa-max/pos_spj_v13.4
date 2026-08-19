"""SALES-20/POS-20 — Preservación visual: comparar golden master, corregir
proporciones, validar 1366×768, validar 1920×1080, validar claro/oscuro,
validar teclado, validar scanner.

Applies the SAME rigor `tests/visual/golden/sales_pos/` already applied to
the LEGACY `ModuloVentas` (SALES-1) to the new, parallel `SalesPosWorkspace`
built in SALES-19 — real widget construction, offscreen, at both target
resolutions, both themes, plus real keyboard/scanner interaction (not just
static geometry). `modulos/ventas.py` itself is not touched by this phase
(SALES-19's own explicit, user-confirmed scope decision) — its own 18
golden-master tests remain the authority for that tree, re-run unchanged
alongside this suite as part of every phase's regression check.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication
from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402

from backend.application.sales.permissions import SalesPermissions  # noqa: E402
from frontend.desktop.modules.sales_pos.sales_pos_presenter import SalesPosPresenter  # noqa: E402
from frontend.desktop.modules.sales_pos.sales_pos_workspace import SalesPosWorkspace  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeSession:
    def __init__(self, permissions=()):
        self.user_id = "cashier-1"
        self.active_branch_id = "branch-1"
        self.is_active = True
        self._permissions = set(permissions)

    def tiene_permiso(self, code: str) -> bool:
        return code in self._permissions


def _all_permissions_presenter() -> SalesPosPresenter:
    permissions = {v for v in vars(SalesPermissions).values() if isinstance(v, str)}
    return SalesPosPresenter(session_context=_FakeSession(permissions))


def _build(app, *, size=(1366, 768)):
    workspace = SalesPosWorkspace(_all_permissions_presenter())
    workspace.resize(*size)
    workspace.show()
    app.processEvents()
    return workspace


# ── Comparar golden master / corregir proporciones ──────────────────────

class TestGoldenMasterComparison:
    """Same structural invariant the legacy golden-master suite protects
    (`test_pos_preserves_two_panel_layout.py`): one splitter, two panels,
    catalog left / checkout right, cashier bar above it."""

    def test_still_exactly_one_two_panel_splitter(self, app):
        from PyQt5.QtWidgets import QSplitter

        workspace = _build(app)
        splitters = workspace.findChildren(QSplitter)
        assert len(splitters) == 1
        assert splitters[0].count() == 2
        workspace.close()

    def test_checkout_panel_stays_within_the_legacy_bounded_width(self, app):
        """The real proportion bug this phase found and fixed: an
        unconstrained QSplitter divided ~50/50, leaving the checkout panel
        ~900px wide at 1920x1080 (measured empirically before the fix).
        The legacy contract bounds it 380-600px — reproduced here, not
        pixel-matched against the legacy tree itself (a different, parallel
        widget), but against the SAME real numbers the legacy layout
        inventory documents."""
        workspace = _build(app, size=(1920, 1080))
        assert 380 <= workspace.checkout.width() <= 600
        workspace.close()


# ── Validar 1366×768 / 1920×1080 ────────────────────────────────────────

class TestResolutionValidation:
    @pytest.mark.parametrize("size", [(1366, 768), (1920, 1080)])
    def test_catalog_gets_the_majority_of_width_at_both_resolutions(self, app, size):
        workspace = _build(app, size=size)
        assert workspace.catalog.width() > workspace.checkout.width()
        workspace.close()

    @pytest.mark.parametrize("size", [(1366, 768), (1920, 1080)])
    def test_no_panel_collapses_to_zero_at_either_resolution(self, app, size):
        workspace = _build(app, size=size)
        assert workspace.catalog.width() > 200
        assert workspace.checkout.width() > 200
        assert workspace.cashier_bar.height() > 0
        workspace.close()

    def test_checkout_width_is_identical_at_both_resolutions(self, app):
        """The checkout sidebar is bounded, not proportional — its width
        should not grow just because the window did."""
        narrow = _build(app, size=(1366, 768))
        wide = _build(app, size=(1920, 1080))
        assert narrow.checkout.width() == wide.checkout.width()
        narrow.close()
        wide.close()


# ── Validar claro/oscuro ─────────────────────────────────────────────────

class TestThemeValidation:
    @pytest.mark.parametrize("theme", ["Oscuro", "Claro"])
    def test_renders_without_error_under_each_theme(self, app, theme):
        from config import TEMAS

        previous = app.styleSheet()
        try:
            app.setStyleSheet(TEMAS.get(theme, ""))
            workspace = _build(app)
            app.processEvents()
            # Structure must survive a theme switch — the QSS never
            # reparents/removes widgets, only restyles them.
            from PyQt5.QtWidgets import QSplitter

            assert len(workspace.findChildren(QSplitter)) == 1
            workspace.close()
        finally:
            app.setStyleSheet(previous)

    def test_no_component_sets_an_inline_stylesheet(self, app):
        """No module builds cards/buttons from raw styled QFrame/QPushButton
        — the look must come from the theme QSS alone (same rule
        `frontend/desktop/components/cards.py`'s own docstring states),
        never a per-widget `setStyleSheet(...)` call baked into POS-19's
        components."""
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "frontend" / "desktop" / "modules" / "sales_pos"
        offenders = []
        for path in root.rglob("*.py"):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"\.setStyleSheet\(", line):
                    offenders.append(f"{path.relative_to(root)}:{lineno}")
        assert not offenders, f"Inline stylesheet found: {offenders}"


# ── Validar teclado ───────────────────────────────────────────────────────

class TestKeyboardValidation:
    """Unlike the legacy screen's F6-F12 badges (confirmed decorative — no
    real `QShortcut` anywhere, `sales_pos_visual_contract.md` §4.1), these
    are real bindings wired to the exact same handlers the buttons trigger."""

    def test_seven_real_shortcuts_are_registered(self, app):
        workspace = _build(app)
        keys = {sc.key().toString() for sc in workspace._shortcuts}
        assert keys == {"F6", "F7", "F8", "F9", "F10", "F11", "F12"}
        workspace.close()

    def test_f9_key_event_triggers_the_same_handler_as_clicking_cobrar(self, app, monkeypatch):
        # Patch on the CLASS before construction so `_wire_shortcuts()` (run
        # exactly once, inside `__init__`, same as production) captures the
        # patched bound method directly. Re-wiring after construction would
        # leave the original QShortcuts alive too (Qt keeps parented
        # children alive regardless of Python references) — two QShortcuts
        # on the same key sequence makes Qt treat the key as AMBIGUOUS and
        # fire neither, which is what made an earlier version of this fix
        # fail even with focus correctly forced.
        calls = []
        monkeypatch.setattr(
            SalesPosWorkspace, "_on_checkout_requested", lambda self: calls.append("checkout"))
        workspace = _build(app)

        # A QShortcut only fires for a widget that actually has window focus
        # — real, not a test artifact: the same reason the legacy screen's
        # F6-F12 badges NEVER fired (no shortcut existed at all, so this
        # never mattered there). Offscreen platforms don't grant focus
        # automatically the way a real window manager does.
        workspace.activateWindow()
        QApplication.setActiveWindow(workspace)
        workspace.setFocus(Qt.OtherFocusReason)
        app.processEvents()

        QTest.keyClick(workspace, Qt.Key_F9)
        app.processEvents()
        assert calls == ["checkout"]
        workspace.close()

    def test_enter_in_search_box_emits_a_scan_not_a_live_filter(self, app):
        """A physical scanner is a fast typist + Enter — must be
        distinguishable from live-as-you-type browsing."""
        workspace = _build(app)
        received = []
        workspace.catalog.code_scanned.connect(received.append)
        workspace.catalog._search.setText("7501234567890")
        QTest.keyClick(workspace.catalog._search, Qt.Key_Return)
        assert received == ["7501234567890"]
        workspace.close()


# ── Validar scanner ──────────────────────────────────────────────────────

class TestScannerValidation:
    def test_scanned_code_with_no_active_sale_is_a_safe_no_op(self, app):
        workspace = _build(app)
        workspace._sale_id = None
        workspace._on_code_scanned("anything")  # must not raise
        workspace.close()

    def test_unresolved_code_shows_a_warning_not_a_silent_failure(self, app, monkeypatch):
        from backend.application.sales.result import SaleResult

        workspace = _build(app)
        workspace._sale_id = "sale-1"

        class _FailingPresenter:
            def scan_code(self, **kwargs):
                return SaleResult.fail("Ningún producto coincide con 'xyz'", "SCAN_CODE_NOT_RESOLVED")

        workspace._presenter = _FailingPresenter()
        shown = []
        monkeypatch.setattr(
            "frontend.desktop.modules.sales_pos.sales_pos_workspace.QMessageBox.warning",
            lambda *a, **k: shown.append(a[2]))
        workspace._on_code_scanned("xyz")
        assert shown and "xyz" in shown[0]
        workspace.close()
