"""Qt UI fixtures; temporary folders inherit Windows workspace permissions."""
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def qt_font_resources():
    """Windows offscreen Qt starts with an empty font database.

    Load actual installed fonts so visual tests exercise text metrics and pixels,
    rather than silently accepting blank-label screenshots.
    """
    from PyQt5.QtCore import QStandardPaths
    from PyQt5.QtGui import QFont, QFontDatabase
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    if not QFontDatabase().families():
        for directory in QStandardPaths.standardLocations(QStandardPaths.FontsLocation):
            for name in ("segoeui.ttf", "segoeuib.ttf", "arial.ttf", "DejaVuSans.ttf"):
                path = Path(directory) / name
                if path.is_file():
                    QFontDatabase.addApplicationFont(str(path))
    families = QFontDatabase().families()
    if families:
        app.setFont(QFont("Segoe UI" if "Segoe UI" in families else families[0], 10))
    yield app


@pytest.fixture
def ui_tmp_path():
    from PyQt5.QtCore import QTemporaryDir

    package = Path(__file__).resolve().parents[2]
    root = package / ".test_tmp"
    root.mkdir(exist_ok=True)
    directory = QTemporaryDir(str(root / "qt-ui-XXXXXX"))
    assert directory.isValid(), "Qt could not create a writable UI test directory"
    path = Path(directory.path()).resolve()
    assert path.is_relative_to(root.resolve())
    yield path
    directory.remove()
