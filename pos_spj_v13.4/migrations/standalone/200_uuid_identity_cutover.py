"""Migración 200 — CORTE UUID GLOBAL DE IDENTIDAD (FASE 2.5).

⚠️  MIGRACIÓN DESTRUCTIVA Y GATED. NO está registrada en ``migrations/engine.py``
    a propósito: nunca debe ejecutarse automáticamente en el bootstrap. Convierte
    TODA PK/FK entera a UUIDv7 ``TEXT`` en una sola transacción atómica.

Precondiciones obligatorias (REGLA CERO, pasos 1-3):
  1. Aplicación cerrada, sin otras instancias.
  2. Backup completo del archivo .db verificado.
  3. ``CUTOVER_SPECS`` AUDITADO y COMPLETO para las 191 tablas (PK + cada FK
     funcional → tabla padre). El spec de abajo es un PUNTO DE PARTIDA de las
     entidades núcleo; está INCOMPLETO y debe completarse/validarse antes de correr.

Ejecución (manual, gated):
    SPJ_UUID_CUTOVER_CONFIRMED=1  +  conn explícita  ->  run(conn)

El motor (``backend/infrastructure/db/uuid_cutover.py``) construye mapas
``old_id -> uuid``, reescribe PK+FK, valida conteos y corre ``PRAGMA
foreign_key_check``; cualquier fallo revierte todo (no se permite migración parcial).
"""

from __future__ import annotations

import logging
import os

from backend.infrastructure.db.uuid_cutover import TableSpec, UuidCutover

logger = logging.getLogger("spj.migrations")

# ── Punto de partida del spec (INCOMPLETO — auditar las 191 tablas antes de correr) ──
# Cada entrada: TableSpec(tabla, pk="id", fks={columna_fk: tabla_padre}).
CUTOVER_SPECS: list[TableSpec] = [
    # raíces
    TableSpec("sucursales"),
    TableSpec("productos"),
    TableSpec("clientes"),
    TableSpec("proveedores"),
    TableSpec("usuarios"),
    TableSpec("categorias"),
    # ventas
    TableSpec("ventas", fks={"sucursal_id": "sucursales", "cliente_id": "clientes"}),
    TableSpec("detalles_venta", fks={"venta_id": "ventas", "producto_id": "productos"}),
    # compras
    TableSpec("compras", fks={"sucursal_id": "sucursales", "proveedor_id": "proveedores"}),
    TableSpec("detalles_compra", fks={"compra_id": "compras", "producto_id": "productos"}),
    # QR/contenedores (migración 111)
    TableSpec("contenedores", fks={"proveedor_id": "proveedores",
                                   "sucursal_destino": "sucursales",
                                   "parent_id": "contenedores"}),
    TableSpec("contenedor_productos", fks={"contenedor_id": "contenedores",
                                           "producto_id": "productos"}),
    # caja
    TableSpec("cierres_caja", fks={"sucursal_id": "sucursales"}),
    # TODO: completar las ~178 tablas restantes (inventario, finanzas, delivery,
    #       fidelidad, rrhh, transferencias, batches, tickets, etc.) con sus FKs.
]

SPEC_IS_COMPLETE = False  # poner True solo tras auditar las 191 tablas.


def run(conn):
    if os.environ.get("SPJ_UUID_CUTOVER_CONFIRMED") != "1":
        raise RuntimeError(
            "Migración 200 (corte UUID) es destructiva y gated. "
            "Requiere SPJ_UUID_CUTOVER_CONFIRMED=1, backup verificado y app cerrada."
        )
    if not SPEC_IS_COMPLETE:
        raise RuntimeError(
            "CUTOVER_SPECS está incompleto. Audita las 191 tablas (PK+FK) y pon "
            "SPEC_IS_COMPLETE=True antes de ejecutar el corte."
        )
    logger.warning("[CUTOVER] iniciando corte UUID global sobre %d tablas", len(CUTOVER_SPECS))
    counts = UuidCutover(conn, CUTOVER_SPECS).run()
    logger.warning("[CUTOVER] completado. Filas migradas: %s", counts)
    return counts
