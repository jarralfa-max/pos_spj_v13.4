# migrations/standalone/059_plan_cuentas.py
# Fase 3 — Plan de cuentas SAT (Plan Maestro SPJ v13.4)
# Catálogo contable mínimo NIF/SAT: 1xx Activo, 2xx Pasivo, 3xx Capital,
# 4xx Ingresos, 5xx Costos, 6xx Gastos. Idempotente.


def run(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plan_cuentas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_sat  TEXT    NOT NULL UNIQUE,
            nombre      TEXT    NOT NULL,
            tipo        TEXT    NOT NULL CHECK(tipo IN
                            ('activo','pasivo','capital','ingreso','costo','gasto')),
            nivel       INTEGER DEFAULT 1,
            padre_id    INTEGER REFERENCES plan_cuentas(id),
            activo      INTEGER DEFAULT 1,
            descripcion TEXT    DEFAULT '',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_pc_codigo
            ON plan_cuentas(codigo_sat)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_pc_tipo
            ON plan_cuentas(tipo)
    """)

    # Catálogo mínimo SAT — INSERT OR IGNORE para idempotencia
    cuentas = [
        # ── Activo ──────────────────────────────────────────────────────────
        ("1000", "Activo",                             "activo", 1, ""),
        ("1100", "Activo Circulante",                  "activo", 2, ""),
        ("1101", "Caja",                               "activo", 3, "Efectivo en caja"),
        ("1102", "Bancos",                             "activo", 3, "Cuentas bancarias"),
        ("1103", "Cuentas por Cobrar Clientes",        "activo", 3, ""),
        ("1200", "Inventarios",                        "activo", 2, ""),
        ("1201", "Inventario de Mercancías",           "activo", 3, ""),
        ("1300", "Activo Fijo",                        "activo", 2, ""),
        ("1301", "Equipo y Maquinaria",                "activo", 3, ""),
        ("1302", "Depreciación Acumulada Equipo",      "activo", 3,
         "Cuenta complementaria de saldo acreedor"),
        # ── Pasivo ──────────────────────────────────────────────────────────
        ("2000", "Pasivo",                             "pasivo", 1, ""),
        ("2100", "Pasivo Circulante",                  "pasivo", 2, ""),
        ("2101", "Cuentas por Pagar Proveedores",      "pasivo", 3, ""),
        ("2102", "IMSS por Pagar",                     "pasivo", 3, "Retenciones y cuotas IMSS"),
        ("2103", "ISR por Pagar",                      "pasivo", 3, "Retenciones ISR empleados"),
        ("2104", "Pasivo Fidelización",                "pasivo", 3,
         "Estrellas emitidas pendientes de canje"),
        # ── Capital ─────────────────────────────────────────────────────────
        ("3000", "Capital",                            "capital", 1, ""),
        ("3100", "Capital Social",                     "capital", 2, ""),
        ("3101", "Aportaciones de Capital",            "capital", 3, ""),
        ("3102", "Retiros de Capital",                 "capital", 3, "Saldo deudor"),
        ("3200", "Resultados",                         "capital", 2, ""),
        ("3201", "Utilidad del Ejercicio",             "capital", 3, ""),
        ("3202", "Utilidades Acumuladas",              "capital", 3, ""),
        # ── Ingresos ────────────────────────────────────────────────────────
        ("4000", "Ingresos",                           "ingreso", 1, ""),
        ("4100", "Ventas",                             "ingreso", 2, ""),
        ("4101", "Ventas al Contado",                  "ingreso", 3, ""),
        ("4102", "Ventas a Crédito",                   "ingreso", 3, ""),
        # ── Costos ──────────────────────────────────────────────────────────
        ("5000", "Costos de Ventas",                   "costo",   1, ""),
        ("5101", "Costo de Mercancías Vendidas",       "costo",   2, ""),
        ("5102", "Merma de Inventario",                "costo",   2, ""),
        # ── Gastos ──────────────────────────────────────────────────────────
        ("6000", "Gastos",                             "gasto",   1, ""),
        ("6100", "Gastos de Operación",                "gasto",   2, ""),
        ("6101", "Renta y Arrendamiento",              "gasto",   3, ""),
        ("6102", "Servicios (Luz, Agua, Gas, Internet)","gasto",  3, ""),
        ("6103", "Nómina y Salarios",                  "gasto",   3, ""),
        ("6104", "Cuotas IMSS Patronales",             "gasto",   3, ""),
        ("6105", "Depreciación de Activos",            "gasto",   3, ""),
        ("6106", "Mantenimiento y Reparación",         "gasto",   3, ""),
        ("6107", "Publicidad y Mercadotecnia",         "gasto",   3, ""),
        ("6108", "Comisiones (MercadoPago, Delivery)", "gasto",   3, ""),
        ("6109", "Gastos de Papelería y Empaque",      "gasto",   3, ""),
    ]

    for codigo, nombre, tipo, nivel, desc in cuentas:
        conn.execute("""
            INSERT OR IGNORE INTO plan_cuentas(codigo_sat, nombre, tipo, nivel, descripcion)
            VALUES (?,?,?,?,?)
        """, (codigo, nombre, tipo, nivel, desc))
