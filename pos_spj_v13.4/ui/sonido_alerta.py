
# ui/sonido_alerta.py — SPJ POS v12
"""
Módulo dedicado de alertas sonoras del POS.
Independiente de servicios para poder usarse desde cualquier módulo UI.

Sonidos:
  - pedido_nuevo   : tono triple ascendente (pedido WhatsApp)
  - pago_confirmado: tono triple positivo
  - alerta_stock   : tono doble de advertencia
  - error          : tono grave
  - caja_abierta   : tono corto
"""
from __future__ import annotations
import threading, logging

logger = logging.getLogger("spj.ui.sonido")


class SonidoAlerta:
    """
    Reproduce alertas sonoras multiplataforma:
      Windows  → winsound.Beep
      Linux    → aplay con bytes PCM generados
      macOS    → afplay o NSSound
      Fallback → terminal bell (\a)
    """
        # Frecuencias y duraciones de cada tipo de alerta
    _TONOS = {
        "pedido_nuevo":    [(700, 120), (900, 120), (1100, 200)],
        "pago_confirmado": [(600, 100), (800, 100), (1000, 180)],
        "alerta_stock":    [(500, 200), (300, 300)],
        "error":           [(280, 400)],
        "caja_abierta":    [(800, 80)],
        "alerta_generico": [(600, 150), (600, 150)],
    }

    @classmethod
    def play(cls, tipo: str = "pedido_nuevo", blocking: bool = False):
        """Reproduce un tono. Non-blocking por defecto."""
        tonos = cls._TONOS.get(tipo, cls._TONOS["alerta_generico"])
        if blocking:
            cls._reproducir(tonos)
        else:
            t = threading.Thread(
                target=cls._reproducir, args=(tonos,),
                daemon=True, name=f"SonidoAlerta-{tipo}")
            t.start()

    # Atajos semánticos
    @classmethod
    def pedido_nuevo(cls):    cls.play("pedido_nuevo")
    @classmethod
    def pago_confirmado(cls): cls.play("pago_confirmado")
    @classmethod
    def alerta_stock(cls):    cls.play("alerta_stock")
    @classmethod
    def error(cls):           cls.play("error")
    @classmethod
    def caja_abierta(cls):    cls.play("caja_abierta")

    # También expone el método legacy usado por notificaciones.py v11
    @classmethod
    def play_alert(cls):  cls.pedido_nuevo()
    @classmethod
    def play_pago(cls):   cls.pago_confirmado()
    @classmethod
    def play_error(cls):  cls.error()

    # ── Motor de reproducción ──────────────────────────────────────
    @staticmethod
    def _reproducir(tonos: list):
        if SonidoAlerta._windows(tonos):  return
        if SonidoAlerta._linux(tonos):    return
        if SonidoAlerta._macos(tonos):    return
        SonidoAlerta._bell()

    @staticmethod
    def _windows(tonos: list) -> bool:
        try:
            import winsound
            for freq, dur in tonos:
                winsound.Beep(max(37, min(32767, freq)), dur)
            return True
        except Exception:
            return False

    @staticmethod
    def _linux(tonos: list) -> bool:
        try:
            import subprocess, struct, math
            rate = 22050
            frames = b""
            pause  = struct.pack(f"<{int(rate*0.04)}h",
                                 *[0]*int(rate*0.04))
            for freq, dur_ms in tonos:
                n      = int(rate * dur_ms / 1000)
                wave   = struct.pack(
                    f"<{n}h",
                    *[int(28000 * math.sin(2 * math.pi * freq * i / rate))
                      for i in range(n)])
                frames += wave + pause
            # Cabecera WAV mínima
            hdr = (b"RIFF"
                   + struct.pack("<I", 36 + len(frames))
                   + b"WAVEfmt "
                   + struct.pack("<IHHIIHH",
                                 16, 1, 1, rate, rate * 2, 2, 16)
                   + b"data"
                   + struct.pack("<I", len(frames)))
            proc = subprocess.Popen(
                ["aplay", "-q", "-f", "S16_LE", "-r", str(rate), "-c", "1"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            proc.communicate(hdr + frames, timeout=5)
            return proc.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _macos(tonos: list) -> bool:
        try:
            import subprocess
            # afplay con archivo temporal
            import tempfile, struct, math
            rate   = 22050
            frames = b""
            for freq, dur_ms in tonos:
                n      = int(rate * dur_ms / 1000)
                frames += struct.pack(
                    f"<{n}h",
                    *[int(28000 * math.sin(2*math.pi*freq*i/rate))
                      for i in range(n)])
            hdr = (b"RIFF"
                   + struct.pack("<I", 36 + len(frames))
                   + b"WAVEfmt "
                   + struct.pack("<IHHIIHH", 16,1,1,rate,rate*2,2,16)
                   + b"data" + struct.pack("<I", len(frames)))
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(hdr + frames); tmp = f.name
            subprocess.run(["afplay", tmp],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           timeout=5)
            import os; os.unlink(tmp)
            return True
        except Exception:
            return False

    @staticmethod
    def _bell():
        try:
            print("\a" * 2, end="", flush=True)
        except Exception:
            pass
