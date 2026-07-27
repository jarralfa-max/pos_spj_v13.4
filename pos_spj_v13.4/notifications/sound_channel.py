"""Sound notification channel — uses QSoundEffect with cooldown.

Requirements:
  - PyQt5.QtMultimedia must be installed.
  - Audio files must exist under assets/sounds/ relative to the project root.
    Expected files (WAV format; QSoundEffect only supports WAV):
      delivery_new.wav     — new order received
      delivery_ready.wav   — order ready / in preparation
      delivery_urgent.wav  — urgent / late order

Call ONLY from the Qt main thread (QSoundEffect is not thread-safe).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Dict, Optional

from notifications.base import NotificationChannel, NotificationPayload

logger = logging.getLogger("spj.notifications.sound")

# Map event_type → sound file stem
_EVENT_SOUND: Dict[str, str] = {
    "delivery_new":       "delivery_new",
    "delivery_created":   "delivery_new",
    "delivery_preparing": "delivery_ready",
    "delivery_ready":     "delivery_ready",
    "delivery_delivered": "delivery_ready",
    "delivery_urgent":    "delivery_urgent",
    "driver_late":        "delivery_urgent",
}

_DEFAULT_COOLDOWN_S = 5.0   # seconds between same-sound plays


def _find_assets_dir() -> str:
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "assets", "sounds"),
        os.path.join(os.getcwd(), "assets", "sounds"),
    ]
    for p in candidates:
        p = os.path.normpath(p)
        if os.path.isdir(p):
            return p
    return ""


class SoundNotificationChannel(NotificationChannel):
    """Plays a WAV sound via QSoundEffect.

    Parameters
    ----------
    cooldown_s:
        Minimum seconds between plays of the same sound (anti-spam).
    volume:
        0.0 – 1.0 playback volume.
    """

    def __init__(self, cooldown_s: float = _DEFAULT_COOLDOWN_S, volume: float = 0.9) -> None:
        self._cooldown_s   = cooldown_s
        self._volume       = max(0.0, min(1.0, volume))
        self._last_play: Dict[str, float] = {}
        self._effects: Dict[str, object] = {}
        self._qt_ok: Optional[bool] = None
        self._assets_dir = _find_assets_dir()

    def is_available(self) -> bool:
        if self._qt_ok is None:
            try:
                from PyQt5.QtMultimedia import QSoundEffect  # noqa: F401
                self._qt_ok = True
            except ImportError:
                self._qt_ok = False
                logger.warning("SoundNotificationChannel: PyQt5.QtMultimedia unavailable")
        return bool(self._qt_ok)

    def send(self, payload: NotificationPayload) -> bool:
        if not self.is_available():
            return False
        sound_name = _EVENT_SOUND.get(payload.event_type, "delivery_new")
        return self._play(sound_name, payload.priority)

    def _play(self, sound_name: str, priority: str = "normal") -> bool:
        now = time.monotonic()
        cooldown = self._cooldown_s if priority != "urgent" else 1.0
        if now - self._last_play.get(sound_name, 0) < cooldown:
            logger.debug("SoundChannel: cooldown active for %s", sound_name)
            return False

        effect = self._get_or_create_effect(sound_name)
        if effect is None:
            return False

        try:
            effect.play()
            self._last_play[sound_name] = now
            logger.debug("SoundChannel: played %s", sound_name)
            return True
        except Exception as exc:
            logger.warning("SoundChannel play failed: %s", exc)
            return False

    def _get_or_create_effect(self, sound_name: str):
        if sound_name in self._effects:
            return self._effects[sound_name]

        if not self._assets_dir:
            logger.warning("SoundChannel: assets/sounds dir not found")
            return None

        wav_path = os.path.join(self._assets_dir, f"{sound_name}.wav")
        if not os.path.isfile(wav_path):
            logger.info("SoundChannel: %s not found — skipping (add WAV to assets/sounds/)", wav_path)
            self._effects[sound_name] = None
            return None

        try:
            from PyQt5.QtCore import QUrl
            from PyQt5.QtMultimedia import QSoundEffect
            effect = QSoundEffect()
            effect.setSource(QUrl.fromLocalFile(wav_path))
            effect.setVolume(self._volume)
            self._effects[sound_name] = effect
            logger.debug("SoundChannel: loaded %s", wav_path)
            return effect
        except Exception as exc:
            logger.warning("SoundChannel load failed: %s", exc)
            self._effects[sound_name] = None
            return None
