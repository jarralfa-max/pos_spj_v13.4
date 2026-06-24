"""Audit tool — generate UUID-cutover TableSpecs from a live schema.

Introspects a SQLite schema, classifies every table (single-id PK vs
junction/config pk=None) and resolves each ``*_id`` FK column to a parent table
via the convention map below, verifying the parent exists. Emits a Python spec
plus a report of unresolved/ambiguous columns that still need a human decision.

Usage:
    python tools/refactor_control/build_cutover_spec.py --db schema.db
"""

from __future__ import annotations

import argparse
import sqlite3

# Columns that are identifiers but NOT domain FKs (never remapped).
NON_FK_ID_COLUMNS = {
    "operation_id", "event_id", "entity_id", "external_id", "message_id",
    "wa_id", "legacy_id", "meta_phone_id", "pedido_wa_id", "device_id",
    "origin_device_id", "reference_id", "referencia_id", "source_id",
    "registro_id", "run_id", "job_id", "challenge_id", "preference_id",
    "documento_id", "legacy_receta_id", "legacy_receta_componente_id",
    "permiso_id", "rol_id",  # roles/permisos handled as junction config
    "entidad_id", "party_id", "sender_id",  # polimórficos / externos (no FK real)
}

# FK column -> parent table (convention map; verified against the live schema).
FK_PARENT = {
    # productos
    **{c: "productos" for c in (
        "producto_id", "product_id", "producto_base_id", "base_product_id",
        "child_product_id", "component_product_id", "producto_componente_id",
        "producto_compuesto_id", "producto_derivado_id", "producto_padre_id",
        "producto_resultante_id", "producto_venta_id", "source_product_id",
        "output_product_id", "piece_product_id", "yield_product_id",
        "product_source_id", "ingrediente_id", "materia_prima_id",
        "corte_producto_id", "producto_pollo_id", "output_id",
    )},
    # sucursales
    **{c: "sucursales" for c in (
        "sucursal_id", "branch_id", "sucursal_destino_id", "sucursal_origen_id",
        "sucursal_principal_id", "branch_dest_id", "branch_origin_id",
        "dest_branch_id", "origin_branch_id",
    )},
    # clientes
    "cliente_id": "clientes", "customer_id": "clientes",
    # proveedores
    "proveedor_id": "proveedores", "supplier_id": "proveedores",
    # ventas
    "venta_id": "ventas", "sale_id": "ventas", "venta_ref_id": "ventas",
    "sale_item_id": "detalles_venta",
    # compras
    "compra_id": "compras", "compra_global_id": "compras",
    "compra_ref_id": "compras", "compra_pollo_id": "compras",
    "purchase_order_id": "ordenes_compra", "orden_id": "ordenes_compra",
    # usuarios / personal
    "usuario_id": "usuarios", "user_id": "usuarios", "cajero_id": "usuarios",
    "responsable_id": "usuarios", "empleado_id": "personal",
    "personal_id": "personal", "chofer_id": "drivers", "driver_id": "drivers",
    "repartidor_id": "drivers",
    # contenedores
    "contenedor_id": "contenedores", "parent_id": "contenedores",
    # batches / lotes
    **{c: "batches" for c in (
        "batch_id", "batch_padre_id", "parent_batch_id", "root_batch_id",
    )},
    **{c: "lotes" for c in (
        "lote_id", "lote_hijo_id", "lote_origen_id", "lote_padre_id",
    )},
    # recetas
    "receta_id": "recetas", "recipe_id": "product_recipes",
    "parent_recipe_id": "product_recipes",
    # otros dominios
    "cotizacion_id": "cotizaciones", "pedido_id": "delivery_orders",
    "pedido_activo_id": "delivery_orders", "transfer_id": "transferencias",
    "transferencia_id": "transferencias", "asset_id": "assets",
    "activo_id": "activos", "caja_id": "cajas", "corte_id": "cierres_caja",
    "cut_id": "cierres_caja", "financial_document_id": "financial_documents",
    "journal_entry_id": "journal_entries", "gasto_id": "gastos",
    "categoria_id": "categorias",
    "plantilla_id": "plantillas_compra", "lista_id": "listas_precio",
    # resueltas en 2da pasada de auditoría
    "ap_id": "accounts_payable", "ar_id": "accounts_receivable",
    "devolucion_id": "devoluciones", "treasury_movement_id": "treasury_movements",
    "payment_id": "payments", "pago_cobro_id": "pagos_cobros",
    "produccion_id": "producciones", "mision_id": "growth_misiones",
    "pr_id": "purchase_requests", "recepcion_id": "recepciones",
}

# Columnas FK dependientes del contexto (significan tablas distintas según la
# tabla): requieren override por-tabla manual, NO un mapeo global.
CONTEXT_DEPENDENT = {
    "parent_id", "padre_id", "origen_id", "destino_id", "target_id",
    "tercero_id", "partner_id", "source_id", "transformation_group_id",
    "transformation_id", "turno_id", "turno_rol_id", "tarjeta_id",
    "operacion_id", "bib_id", "goal_id", "ticket_id", "paquete_id",
}

CONFIG_PKS = {"clave", "key", "numero"}


def build(db_path: str):
    conn = sqlite3.connect(db_path)
    tables = sorted(
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        if r[0] not in ("schema_migrations",)
    )
    existing = set(tables)

    specs: list[str] = []
    unresolved: dict[str, list[str]] = {}
    junctions: list[str] = []

    for t in tables:
        cols = conn.execute(f'PRAGMA table_info("{t}")').fetchall()
        pk_cols = [c[1] for c in sorted(cols, key=lambda c: c[5]) if c[5]]
        single_id_pk = pk_cols == ["id"]
        is_config_pk = bool(pk_cols) and all(c in CONFIG_PKS for c in pk_cols)
        pk = "id" if single_id_pk else None
        if not single_id_pk and (len(pk_cols) > 1 or is_config_pk or not pk_cols):
            junctions.append(t)

        fks: dict[str, str] = {}
        for c in cols:
            name = c[1]
            if not name.endswith("_id") or name in NON_FK_ID_COLUMNS:
                continue
            if name == "id":
                continue
            parent = FK_PARENT.get(name)
            if parent and parent in existing:
                fks[name] = parent
            elif name in CONTEXT_DEPENDENT:
                unresolved.setdefault(t, []).append(f"{name} [context — override por-tabla]")
            else:
                unresolved.setdefault(t, []).append(
                    f"{name} -> {parent or '??'}{' (parent missing)' if parent and parent not in existing else ''}"
                )

        fks_repr = ", ".join(f'"{k}": "{v}"' for k, v in fks.items())
        pk_repr = '"id"' if pk == "id" else "None"
        body = f'TableSpec("{t}", pk={pk_repr}'
        if fks_repr:
            body += f", fks={{{fks_repr}}}"
        body += ")"
        specs.append(body)

    return specs, unresolved, junctions, len(tables)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    args = ap.parse_args()
    specs, unresolved, junctions, total = build(args.db)
    print(f"# {total} tablas | {len(junctions)} junction/config (pk=None) | "
          f"{len(unresolved)} con FK no resueltas\n")
    print("CUTOVER_SPECS = [")
    for s in specs:
        print(f"    {s},")
    print("]\n")
    print(f"# === {sum(len(v) for v in unresolved.values())} FK NO RESUELTAS (revisar) ===")
    for t, items in sorted(unresolved.items()):
        print(f"#   {t}: {', '.join(items)}")


if __name__ == "__main__":
    main()
