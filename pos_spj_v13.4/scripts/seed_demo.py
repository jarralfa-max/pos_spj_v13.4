
#!/usr/bin/env python3
# scripts/seed_demo.py — SPJ POS v10
"""
Pobla la BD con datos realistas de una polleria/carniceria.
Ideal para demostraciones y training de cajeros.

Uso:
    python scripts/seed_demo.py                    # BD default data/spj.db
    python scripts/seed_demo.py --db data/demo.db  # BD especifica
    python scripts/seed_demo.py --clear            # Limpia antes de sembrar
"""
import sys, os, sqlite3, argparse, hashlib, random
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    ("Pollo Entero",          89.0,  55.0, 80.0, 20.0, "Pollo"),
    ("Pechuga Sin Hueso",    115.0,  70.0, 50.0, 15.0, "Pollo"),
    ("Pierna con Muslo",      75.0,  45.0, 60.0, 15.0, "Pollo"),
    ("Alas de Pollo",         72.0,  42.0, 40.0, 10.0, "Pollo"),
    ("Filete de Pechuga",    125.0,  78.0, 30.0, 10.0, "Pollo"),
    ("Milanesa de Pollo",    110.0,  68.0, 25.0,  8.0, "Pollo"),
    ("Molida de Pollo",       85.0,  52.0, 35.0, 10.0, "Pollo"),
    ("Caldo de Pollo (hueso)",45.0,  20.0, 40.0, 10.0, "Pollo"),
    # Cerdo
    ("Lomo de Cerdo",        120.0,  75.0, 30.0,  8.0, "Cerdo"),
    ("Costilla de Cerdo",     95.0,  58.0, 25.0,  5.0, "Cerdo"),
    ("Chuleta de Cerdo",     105.0,  65.0, 20.0,  5.0, "Cerdo"),
    ("Molida de Cerdo",       92.0,  56.0, 25.0,  5.0, "Cerdo"),
    # Res
    ("Bistec de Res",        185.0, 120.0, 20.0,  5.0, "Res"),
    ("Molida de Res",        155.0,  98.0, 25.0,  5.0, "Res"),
    ("Arrachera",            245.0, 160.0, 10.0,  3.0, "Res"),
    # Empaquetados
    ("Surtido Familiar 1kg",  95.0,  58.0,  0.0,  0.0, "Paquetes"),
    ("Parrillero 2kg",       185.0, 115.0,  0.0,  0.0, "Paquetes"),
    ("Económico 500g",        45.0,  28.0,  0.0,  0.0, "Paquetes"),
    # Complementos
    ("Limones (kg)",          35.0,  18.0, 20.0,  5.0, "Complementos"),
    ("Salsa Valentina",        22.0,  12.0, 30.0, 10.0, "Complementos"),
]

CLIENTES_DEMO = [
    ("Juan García López",      "442-111-2222", "GALJ800101ABC"),
    ("María Rodríguez Pérez",  "442-333-4444", "ROPM750215XYZ"),
    ("Restaurante El Fogón",   "442-555-6666", "REFO900301DEF"),
    ("Tacos Los Compadres",    "442-777-8888", "TALC850620GHI"),
    ("Carnicería San Miguel",  "442-999-0000", "CASM700101JKL"),
    ("Ana Martínez Torres",    "442-121-3434", None),
    ("Pedro Sánchez Ruiz",     "442-565-7878", None),
    ("Cocina La Abuela",       "442-909-1212", "COAB880430MNO"),
]

USUARIOS_DEMO = [
    # (usuario, nombre, rol, password)
    ("admin",    "Administrador",     "Administrador", "Admin2024!"),
    ("cajero1",  "Carlos Morales",    "Cajero",        "Cajero123"),
    ("cajero2",  "Diana Fuentes",     "Cajero",        "Cajero123"),
    ("gerente",  "Roberto González",  "Gerente",       "Gerente123"),
    ("repartidor1", "Miguel Ángel H.","Repartidor",    "Reparto123"),
]

PAQUETES_DEMO = [
    # (nombre_paquete, peso_kg, precio, [(nombre_corte, porcentaje), ...])
    ("Surtido Familiar 1kg", 1.0, 95.0, [
        ("Pechuga Sin Hueso", 40.0),
        ("Pierna con Muslo",  30.0),
        ("Alas de Pollo",     30.0),
    ]),
    ("Parrillero 2kg", 2.0, 185.0, [
        ("Lomo de Cerdo",    35.0),
        ("Costilla de Cerdo",35.0),
        ("Bistec de Res",    30.0),
    ]),
    ("Económico 500g", 0.5, 45.0, [
        ("Molida de Pollo",   60.0),
        ("Caldo de Pollo (hueso)", 40.0),
    ]),
]


def seed(db_path: str, clear: bool = False):
    print(f"\n{'='*55}")
    print(f"  SPJ POS v10 — Seed de datos demo")
    print(f"  BD: {db_path}")
    print(f"{'='*55}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")

    if clear:
        print("⚠ Limpiando tablas...")
        for t in ("ventas","detalles_venta","movimientos_caja","movimientos_inventario",
                  "clientes","productos","usuarios","paquetes","paquetes_componentes",
                  "lotes","delivery_orders"):
            try: conn.execute(f"DELETE FROM {t}")
            except Exception: pass
        conn.commit()

    # ── Aplicar migraciones ─────────────────────────────────────────────
    print("→ Aplicando migraciones...")
    try:
        from migrations.engine import aplicar_migraciones
        aplicar_migraciones(conn)
        print("  ✓ Migraciones OK")
    except Exception as e:
        print(f"  ⚠ Migraciones: {e}")

    # ── Configuración empresa ───────────────────────────────────────────
    print("→ Configurando empresa...")
    for k, v in EMPRESA.items():
        try:
            conn.execute("INSERT OR REPLACE INTO configuraciones(clave,valor) VALUES(?,?)",
                         (f"empresa_{k}", v))
        except Exception: pass
    conn.commit()

    # ── Productos ───────────────────────────────────────────────────────
    print("→ Insertando productos...")
    prod_ids = {}
    for nombre, precio, precio_compra, stock, stock_min, cat in PRODUCTOS_CARNE:
        try:
            pid = conn.execute("""
                INSERT OR IGNORE INTO productos
                (nombre, precio, precio_compra, existencia, stock_minimo, unidad, categoria, activo)
                VALUES(?,?,?,?,?,'kg',?,1)""",
                (nombre, precio, precio_compra, stock, stock_min, cat)).lastrowid
            if not pid:
                pid = conn.execute("SELECT id FROM productos WHERE nombre=?", (nombre,)).fetchone()[0]
            prod_ids[nombre] = pid
        except Exception as e:
            print(f"  ⚠ Producto {nombre}: {e}")
    conn.commit()
    print(f"  ✓ {len(prod_ids)} productos")

    # ── Lotes con fechas de caducidad ───────────────────────────────────
    print("→ Creando lotes de inventario...")
    lote_count = 0
    for nombre, precio, precio_compra, stock, _, cat in PRODUCTOS_CARNE:
        if stock <= 0 or cat == "Paquetes" or cat == "Complementos":
            continue
        pid = prod_ids.get(nombre)
        if not pid: continue
        # 2-3 lotes por producto con diferentes fechas de caducidad
        for i, dias_cad in enumerate([5, 10, 20]):
            peso = stock / 2 if i == 0 else stock / 4
            fecha_cad = (date.today() + timedelta(days=dias_cad)).isoformat()
            try:
                conn.execute("""INSERT INTO lotes
                    (producto_id, numero_lote, peso_inicial_kg, peso_actual_kg,
                     costo_kg, fecha_caducidad, fecha_recepcion, sucursal_id, estado)
                    VALUES(?,?,?,?,?,?,date('now'),1,'activo')""",
                    (pid, f"L{datetime.now().strftime('%Y%m%d')}-{pid:03d}-{i+1:02d}",
                     peso, peso, precio_compra, fecha_cad))
                lote_count += 1
            except Exception: pass
    conn.commit()
    print(f"  ✓ {lote_count} lotes")

    # ── Clientes ────────────────────────────────────────────────────────
    print("→ Insertando clientes...")
    cli_ids = []
    for nombre, tel, rfc in CLIENTES_DEMO:
        try:
            cid = conn.execute("""
                INSERT OR IGNORE INTO clientes(nombre, telefono, rfc, puntos, activo)
                VALUES(?,?,?,?,1)""",
                (nombre, tel, rfc, random.randint(0, 500))).lastrowid
            if not cid:
                cid = conn.execute("SELECT id FROM clientes WHERE nombre=?", (nombre,)).fetchone()[0]
            cli_ids.append(cid)
        except Exception as e:
            print(f"  ⚠ Cliente {nombre}: {e}")
    conn.commit()
    print(f"  ✓ {len(cli_ids)} clientes")

    # ── Usuarios ────────────────────────────────────────────────────────
    print("→ Insertando usuarios...")
    usr_count = 0
    for usuario, nombre, rol, password in USUARIOS_DEMO:
        try:
            import bcrypt
            hashed = __import__('hashlib').sha256(password.encode()).hexdigest() if not bcrypt else bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        except ImportError:
            hashed = hashlib.sha256(password.encode()).hexdigest()
        try:
            conn.execute("""
                INSERT OR IGNORE INTO usuarios(usuario, nombre, contrasena, rol, activo)
                VALUES(?,?,?,?,1)""", (usuario, nombre, hashed, rol))
            usr_count += 1
        except Exception as e:
            print(f"  ⚠ Usuario {usuario}: {e}")
    conn.commit()
    print(f"  ✓ {usr_count} usuarios (contraseñas en requirements)")

    # ── Paquetes ────────────────────────────────────────────────────────
    print("→ Creando paquetes/surtidos...")
    pkg_count = 0
    for pkg_nombre, peso, precio, componentes in PAQUETES_DEMO:
        pkg_prod_id = prod_ids.get(pkg_nombre)
        if not pkg_prod_id:
            continue
        try:
            conn.execute("UPDATE productos SET precio=? WHERE id=?", (precio, pkg_prod_id))
            pid = conn.execute("""
                INSERT OR REPLACE INTO paquetes
                (producto_id, nombre, peso_total_kg, precio, activo)
                VALUES(?,?,?,?,1)""",
                (pkg_prod_id, pkg_nombre, peso, precio)).lastrowid
            conn.execute("DELETE FROM paquetes_componentes WHERE paquete_id=?", (pid,))
            for corte_nombre, pct in componentes:
                corte_id = prod_ids.get(corte_nombre)
                if corte_id:
                    conn.execute("""INSERT INTO paquetes_componentes
                        (paquete_id, corte_producto_id, porcentaje) VALUES(?,?,?)""",
                        (pid, corte_id, pct))
            pkg_count += 1
        except Exception as e:
            print(f"  ⚠ Paquete {pkg_nombre}: {e}")
    conn.commit()
    print(f"  ✓ {pkg_count} paquetes")

    # ── Historial de ventas (últimos 30 días) ───────────────────────────
    print("→ Generando historial de ventas (30 días)...")
    venta_count = 0
    prods_vendibles = [(n, pid) for n, pid in prod_ids.items()
                       if "Paquete" not in n and "Surtido" not in n and "Parrillero" not in n and "Económico" not in n]
    formas = ["Efectivo"] * 6 + ["Tarjeta"] * 3 + ["Transferencia"]
    for dias_atras in range(30, 0, -1):
        fecha = datetime.now() - timedelta(days=dias_atras)
        num_ventas = random.randint(8, 25)
        for _ in range(num_ventas):
            try:
                cliente_id = random.choice(cli_ids + [None, None])
                forma      = random.choice(formas)
                n_items    = random.randint(1, 4)
                items      = random.sample(prods_vendibles, min(n_items, len(prods_vendibles)))
                subtotal   = 0.0
                venta_id = conn.execute("""
                    INSERT INTO ventas
                    (uuid, folio, sucursal_id, usuario, cliente_id,
                     subtotal, total, forma_pago, efectivo_recibido, cambio,
                     estado, fecha)
                    VALUES(lower(hex(randomblob(16))),?,1,'cajero1',?,0,0,?,0,0,'completada',?)""",
                    (f"V{venta_count+1:06d}", cliente_id, forma,
                     fecha.strftime("%Y-%m-%d %H:%M:%S"))).lastrowid
                for prod_nombre, pid in items:
                    qty   = round(random.uniform(0.5, 3.0), 3)
                    precio = next(p for n,p,*_ in PRODUCTOS_CARNE if n == prod_nombre)
                    sub   = round(qty * precio, 2)
                    subtotal += sub
                    conn.execute("""
                        INSERT INTO detalles_venta
                        (venta_id, producto_id, cantidad, precio_unitario, subtotal, unidad)
                        VALUES(?,?,?,?,?,'kg')""",
                        (venta_id, pid, qty, precio, sub))
                recibido = subtotal * random.uniform(1.0, 1.5)
                conn.execute("""UPDATE ventas SET subtotal=?,total=?,efectivo_recibido=?,cambio=?
                    WHERE id=?""",
                    (subtotal, subtotal, recibido, recibido-subtotal, venta_id))
                conn.execute("""INSERT INTO movimientos_caja
                    (tipo,monto,descripcion,usuario,venta_id,forma_pago,fecha)
                    VALUES('INGRESO',?,?,?,'cajero1',?,?)""",
                    (subtotal, f"Venta {venta_id}", forma,
                     fecha.strftime("%Y-%m-%d %H:%M:%S")))
                venta_count += 1
            except Exception:
                pass
    conn.commit()
    print(f"  ✓ {venta_count} ventas históricas")

    # ── Turno abierto para demo ─────────────────────────────────────────
    try:
        conn.execute("""INSERT OR REPLACE INTO turno_actual
            (sucursal_id, usuario, turno, fondo_inicial, fecha_apertura, abierto)
            VALUES(1,'admin','Demo',500.0,datetime('now'),1)""")
        conn.commit()
        print("→ Turno demo abierto ✓")
    except Exception: pass

    # ── Resumen ─────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"  ✓ Seed completado exitosamente")
    print(f"{'='*55}")
    print(f"  Productos:       {len(prod_ids)}")
    print(f"  Clientes:        {len(cli_ids)}")
    print(f"  Usuarios:        {usr_count}")
    print(f"  Paquetes:        {pkg_count}")
    print(f"  Ventas (30d):    {venta_count}")
    print(f"\n  Credenciales de acceso:")
    for usuario, _, rol, password in USUARIOS_DEMO:
        print(f"    {usuario:15s} / {password:15s}  [{rol}]")
    print(f"{'='*55}\n")
    # Bot tables
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS bot_sessions (
            numero TEXT PRIMARY KEY, datos TEXT,
            ultima_actividad DATETIME DEFAULT (datetime('now')))""")
        conn.commit()
    except Exception: pass
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SPJ POS v10 — Seed de datos demo")
    parser.add_argument("--db",    default="data/spj.db", help="Ruta a la BD")
    parser.add_argument("--clear", action="store_true",    help="Limpiar antes de sembrar")
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)
    seed(args.db, args.clear)
