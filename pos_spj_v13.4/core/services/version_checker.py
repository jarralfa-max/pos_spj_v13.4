# core/services/version_checker.py — SPJ POS v13
"""
Verificador de actualizaciones en segundo plano.
Compara la versión actual contra un endpoint JSON configurable.
No bloquea la UI — usa QThread.
"""
from __future__ import annotations
import logging
from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger("spj.version_checker")


class VersionChecker(QThread):
    update_available = pyqtSignal(dict)  # {'version': '13.1.0', 'url': '...', 'notas': '...'}

    def __init__(self, current_version: str, parent=None):
        super().__init__(parent)
        self.current_version = current_version
        self._callback = None

    def check_async(self, callback=None):
        self._callback = callback
        self.start()

    def run(self):
        try:
            import urllib.request, json
            url = "https://raw.githubusercontent.com/spjpos/spjpos/main/version.json"
            req = urllib.request.Request(url, headers={"User-Agent": "SPJ-POS/13"})
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read().decode())
            latest = data.get("version", "")
            if latest and self._is_newer(latest, self.current_version):
                info = {
                    "version": latest,
                    "url":     data.get("url", ""),
                    "notas":   data.get("notas", "Nueva versión disponible"),
                }
                if self._callback:
                    self._callback(info)
                self.update_available.emit(info)
        except Exception as e:
            logger.debug("version_checker: %s", e)

    @staticmethod
    def _is_newer(latest: str, current: str) -> bool:
        try:
            def parse(v): return tuple(int(x) for x in v.strip().split(".")[:3])
            return parse(latest) > parse(current)
        except Exception:
            return False
