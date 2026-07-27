# core/services/discount_guard.py — SPJ POS v13.2
"""
Motor de protección financiera para descuentos.

Reglas:
  1. Por debajo del costo → BLOQUEADO siempre (pérdida garantizada)
  2. Descuento > umbral_gerente (default 20%) → requiere PIN de gerente
  3. Margen mínimo configurable por producto o categoría

La validación es síncrona y se llama ANTES de aplicar el descuento.
"""
from __future__ import annotations
import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger("spj.discount_guard")

_CFG_CACHE_TTL = 60  # segundos — refresca config cada minuto


class DiscountGuard:
    """
    Valida si un descuento es financieramente seguro.
    Se instancia con la DB y devuelve (permitido, razon, requiere_pin).
    """
    
    # Defaults — overrideable via configuraciones table
    DEFAULT_MAX_DESCUENTO_SIN_PIN = 20.0   # % máximo sin autorización
    DEFAULT_MARGEN_MINIMO         = 5.0    # % margen mínimo permitido

    def __init__(self, db):
        self.db = db
        self._cfg_cache: dict = {}
        self._cfg_timestamps: dict = {}

    def _cfg(self, clave: str, default: str) -> str:
        now = time.monotonic()
        if clave not in self._cfg_cache or (now - self._cfg_timestamps.get(clave, 0)) > _CFG_CACHE_TTL:
            try:
                r = self.db.execute(
                    "SELECT valor FROM configuraciones WHERE clave=?", (clave,)
                ).fetchone()
                self._cfg_cache[clave] = r[0] if r else default
            except Exception:
                self._cfg_cache[clave] = default
            self._cfg_timestamps[clave] = now
        return self._cfg_cache[clave]

    def limpiar_cache(self) -> None:
        self._cfg_cache.clear()
        self._cfg_timestamps.clear()

    def validar_descuento(
        self,
        producto_id: int,
        precio_original: float,
        precio_con_descuento: float,
        descuento_pct: float,
        rol_usuario: str = "cajero",
    ) -> Tuple[bool, str, bool]:
        """
        Valida si el descuento es permitido.

        Returns:
            (permitido, mensaje, requiere_pin_gerente)
        """
        max_sin_pin = float(self._cfg("descuento_max_sin_pin", 
                                      str(self.DEFAULT_MAX_DESCUENTO_SIN_PIN)))
        margen_min  = float(self._cfg("margen_minimo_venta",
                                      str(self.DEFAULT_MARGEN_MINIMO)))

        # Obtener costo del producto
        costo = self._get_costo(producto_id)

        # Regla 1: NUNCA por debajo del costo (pérdida garantizada)
        if costo > 0 and precio_con_descuento < costo:
            perdida = costo - precio_con_descuento
            return (
                False,
                f"❌ BLOQUEADO: El precio ${precio_con_descuento:.2f} está por debajo "
                f"del costo (${costo:.2f}). Pérdida de ${perdida:.2f} por unidad.",
                False
            )

        # Regla 2: Margen mínimo
        if costo > 0 and precio_con_descuento > 0:
            margen_real = ((precio_con_descuento - costo) / precio_con_descuento) * 100
            if margen_real < margen_min:
                return (
                    False,
                    f"❌ BLOQUEADO: Margen real {margen_real:.1f}% es menor al mínimo "
                    f"permitido ({margen_min:.1f}%). Sube el precio mínimo a "
                    f"${costo / (1 - margen_min/100):.2f}.",
                    False
                )

        # Regla 3: Descuento mayor al umbral → requiere PIN de gerente
        if descuento_pct > max_sin_pin:
            # Admins y gerentes pueden aprobar sin PIN adicional si ya están autenticados
            if rol_usuario.lower() in ("admin", "administrador", "gerente"):
                return (
                    True,
                    f"⚠️  Descuento {descuento_pct:.1f}% autorizado por {rol_usuario}.",
                    False
                )
            return (
                True,
                f"⚠️  Descuento {descuento_pct:.1f}% supera el límite automático "
                f"({max_sin_pin:.0f}%). Se requiere PIN de gerente.",
                True   # UI debe solicitar PIN
            )

        return (True, "", False)

    def solicitar_pin_gerente(self, db, pin_ingresado: str) -> bool:
        """
        Verifica el PIN de un gerente o admin contra el hash almacenado.
        Soporta bcrypt (preferido) y SHA-256 (legacy). NUNCA texto plano.
        """
        if not pin_ingresado:
            return False
        try:
            rows = db.execute(
                """SELECT contrasena FROM usuarios
                   WHERE rol IN ('admin','administrador','gerente')
                     AND activo=1"""
            ).fetchall()
        except Exception as e:
            logger.error("solicitar_pin_gerente: error DB: %s", e)
            return False

        import hashlib
        sha256_ingresado = hashlib.sha256(pin_ingresado.encode()).hexdigest()

        try:
            import bcrypt
            HAS_BCRYPT = True
        except ImportError:
            HAS_BCRYPT = False

        for row in rows:
            stored = row[0] if row else ""
            if not stored:
                continue
            if stored.startswith(("$2b$", "$2a$", "$2y$")):
                if HAS_BCRYPT:
                    try:
                        if bcrypt.checkpw(pin_ingresado.encode("utf-8"), stored.encode("utf-8")):
                            return True
                    except Exception:
                        pass
            elif stored == sha256_ingresado:
                return True
            # Nota: comparación de texto plano eliminada intencionalmente

        return False

    def _get_costo(self, producto_id: int) -> float:
        try:
            r = self.db.execute(
                "SELECT COALESCE(precio_compra,0) FROM productos WHERE id=?",
                (producto_id,)
            ).fetchone()
            return float(r[0]) if r else 0.0
        except Exception:
            return 0.0

    def get_config(self) -> dict:
        return {
            "max_sin_pin":  float(self._cfg("descuento_max_sin_pin", str(self.DEFAULT_MAX_DESCUENTO_SIN_PIN))),
            "margen_minimo": float(self._cfg("margen_minimo_venta",   str(self.DEFAULT_MARGEN_MINIMO))),
        }

    def guardar_config(self, max_sin_pin: float, margen_minimo: float) -> None:
        for clave, valor in [
            ("descuento_max_sin_pin", str(max_sin_pin)),
            ("margen_minimo_venta",   str(margen_minimo)),
        ]:
            self.db.execute(
                "INSERT INTO configuraciones(clave,valor) VALUES(?,?) "
                "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                (clave, valor)
            )
        try: self.db.commit()
        except Exception: pass
        self.limpiar_cache()
