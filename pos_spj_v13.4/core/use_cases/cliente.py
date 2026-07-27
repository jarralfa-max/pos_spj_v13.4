# core/use_cases/cliente.py — SPJ POS v13.5
"""
Caso de uso: Gestionar Cliente

Orquesta el ciclo de vida del cliente:
  1. Crear cliente → inicializar fidelidad → asiento AR (si crédito) → EventBus
  2. Actualizar campos permitidos → EventBus
  3. Dar de baja (soft-delete) → EventBus

Brecha que cierra: ClienteRepository.crear() y actualizar() son usados
directamente desde 34+ módulos de UI sin pasar por la capa UC.
Este UC centraliza la lógica de orquestación sin modificar el repositorio.

Acceso desde AppContainer: container.uc_cliente
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("spj.use_cases.cliente")


# ── DTOs ─────────────────────────────────────────────────────────────────────

@dataclass
class DatosCliente:
    nombre:           str
    telefono:         str   = ""
    email:            str   = ""
    direccion:        str   = ""
    notas:            str   = ""
    allows_credit:    bool  = False
    credit_limit:     float = 0.0
    codigo_fidelidad: Optional[str] = None


@dataclass
class ResultadoCliente:
    ok:         bool
    cliente_id: int  = 0
    mensaje:    str  = ""
    error:      str  = ""


# ── Caso de uso ───────────────────────────────────────────────────────────────

class GestionarClienteUC:
    """
    Orquestador del ciclo de vida de clientes.

    Uso desde AppContainer:
        uc = container.uc_cliente
        res = uc.crear_cliente(datos, sucursal_id, usuario)
    """

    def __init__(
        self,
        cliente_repo,
        loyalty_service = None,
        finance_service = None,
        event_bus       = None,
    ):
        self._repo    = cliente_repo
        self._loyalty = loyalty_service
        self._finance = finance_service
        self._bus     = event_bus

    @classmethod
    def desde_container(cls, container) -> "GestionarClienteUC":
        from core.events.event_bus import EventBus
        return cls(
            cliente_repo    = container.cliente_repo,
            loyalty_service = getattr(container, "loyalty_service", None),
            finance_service = getattr(container, "finance_service", None),
            event_bus       = EventBus(),
        )

    # ── Crear ────────────────────────────────────────────────────────────────

    def crear_cliente(
        self,
        datos:       DatosCliente,
        sucursal_id: int,
        usuario:     str,
    ) -> ResultadoCliente:
        """
        Crea un nuevo cliente, opcionalmente abre línea de crédito y registra
        en el ledger de fidelidad.
        """
        if not datos.nombre or not datos.nombre.strip():
            return ResultadoCliente(ok=False, error="El nombre del cliente es obligatorio.")

        # ── 1. Crear en BD ───────────────────────────────────────────────────
        try:
            cliente_id = self._repo.crear(
                nombre           = datos.nombre.strip(),
                telefono         = datos.telefono,
                email            = datos.email,
                direccion        = datos.direccion,
                notas            = datos.notas,
                codigo_fidelidad = datos.codigo_fidelidad,
            )
        except Exception as exc:
            logger.error("GestionarClienteUC.crear: %s", exc)
            return ResultadoCliente(ok=False, error=str(exc))

        # ── 2. Asiento apertura de crédito  [1301 / 3101] ────────────────────
        if datos.allows_credit and datos.credit_limit > 0 and self._finance:
            try:
                self._finance.registrar_asiento(
                    debe         = "1301",
                    haber        = "3101",
                    concepto     = f"Apertura crédito cliente {datos.nombre.strip()}",
                    monto        = datos.credit_limit,
                    modulo       = "clientes",
                    referencia_id= cliente_id,
                    evento       = "CREDITO_CLIENTE_APERTURA",
                    sucursal_id  = sucursal_id,
                )
            except Exception as exc:
                logger.warning("GestionarClienteUC asiento crédito: %s", exc)

        # ── 3. Inicializar ledger de fidelidad (soft fail) ───────────────────
        if self._loyalty:
            try:
                if hasattr(self._loyalty, "registrar_en_ledger"):
                    self._loyalty.registrar_en_ledger(
                        cliente_id  = cliente_id,
                        tipo        = "acumulacion",
                        puntos      = 0,
                        descripcion = "Registro inicial",
                        usuario     = usuario,
                    )
            except Exception as exc:
                logger.debug("GestionarClienteUC loyalty init: %s", exc)

        # ── 4. Publicar evento ───────────────────────────────────────────────
        if self._bus:
            try:
                from core.events.event_bus import CLIENTE_CREADO
                self._bus.publish(
                    CLIENTE_CREADO,
                    {
                        "cliente_id":  cliente_id,
                        "nombre":      datos.nombre.strip(),
                        "telefono":    datos.telefono,
                        "sucursal_id": sucursal_id,
                        "usuario":     usuario,
                    },
                    async_=True,
                )
            except Exception as exc:
                logger.warning("GestionarClienteUC publish crear: %s", exc)

        return ResultadoCliente(
            ok=True,
            cliente_id=cliente_id,
            mensaje=f"Cliente '{datos.nombre.strip()}' creado correctamente.",
        )

    # ── Actualizar ───────────────────────────────────────────────────────────

    def actualizar_cliente(
        self,
        cliente_id: int,
        campos:     dict,
        usuario:    str,
    ) -> ResultadoCliente:
        """Actualiza campos permitidos de un cliente existente."""
        if not self._repo_existe(cliente_id):
            return ResultadoCliente(
                ok=False, error=f"Cliente {cliente_id} no encontrado."
            )
        try:
            self._repo.actualizar(cliente_id, **campos)
        except Exception as exc:
            logger.error("GestionarClienteUC.actualizar: %s", exc)
            return ResultadoCliente(ok=False, error=str(exc))

        if self._bus:
            try:
                from core.events.event_bus import CLIENTE_ACTUALIZADO
                self._bus.publish(
                    CLIENTE_ACTUALIZADO,
                    {"cliente_id": cliente_id, "campos": list(campos.keys()), "usuario": usuario},
                    async_=True,
                )
            except Exception as exc:
                logger.warning("GestionarClienteUC publish actualizar: %s", exc)

        return ResultadoCliente(ok=True, cliente_id=cliente_id, mensaje="Cliente actualizado.")

    # ── Dar de baja ──────────────────────────────────────────────────────────

    def dar_de_baja(self, cliente_id: int, usuario: str) -> ResultadoCliente:
        """Soft-delete: marca al cliente como inactivo preservando historial."""
        try:
            self._repo.dar_de_baja(cliente_id)
        except Exception as exc:
            logger.error("GestionarClienteUC.dar_de_baja: %s", exc)
            return ResultadoCliente(ok=False, error=str(exc))

        if self._bus:
            try:
                from core.events.event_bus import CLIENTE_ACTUALIZADO
                self._bus.publish(
                    CLIENTE_ACTUALIZADO,
                    {"cliente_id": cliente_id, "accion": "baja", "usuario": usuario},
                    async_=True,
                )
            except Exception as exc:
                logger.warning("GestionarClienteUC publish baja: %s", exc)

        return ResultadoCliente(ok=True, cliente_id=cliente_id, mensaje="Cliente dado de baja.")

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _repo_existe(self, cliente_id: int) -> bool:
        try:
            if hasattr(self._repo, "existe"):
                return self._repo.existe(cliente_id)
            row = self._repo.db.execute(
                "SELECT id FROM clientes WHERE id=? AND activo=1", (cliente_id,)
            ).fetchone()
            return row is not None
        except Exception:
            return True  # Asumir que existe; el repo lanzará si no
