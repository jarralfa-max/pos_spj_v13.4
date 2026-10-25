"""Carga la PWA de Logística servida por la API en QtWebEngine (Chromium 83:
más viejo que cualquier teléfono soportado) e imprime los errores de consola.

Proceso aparte por la misma razón que `_jsqr_decode.py`. Uso:

    python _pwa_console.py <puerto>   → «OK» o una línea «ERROR …» por error
"""

import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")
from PyQt5.QtCore import QEventLoop, QTimer, QUrl  # noqa: E402
from PyQt5.QtWebEngineWidgets import QWebEnginePage  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402


def _wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


def main(port: int) -> int:
    import uvicorn

    from backend.api.main import create_app

    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port,
                                           log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    app = QApplication([])
    errores = []

    class Page(QWebEnginePage):
        def javaScriptConsoleMessage(self, level, message, line, source):
            if int(level) >= 2:      # ErrorMessageLevel
                errores.append(f"ERROR {message} ({source}:{line})")

    page = Page()
    loaded = QEventLoop()
    page.loadFinished.connect(lambda _ok: loaded.quit())
    QTimer.singleShot(20000, loaded.quit)
    page.load(QUrl(f"http://127.0.0.1:{port}/mobile/logistics/"))
    loaded.exec_()
    _wait(2500)
    # El lector se carga al abrir la cámara: se fuerza aquí.
    page.runJavaScript("var s=document.createElement('script');s.src='vendor/jsQR.js';"
                       "s.onload=()=>window.__jsqr=typeof jsQR;document.head.append(s);")
    _wait(2000)
    estado = {}
    page.runJavaScript("window.__jsqr || 'no'", lambda v: estado.__setitem__("jsqr", v))
    _wait(500)
    if estado.get("jsqr") != "function":
        errores.append(f"ERROR jsQR no cargó: {estado.get('jsqr')!r}")
    for linea in errores:
        print(linea, flush=True)
    if not errores:
        print("OK", flush=True)
    server.should_exit = True
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1])))
