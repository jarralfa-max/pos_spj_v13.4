#!/usr/bin/env python3
# scripts/seed_demo.py — SPJ POS v13.4 (UUID-only)
"""
Pobla la BD con datos realistas de una polleria/carniceria.
Ideal para demostraciones y training de cajeros.

Uso:
    python scripts/seed_demo.py                    # BD default data/spj.db
    python scripts/seed_demo.py --db data/demo.db  # BD especifica
    python scripts/seed_demo.py --clear            # Limpia antes de sembrar

Identity: todos los IDs de entidades son UUIDv7 generados por backend.shared.ids.new_uuid().
No se usa lastrowid, AUTOINCREMENT ni enteros como identidad funcional.
"""
import sys, os, sqlite3, argparse, hashlib, random
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.shared.ids import new_uuid

# ── Datos de la empresa demo ────────────────────────────────────────────────
EMPRESA = {
    "nombre":         "Pollos y Carnes Don José",
    "rfc":            "XAXX010101000",
    "telefono":       "442-123-4567",
    "direccion":      "Av. Constitución 123, Querétaro, Qro.",
    "regimen_fiscal": "626",
    "cp":             "76000",
}

PRODUCTOS_CARNE = [
    # (nombre, precio_kg, precio_compra, stock_inicial, stock_min, categoria)
    ("Pollo Entero",           89.0,  55.0, 80.0, 20.0, "Pollo"),
    ("Pechuga Sin Hueso",     115.0,  70.0, 50.0, 15.0, "Pollo"),
    ("Pierna con Muslo",       75.0,  45.0, 60.0, 15.0, "Pollo"),
    ("Alas de Pollo",          72.0,  42.0, 40.0, 10.0, "Pollo"),
    ("Filete de Pechuga",     125.0,  78.0, 30.0, 10.0, "Pollo"),
    ("Milanesa de Pollo",     110.0,  68.0, 25.0,  8.0, "Pollo"),
    ("Molida de Pollo",        85.0,  52.0, 35.0, 10.0, "Pollo"),
    ("Caldo de Pollo (hueso)", 45.0,  20.0, 40.0, 10.0, "Pollo"),
    ("Lomo de Cerdo",         120.0,  75.0, 30.0,  8.0, "Cerdo"),
    ("Costilla de Cerdo",      95.0,  58.0, 25.0,  5.0, "Cerdo"),
    ("Chuleta de Cerdo",      105.0,  65.0, 20.0,  5.0, "Cerdo"),
    ("Molida de Cerdo",        92.0,  56.0, 25.0,  5.0, "Cerdo"),
    ("Bistec de Res",         185.0, 120.0, 20.0,  5.0, "Res"),
    ("Molida de Res",         155.0,  98.0, 25.0,  5.0, "Res"),
    ("Arrachera",             245.0, 160.0, 10.0,  3.0, "Res"),
    ("Surtido Familiar 1kg",   95.0,  58.0,  0.0,  0.0, "Paquetes"),
    ("Parrillero 2kg",        185.0, 115.0,  0.0,  0.0, "Paquetes"),
    ("Económico 500g",         45.0,  28.0,  0.0,  0.0, "Paquetes"),
    ("Limones (kg)",           35.0,  18.0, 20.0,  5.0, "Complementos"),
    ("Salsa Valentina",        22.0,  12.0, 30.0, 10.0, "Complementos"),
]

CLIENTES_DEMO = [
    ("Juan García López",      "442-111-2222", "GALJ800101ABC"),
    ("María Rodríguez Pérez",  "442-333-4444", "ROPM750215XYZ"),
    ("Restaurante El Fogón",   "442-555-6666", "REFO900301DEF"),
    ("Tacos Los Compadres",    "442-777-8888", "TALC850620GHI"),
]

USUARIOS_DEMO = [
    ("admin",    "Administrador",     "admin",   "Admin2024!"),
    ("cajero1",  "Ana Martínez",      "cajero",  "Cajero123!"),
    ("cajero2",  "Luis Hernández",    "cajero",  "Cajero456!"),
    ("gerente",  "Roberto Sánchez",   "gerente", "Gerente789!"),
]

PAQUETES_DEMO = [
    ("Surtido Familiar 1kg", 1.0, 95.0,
     [("Pollo Entero", 0.50), ("Pierna con Muslo", 0.30), ("Alas de Pollo", 0.20)]),
    ("Parrillero 2kg", 2.0, 185.0,
     [("Arrachera", 0.40), ("Costilla de Cerdo", 0.35), ("Chuleta de Cerdo", 0.25)]),
    ("Económico 500g", 0.5, 45.0,
     [("Molida de Pollo", 0.60), ("Molida de Cerdo", 0.40)]),
]

# ── Sucursal demo fija ───────────────────────────────────────────────────────
BRANCH_UUID = "01900000-0000-7000-8000-000000000011"


def _upsert_product(conn, nombre, precio, precio_compra, stock, stock_min, cat) -> str:
    """Insert or fetch product UUID."""
    row = conn.execute("SELECT id FROM productos WHERE LOWER(TRIM(nombre))=LOWER(TRIM(?))", (nombre,)).fetchone()
    if row:
        return str(row[0])
    pid = new_uuid()
    try:
        conn.execute(
            "INSERT INTO productos (id, nombre, precio, precio_compra, existencia, "
            "stock_minimo, unidad, categoria, activo) VALUES (?,?,?,?,?,?,'kg',?,1)",
            (pid, nombre, precio, precio_compra, stock, stock_min, cat),
        )
    except Exception as e:
        print(f"  ⚠ Producto {nombre}: {e}")
        return ""
    return pid


def _upsert_client(conn, nombre, telefono, rfc, puntos) -> str:
    row = conn.execute("SELECT id FROM clientes WHERE nombre=?", (nombre,)).fetchone()
    if row:
        return str(row[0])
    cid = new_uuid()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO clientes (id, nombre, telefono, rfc, puntos, activo) "
            "VALUES (?,?,?,?,?,1)",
            (cid, nombre, telefono, rfc, puntos),
        )
    except Exception as e:
        print(f"  ⚠ Cliente {nombre}: {e}")
        return ""
    return cid


def seed(db_path: str, clear: bool = False):
    print(f"\n{'='*55}")
    print(f"  SPJ POS v13.4 — Seed de datos demo (UUID-only)")
    print(f"  BD: {db_path}")
    print(f"{'='*55}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")

    if clear:
        print("⚠ Limpiando tablas...")
        for t in ("ventas", "detalles_venta", "movimientos_caja", "inventory_movements",
                  "inventory_stock", "clientes", "productos", "usuarios",
                  "paquetes", "paquetes_componentes", "lotes", "delivery_orders"):
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.commit()

    # ── Migraciones ──────────────────────────────────────────────────────────
    print("→ Aplicando migraciones...")
    try:
        from migrations.engine import aplicar_migraciones
        aplicar_migraciones(conn)
        print("  ✓ Migraciones OK")
    except Exception as e:
        print(f"  ⚠ Migraciones: {e}")

    # ── Configuración empresa ─────────────────────────────────────────────────
    print("→ Configurando empresa...")
    for k, v in EMPRESA.items():
        try:
            conn.execute(
                "INSERT OR REPLACE INTO configuraciones(clave,valor) VALUES(?,?)",
                (f"empresa_{k}", v),
            )
        except Exception:
            pass
    conn.commit()

    # ── Sucursal ──────────────────────────────────────────────────────────────
    try:
        conn.execute(
            "INSERT OR IGNORE INTO sucursales (id, nombre, direccion, activo) "
            "VALUES (?,?,?,1)",
            (BRANCH_UUID, "Sucursal Principal", EMPRESA["direccion"]),
        )
        conn.commit()
    except Exception:
        pass

    # ── Productos ─────────────────────────────────────────────────────────────
    print("→ Insertando productos...")
    prod_ids: dict[str, str] = {}  # nombre → uuid
    for nombre, precio, precio_compra, stock, stock_min, cat in PRODUCTOS_CARNE:
        pid = _upsert_product(conn, nombre, precio, precio_compra, stock, stock_min, cat)
        if pid:
            prod_ids[nombre] = pid
    conn.commit()
    print(f"  ✓ {len(prod_ids)} productos")

    # ── Inventario inicial (inventory_stock) ──────────────────────────────────
    print("→ Cargando stock inicial...")
    for nombre, precio, precio_compra, stock, stock_min, cat in PRODUCTOS_CARNE:
        pid = prod_ids.get(nombre)
        if not pid or stock <= 0:
            continue
        try:
            conn.execute(
                "INSERT INTO inventory_stock (product_id, branch_id, quantity, unit, updated_at) "
                "VALUES (?,?,?,'kg',datetime('now')) "
                "ON CONFLICT(product_id, branch_id) DO UPDATE SET quantity=excluded.quantity",
                (pid, BRANCH_UUID, stock),
            )
        except Exception:
            pass
    conn.commit()

    # ── Lotes con fechas de caducidad ─────────────────────────────────────────
    print("→ Creando lotes de inventario...")
    lote_count = 0
    for nombre, precio, precio_compra, stock, _, cat in PRODUCTOS_CARNE:
        if stock <= 0 or cat in ("Paquetes", "Complementos"):
            continue
        pid = prod_ids.get(nombre)
        if not pid:
            continue
        for i, dias_cad in enumerate([5, 10, 20]):
            peso = stock / 2 if i == 0 else stock / 4
            fecha_cad = (date.today() + timedelta(days=dias_cad)).isoformat()
            try:
                lote_id = new_uuid()
                conn.execute(
                    "INSERT OR IGNORE INTO lotes "
                    "(id, producto_id, numero_lote, peso_inicial_kg, peso_actual_kg, "
                    "costo_kg, fecha_caducidad, fecha_recepcion, sucursal_id, estado) "
                    "VALUES (?,?,?,?,?,?,?,date('now'),?,'activo')",
                    (lote_id, pid,
                     f"L{datetime.now().strftime('%Y%m%d')}-{pid[:6]}-{i+1:02d}",
                     peso, peso, precio_compra, fecha_cad, BRANCH_UUID),
                )
                lote_count += 1
            except Exception:
                pass
    conn.commit()
    print(f"  ✓ {lote_count} lotes")

    # ── Clientes ──────────────────────────────────────────────────────────────
    print("→ Insertando clientes...")
    cli_ids: list[str] = []
    for nombre, tel, rfc in CLIENTES_DEMO:
        cid = _upsert_client(conn, nombre, tel, rfc, random.randint(0, 500))
        if cid:
            cli_ids.append(cid)
    conn.commit()
    print(f"  ✓ {len(cli_ids)} clientes")

    # ── Usuarios ──────────────────────────────────────────────────────────────
    print("→ Insertando usuarios...")
    usr_count = 0
    for usuario, nombre, rol, password in USUARIOS_DEMO:
        hashed = hashlib.sha256(password.encode()).hexdigest()
        try:
            uid = new_uuid()
            conn.execute(
                "INSERT OR IGNORE INTO usuarios (id, usuario, nombre, contrasena, rol, activo) "
                "VALUES (?,?,?,?,?,1)",
                (uid, usuario, nombre, hashed, rol),
            )
            usr_count += 1
        except Exception as e:
            print(f"  ⚠ Usuario {usuario}: {e}")
    conn.commit()
    print(f"  ✓ {usr_count} usuarios")

    # ── Historial de ventas (últimos 30 días) ─────────────────────────────────
    print("→ Generando historial de ventas (30 días)...")
    venta_count = 0
    prods_vendibles = [
        (n, pid) for n, pid in prod_ids.items()
        if "Paquete" not in n and "Surtido" not in n
        and "Parrillero" not in n and "Económico" not in n
    ]
    formas = ["Efectivo"] * 6 + ["Tarjeta"] * 3 + ["Transferencia"]
    for dias_atras in range(30, 0, -1):
        fecha = datetime.now() - timedelta(days=dias_atras)
        num_ventas = random.randint(8, 25)
        for _ in range(num_ventas):
            try:
                cliente_id = random.choice(cli_ids + [None, None])
                forma = random.choice(formas)
                n_items = random.randint(1, 4)
                items = random.sample(prods_vendibles, min(n_items, len(prods_vendibles)))
                subtotal = 0.0
                venta_id = new_uuid()
                op_id = new_uuid()
                folio = f"V{venta_count+1:06d}"
                conn.execute(
                    "INSERT INTO ventas "
                    "(id, folio, sucursal_id, usuario, cliente_id, subtotal, total, "
                    "forma_pago, efectivo_recibido, estado, operation_id, fecha) "
                    "VALUES (?,?,?,?,?,0,0,?,0,'completada',?,?)",
                    (venta_id, folio, BRANCH_UUID, "cajero1", cliente_id,
                     forma, op_id, fecha.strftime("%Y-%m-%d %H:%M:%S")),
                )
                for prod_nombre, pid in items:
                    qty = round(random.uniform(0.5, 3.0), 3)
                    precio = next(p for n, p, *_ in PRODUCTOS_CARNE if n == prod_nombre)
                    sub = round(qty * precio, 2)
                    subtotal += sub
                    det_id = new_uuid()
                    conn.execute(
                        "INSERT INTO detalles_venta "
                        "(id, venta_id, producto_id, cantidad, precio_unitario, subtotal) "
                        "VALUES (?,?,?,?,?,?)",
                        (det_id, venta_id, pid, qty, precio, sub),
                    )
                recibido = subtotal * random.uniform(1.0, 1.5)
                conn.execute(
                    "UPDATE ventas SET subtotal=?,total=?,efectivo_recibido=? WHERE id=?",
                    (subtotal, subtotal, recibido, venta_id),
                )
                try:
                    conn.execute(
                        "INSERT INTO movimientos_caja "
                        "(tipo, monto, concepto, forma_pago, usuario, fecha) "
                        "VALUES ('INGRESO',?,?,?,'cajero1',?)",
                        (subtotal, f"Venta {folio}", forma,
                         fecha.strftime("%Y-%m-%d %H:%M:%S")),
                    )
                except Exception:
                    pass
                venta_count += 1
            except Exception:
                pass
    conn.commit()
    print(f"  ✓ {venta_count} ventas históricas")

    # ── Resumen ───────────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"  ✓ Seed completado exitosamente")
    print(f"{'='*55}")
    print(f"  Productos:       {len(prod_ids)}")
    print(f"  Clientes:        {len(cli_ids)}")
    print(f"  Usuarios:        {usr_count}")
    print(f"  Lotes:           {lote_count}")
    print(f"  Ventas (30d):    {venta_count}")
    print(f"\n  Credenciales de acceso:")
    for usuario, _, rol, password in USUARIOS_DEMO:
        print(f"    {usuario:15s} / {password:15s}  [{rol}]")
    print(f"{'='*55}\n")

    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS bot_sessions "
            "(numero TEXT PRIMARY KEY, datos TEXT, "
            "ultima_actividad DATETIME DEFAULT (datetime('now')))"
        )
        conn.commit()
    except Exception:
        pass
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo data for SPJ POS")
    parser.add_argument("--db", default="data/spj.db", help="SQLite DB path")
    parser.add_argument("--clear", action="store_true", help="Clear tables before seeding")
    args = parser.parse_args()
    seed(args.db, clear=args.clear)
