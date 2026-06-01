from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QT_QSS_DIRS = ("interfaz", "modulos", "ui", "presentation", "core")


def _qt_style_sources():
    for rel in QT_QSS_DIRS:
        base = ROOT / rel
        if not base.exists():
            continue
        yield from base.rglob("*.py")
        yield from base.rglob("*.qss")


def test_qt_qss_sources_do_not_use_unsupported_box_shadow():
    offenders = []
    for path in _qt_style_sources():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "box-shadow" in text:
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == [], "Qt/QSS no soporta box-shadow; usa QGraphicsDropShadowEffect: " + ", ".join(offenders)
