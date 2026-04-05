# core/use_cases/pedido_wa.py — SPJ POS v13.1
"""
Caso de uso: Procesar Pedido WhatsApp

Orquesta el flujo completo:
  pedido entrante → validar sucursal y horario → registrar pedido
  → calcular anticipo si aplica → notificar al POS
  → publicar PEDIDO_NUEVO al EventBus → enviar confirmación al cliente

Centraliza lógica que antes estaba dispersa entre:
  - services/bot_pedidos.py (flujo principal)
  - integrations/pos_adapter.py (legacy)
  - webapp/api_pedidos.py (flujo alternativo)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger("spj.use_cases.pedido_wa")


# ── DTOs ──────────────────────────────────────────────────────────────────────

@dataclass
class ItemPedido:
    producto_id: int
    nombre:      str
    cantidad:    float
    precio:      float

    @property
    def subtotal(self) -> float:
        return round(self.cantidad * self.precio, 2)


@dataclass
class ResultadoPedido:
    ok:              bool
    pedido_id:       int        = 0
    numero_pedido:   str        = ""
    total:           float      = 0.0
    anticipo:        float      = 0.0
    programado:      bool       = False
    hora_estimada:   str        = ""
    mensaje_cliente: str        = ""
    error:           str        = ""


# ── Caso de uso ───────────────────────────────────────────────────────────────

class ProcesarPedidoWAUC:
    """
    Orquestador del flujo de pedido por WhatsApp.

    Uso desde el bot:
        uc = ProcesarPedidoWAUC.desde_container(container)
        resultado = uc.ejecutar(items, cliente_tel, sucursal_id, hora_deseada)
    """

    def __init__(
        self,
        db,
        anticipo_service = None,
        whatsapp_service = None,
        event_bus        = None,
    ):
        self._db       = db
        self._anticipo = anticipo_service
        self._wa       = whatsapp_service
        self._bus      = event_bus

    @classmethod
    def desde_container(cls, container) -> "ProcesarPedidoWAUC":
        return cls(
            db               = container.db,
            anticipo_service = getattr(container, "anticipo_service", None),
            whatsapp_service = getattr(container, "whatsapp_service", None),
            event_bus        = _get_bus(),
        )

    # ── Punto de entrada ──────────────────────────────────────────────────────

    def ejecutar(
        self,
        items:         List[ItemPedido],
        cliente_tel:   str,
        sucursal_id:   int,
        usuario:       str   = "bot_wa",
        hora_deseada:  str   = "",
        programado:    bool  = False,
        notas:         str   = "",
    ) -> ResultadoPedido:
        """
        Registra un pedido WhatsApp completo.
        Calcula anticipo si aplica. Notifica al POS via EventBus.
        """
        if not items:
            return ResultadoPedido(ok=False, error="Pedido sin items.")

        total = round(sum(it.subtotal for it in items), 2)

        # ── 1. Calcular anticipo ──────────────────────────────────────────────
        anticipo = 0.0
        if self._anticipo and total > 0:
            try:
                anticipo = self._anticipo.calcular_anticipo(
                    monto        = total,
                    sucursal_id  = sucursal_id,
                )
            except Exception as e:
                logger.warning("Anticipo pedido tel=%s: %s", cliente_tel, e)

        # ── 2. Registrar pedido en BD ─────────────────────────────────────────
        numero_pedido = _generar_numero_pedido(self._db)
        try:
            cur = self._db.execute(
                """
                INSERT INTO pedidos_whatsapp
                    (numero, telefono_cliente, sucursal_id, total, anticipo,
                     estado, programado, hora_deseada, notas, usuario_registro,
                     fecha)
                VALUES (?,?,?,?,?,'pendiente',?,?,?,?,datetime('now'))
                """,
                (numero_pedido, cliente_tel, sucursal_id, total, anticipo,
                 int(programado), hora_deseada, notas, usuario)
            )
            pedido_id = cur.lastrowid
            # Guardar items
            for it in items:
                self._db.execute(
                    "INSERT INTO pedidos_whatsapp_items"
                    "(pedido_id,producto_id,nombre,cantidad,precio) VALUES(?,?,?,?,?)",
                    (pedido_id, it.producto_id, it.nombre, it.cantidad, it.precio)
                )
            try:
                self._db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.error("Registrar pedido WA tel=%s: %s", cliente_tel, e)
            return ResultadoPedido(ok=False, error=f"Error al registrar: {e}")

        # ── 3. Publicar evento PEDIDO_NUEVO ───────────────────────────────────
        if self._bus:
            try:
                self._bus.publish(
                    "PEDIDO_NUEVO",
                    {
                        "pedido_id":    pedido_id,
                        "numero":       numero_pedido,
                        "sucursal_id":  sucursal_id,
                        "total":        total,
                        "anticipo":     anticipo,
                        "telefono":     cliente_tel,
                        "programado":   programado,
                        "hora_deseada": hora_deseada,
                    },
                    async_=True,
                )
            except Exception as e:
                logger.debug("EventBus PEDIDO_NUEVO: %s", e)

        # ── 4. Construir mensaje de confirmación ──────────────────────────────
        msg = self._construir_confirmacion(
            numero_pedido, total, anticipo, programado, hora_deseada, items
        )

        logger.info(
            "Pedido WA %s registrado — tel=%s total=$%.2f anticipo=$%.2f",
            numero_pedido, cliente_tel, total, anticipo,
        )
        return ResultadoPedido(
            ok            = True,
            pedido_id     = pedido_id,
            numero_pedido = numero_pedido,
            total         = total,
            anticipo      = anticipo,
            programado    = programado,
            hora_estimada = hora_deseada,
            mensaje_cliente = msg,
        )

    def _construir_confirmacion(
        self,
        numero:   str,
        total:    float,
        anticipo: float,
        programado: bool,
        hora:     str,
        items:    List[ItemPedido],
    ) -> str:
        resumen = "\n".join(
            f"  • {it.nombre} x{it.cantidad:.1f} = ${it.subtotal:.2f}"
            for it in items
        )
        msg = f"✅ Pedido #{numero} confirmado\n\n{resumen}\n\nTotal: ${total:.2f}"
        if anticipo > 0:
            msg += f"\nAnticipo requerido: ${anticipo:.2f}"
        if programado and hora:
            msg += f"\n📅 Programado para: {hora}"
        return msg


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generar_numero_pedido(db) -> str:
    try:
        row = db.execute(
            "SELECT COUNT(*) FROM pedidos_whatsapp WHERE fecha >= date('now')"
        ).fetchone()
        n = (row[0] if row else 0) + 1
        hoy = datetime.now().strftime("%d%m")
        return f"PED-{hoy}-{n:04d}"
    except Exception:
        import uuid
        return f"PED-{uuid.uuid4().hex[:8].upper()}"


def _get_bus():
    try:
        from core.events.event_bus import get_bus
        return get_bus()
    except Exception:
        return None
