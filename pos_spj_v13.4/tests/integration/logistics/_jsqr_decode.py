"""Decodifica PNGs con el jsQR de la PWA dentro de QtWebEngine (el lector que usa
el teléfono cuando el navegador no trae BarcodeDetector).

Se corre en un PROCESO APARTE: QtWebEngine debe importarse antes de crear la
QApplication, y dentro de pytest ya existe una. Uso:

    python _jsqr_decode.py <jsQR.js> <png> [<png> ...]   → una línea por imagen
"""

import base64
import os
import sys

os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")
from PyQt5.QtCore import QEventLoop, QTimer, QUrl  # noqa: E402
from PyQt5.QtWebEngineWidgets import QWebEnginePage  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402


def _wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


def main(argv: list[str]) -> int:
    app = QApplication([])
    jsqr = open(argv[1], encoding="utf-8").read()
    for path in argv[2:]:
        data = base64.b64encode(open(path, "rb").read()).decode()
        page = QWebEnginePage()
        loaded = QEventLoop()
        page.loadFinished.connect(lambda _ok: loaded.quit())
        QTimer.singleShot(20000, loaded.quit)
        page.setHtml(f"<html><body><script>{jsqr}</script></body></html>", QUrl("about:blank"))
        loaded.exec_()
        page.runJavaScript(
            "(() => { const i = new Image(); i.onload = () => { const c = document."
            "createElement('canvas'); c.width = i.width; c.height = i.height; const x = "
            "c.getContext('2d'); x.drawImage(i, 0, 0); const d = x.getImageData(0, 0, c.width,"
            " c.height); const r = jsQR(d.data, d.width, d.height); window.__r = r ? r.data :"
            f" 'NO-DECODE'; }}; i.src = 'data:image/png;base64,{data}'; }})()")
        result = {}
        for _ in range(150):
            _wait(100)
            page.runJavaScript("window.__r || ''", lambda v: result.__setitem__("v", v))
            _wait(30)
            if result.get("v"):
                break
        print(result.get("v") or "TIMEOUT", flush=True)
        page.deleteLater()
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
