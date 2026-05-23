from __future__ import annotations


class NotificationSoundService:
    """Non-blocking sound helper with simple dedupe guard."""

    def __init__(self):
        self._played = set()

    def play_for_notification(self, dedupe_key: str, severity: str = "info") -> bool:
        if not dedupe_key:
            return False
        if dedupe_key in self._played:
            return False
        self._played.add(dedupe_key)
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                QApplication.beep()
                return True
        except Exception:
            pass
        return False
