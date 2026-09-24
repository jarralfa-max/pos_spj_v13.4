"""263 — SUP-6: los proveedores heredados entran al maestro canónico.

QUÉ ARREGLA, MEDIDO
--------------------
Había DOS buscadores de proveedores contra DOS tablas, con resultados disjuntos:
el módulo de Proveedores leía `supplier_master` y Compras leía `proveedores`. Y
nada en el código de producción escribe en `proveedores`. Consecuencia: un
proveedor dado de alta y aprobado hoy **no se podía elegir al crear una compra**,
y los proveedores heredados no aparecían en el módulo de Proveedores.

La migración 119 ya lo dejó escrito: "los lectores migran a este maestro en
SUP-6". Esto es SUP-6.

POR QUÉ SE CONSERVA EL id
--------------------------
`purchase_orders`, `direct_purchases`, `compras`, `recepciones`, `goods_receipts`,
`supplier_invoices`, `contenedores` y las cotizaciones guardan `supplier_id`
apuntando a `proveedores.id`. Copiar con un id nuevo dejaría todos esos documentos
sin proveedor resoluble. `proveedores.id` ya es TEXT/UUID desde el corte de
identidad, así que conservarlo NO reintroduce identidades heredadas de otro tipo:
es el MISMO uuid, en la tabla que ahora manda.

LO QUE NO PUEDE PERDERSE: LOS BLOQUEOS
---------------------------------------
`proveedores` marca el bloqueo con dos columnas (`compras_habilitadas`,
`bloqueado_financiero`) y el maestro lo hace con filas en `supplier_blocks`.
Copiar sólo los datos del proveedor DESBLOQUEARÍA EN SILENCIO a quien estaba
bloqueado, que es el peor resultado posible de esta migración: pasarían a ser
seleccionables para comprar. Por eso cada marca se traduce a su bloqueo
equivalente:

    compras_habilitadas = 0   ->  PURCHASING_BLOCK
    bloqueado_financiero = 1  ->  PAYMENT_BLOCK

Las dos columnas son opcionales (las añadió la migración 178); si no están, no
hay bloqueo que traducir y no se inventa ninguno.

ESTADO
------
`activo = 0` se copia como `INACTIVE`, no como `REJECTED`: rechazado significa
que se evaluó y se descartó, y eso nadie lo capturó. `activo = 1` entra como
`ACTIVE` porque en el modelo heredado no existía un paso de aprobación: exigirles
volver a aprobarse dejaría a Compras sin ningún proveedor el día del corte.

IDEMPOTENTE: cada fila se salta si su id ya está en el maestro, así que volver a
correrla no duplica ni pisa nada de lo capturado después.
"""

from __future__ import annotations

import logging
import re
import unicodedata

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.263")

LEGACY_TABLE = "proveedores"
MASTER_TABLE = "supplier_master"
BLOCKS_TABLE = "supplier_blocks"

#: Usuario al que se atribuyen las filas creadas por el corte. No se usa un
#: usuario real ni se inventa uno: la auditoría tiene que poder distinguir lo que
#: capturó una persona de lo que trajo una migración.
MIGRATION_ACTOR = "migration:263"


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _normalized(value: str) -> str:
    """Idéntica a `supplier_repository.normalize_name` (pliega acentos y quita
    todo lo que no sea letra o dígito). Si difiriera, los proveedores migrados
    no se encontrarían por el mismo texto que los capturados en el módulo."""
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", text)


def _next_sequence(conn) -> int:
    """Continúa la numeración `PRV-NNNNNN` existente.

    Mismo cálculo que `SupplierRepository.next_code`, para que los códigos que
    genere la aplicación después del corte no choquen con los de aquí.
    """
    fila = conn.execute(
        f"SELECT supplier_code FROM {MASTER_TABLE}"
        " WHERE supplier_code LIKE 'PRV-%'"
        " ORDER BY CAST(SUBSTR(supplier_code, 5) AS INTEGER) DESC LIMIT 1"
    ).fetchone()
    if not fila or not fila[0]:
        return 1
    try:
        return int(str(fila[0]).split("-")[1]) + 1
    except (IndexError, ValueError):
        return 1


def _block(conn, supplier_id: str, block_type: str, reason: str, when: str) -> None:
    conn.execute(
        f"INSERT INTO {BLOCKS_TABLE} (id, supplier_id, block_type, reason,"
        " effective_at, created_by_user_id, operation_id, active)"
        " VALUES (?,?,?,?,?,?,?,1)",
        (new_uuid(), supplier_id, block_type, reason, when, MIGRATION_ACTOR,
         new_uuid()))


def run(conn) -> None:
    if not _table_exists(conn, LEGACY_TABLE):
        logger.info("263: %s no existe (instalación nueva); nada que migrar.",
                    LEGACY_TABLE)
        return
    if not _table_exists(conn, MASTER_TABLE):
        logger.info("263: %s no existe todavía; la 119 no ha corrido.", MASTER_TABLE)
        return

    legacy_cols = _columns(conn, LEGACY_TABLE)
    if "id" not in legacy_cols or "nombre" not in legacy_cols:
        logger.warning("263: %s no tiene la forma esperada; se omite.", LEGACY_TABLE)
        return

    opcionales = [c for c in ("rfc", "activo", "fecha_alta", "compras_habilitadas",
                              "bloqueado_financiero") if c in legacy_cols]
    seleccion = ", ".join(["id", "nombre", *opcionales])
    filas = conn.execute(f"SELECT {seleccion} FROM {LEGACY_TABLE}").fetchall()
    if not filas:
        logger.info("263: %s está vacía; nada que migrar.", LEGACY_TABLE)
        return

    ya_estan = {str(r[0]) for r in
                conn.execute(f"SELECT id FROM {MASTER_TABLE}").fetchall()}
    hay_bloqueos = _table_exists(conn, BLOCKS_TABLE)
    secuencia = _next_sequence(conn)
    campos = ["id", "nombre", *opcionales]
    copiados = bloqueados = 0

    for fila in filas:
        datos = dict(zip(campos, fila))
        supplier_id = str(datos["id"] or "").strip()
        if not supplier_id or supplier_id in ya_estan:
            continue
        nombre = str(datos.get("nombre") or "").strip()
        if not nombre:
            # `legal_name` es NOT NULL y un proveedor sin nombre no se puede
            # mostrar ni elegir. Se deja fuera y se dice cuál.
            logger.warning("263: proveedor %s sin nombre; no se migra.", supplier_id)
            continue

        activo = datos.get("activo", 1)
        activo = 1 if activo is None else int(activo)
        alta = str(datos.get("fecha_alta") or "").strip()
        conn.execute(
            f"INSERT INTO {MASTER_TABLE} (id, supplier_code, legal_name, trade_name,"
            " normalized_name, tax_identifier, status, has_history, active,"
            " created_by_user_id, created_at, updated_at)"
            " VALUES (?,?,?,'',?,?,?,1,?,?,COALESCE(NULLIF(?,''), datetime('now')),"
            " datetime('now'))",
            (supplier_id, f"PRV-{secuencia:06d}", nombre, _normalized(nombre),
             (str(datos.get("rfc") or "").strip().upper() or None),
             "ACTIVE" if activo else "INACTIVE", 1 if activo else 0,
             MIGRATION_ACTOR, alta))
        secuencia += 1
        copiados += 1
        ya_estan.add(supplier_id)

        if not hay_bloqueos:
            continue
        cuando = alta or "1970-01-01 00:00:00"
        compras = datos.get("compras_habilitadas", 1)
        if "compras_habilitadas" in datos and compras is not None and not int(compras):
            _block(conn, supplier_id, "PURCHASING_BLOCK",
                   "Migración 263: venía con las compras deshabilitadas", cuando)
            bloqueados += 1
        financiero = datos.get("bloqueado_financiero", 0)
        if "bloqueado_financiero" in datos and financiero and int(financiero):
            _block(conn, supplier_id, "PAYMENT_BLOCK",
                   "Migración 263: venía con bloqueo financiero", cuando)
            bloqueados += 1

    conn.commit()
    logger.info("263: %s proveedores heredados copiados al maestro (%s bloqueos "
                "preservados).", copiados, bloqueados)


up = run
