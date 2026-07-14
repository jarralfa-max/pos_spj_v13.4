# migrations/standalone/047_v13_schema.py — SPJ POS v13
"""
Migración 047 — Esquema completo v13.

Nuevas tablas:
  - sucursales: columnas de horario de atención
  - pedidos_whatsapp: sucursal_id, hora_deseada, prioridad, escalación
  - ordenes_cotizacion: flujo cotización → orden → anticipo → entrega
  - anticipo_reglas: reglas por categoría y monto
  - anticipo_config: configuración general de anticipos
  - lotes_tarjetas_pdf: historial de lotes PDF de tarjetas
  - rol_permisos: permisos granulares por módulo/acción
  - usuarios_sucursales: un usuario en múltiples sucursales
  - version_checker: última versión verificada
  
Columnas nuevas en tablas existentes:
  - usuarios: empleado_id, foto_path, sucursal_principal_id,
              intentos_fallidos, bloqueado_hasta, ultimo_acceso
  - personal (RRHH): usuario_id
  - sucursales: horario completo
"""
import logging
logger = logging.getLogger(__name__)
VERSION     = "047"
DESCRIPTION = "v13.0 schema: horarios, anticipos, ordenes_cotizacion, permisos granulares, tarjetas lotes"


def up(conn):
    # ── Helpers ───────────────────────────────────────────────────────────────
    def col_exists(table, col):
        try:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            return col in cols
        except Exception:
            return False

    def add_col(table, col_def):
        col_name = col_def.split()[0]
        if not col_exists(table, col_name):
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
            except Exception as e:
                logger.debug("add_col %s.%s: %s", table, col_name, e)

    # ── 1. Sucursales — horario de atención ──────────────────────────────────
    add_col("sucursales", "hora_apertura TEXT DEFAULT '08:00'")
    add_col("sucursales", "hora_cierre TEXT DEFAULT '21:00'")
    add_col("sucursales", "dias_operacion TEXT DEFAULT '1,2,3,4,5,6'")
    add_col("sucursales", "acepta_pedidos_fuera_horario INTEGER DEFAULT 1")
    add_col("sucursales", "mensaje_fuera_horario TEXT DEFAULT 'Estamos cerrados en este momento. Tu pedido quedará programado para cuando abramos.'")
    add_col("sucursales", "telefono TEXT")
    add_col("sucursales", "email TEXT")
    add_col("sucursales", "logo_path TEXT")

    # ── 2. Pedidos WhatsApp — ampliación v13 ──────────────────────────────────
    add_col("pedidos_whatsapp", "sucursal_id TEXT")
    add_col("pedidos_whatsapp", "hora_deseada TEXT")
    add_col("pedidos_whatsapp", "prioridad TEXT DEFAULT 'normal'")
    add_col("pedidos_whatsapp", "notificado_gerente INTEGER DEFAULT 0")
    add_col("pedidos_whatsapp", "respuesta_auto_enviada INTEGER DEFAULT 0")
    add_col("pedidos_whatsapp", "programado INTEGER DEFAULT 0")

    # ── 3. Órdenes de cotización ──────────────────────────────────────────────
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ordenes_cotizacion (
            id                      TEXT NOT NULL PRIMARY KEY,
            numero_orden            TEXT UNIQUE NOT NULL,
            cotizacion_id           TEXT REFERENCES cotizaciones(id),
            cliente_id              TEXT REFERENCES clientes(id),
            sucursal_id             TEXT,
            estado                  TEXT DEFAULT 'pendiente',
            -- pendiente | anticipo_pendiente | anticipo_pagado |
            -- en_preparacion | listo | entregado | cancelado
            requiere_anticipo       INTEGER DEFAULT 1,
            pct_anticipo_aplicado   REAL DEFAULT 0,
            razon_anticipo          TEXT,
            -- 'categoria:Cortes especiales:50%|monto:$1165:30%→max=50%'
            monto_total             REAL DEFAULT 0,
            monto_anticipo          REAL DEFAULT 0,
            anticipo_pagado         REAL DEFAULT 0,
            metodo_anticipo         TEXT,
            link_pago               TEXT,
            payment_id              TEXT,
            fecha_entrega           DATE,
            hora_entrega            TEXT,
            tipo_entrega            TEXT DEFAULT 'mostrador',
            direccion_entrega       TEXT,
            recordatorio_d2_enviado INTEGER DEFAULT 0,
            recordatorio_d1_enviado INTEGER DEFAULT 0,
            recordatorio_apertura_enviado INTEGER DEFAULT 0,
            notas                   TEXT,
            usuario_asigno          TEXT,
            fecha_creacion          DATETIME DEFAULT (datetime('now')),
            fecha_confirmacion      DATETIME,
            fecha_entrega_real      DATETIME
        );
        CREATE INDEX IF NOT EXISTS idx_oc_estado
            ON ordenes_cotizacion(estado, fecha_entrega);
        CREATE INDEX IF NOT EXISTS idx_oc_cliente
            ON ordenes_cotizacion(cliente_id, estado);
    """)

    # ── 4. Reglas de anticipo ─────────────────────────────────────────────────
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS anticipo_reglas (
            id           TEXT NOT NULL PRIMARY KEY,
            tipo         TEXT NOT NULL CHECK(tipo IN ('categoria','monto')),
            categoria    TEXT,
            monto_desde  REAL DEFAULT 0,
            monto_hasta  REAL,
            pct_anticipo REAL NOT NULL DEFAULT 30.0
                         CHECK(pct_anticipo >= 0 AND pct_anticipo <= 100),
            activo       INTEGER DEFAULT 1,
            sucursal_id  TEXT DEFAULT 0,
            notas        TEXT,
            created_at   DATETIME DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS anticipo_config (
            clave TEXT NOT NULL PRIMARY KEY,
            valor TEXT NOT NULL
        );

        INSERT OR IGNORE INTO anticipo_config VALUES('pct_default',          '30');
        INSERT OR IGNORE INTO anticipo_config VALUES('monto_minimo',         '500');
        INSERT OR IGNORE INTO anticipo_config VALUES('criterio_combinacion', 'maximo');
        INSERT OR IGNORE INTO anticipo_config VALUES('niveles_exentos',      'Platino,Black');
        INSERT OR IGNORE INTO anticipo_config VALUES('dias_recordatorio_1',  '2');
        INSERT OR IGNORE INTO anticipo_config VALUES('dias_recordatorio_2',  '1');
        INSERT OR IGNORE INTO anticipo_config VALUES('tel_encargado_compras','');
        INSERT OR IGNORE INTO anticipo_config VALUES('msg_recordatorio_cliente',
            'Hola {nombre}, te recordamos tu orden #{orden} para el {fecha}. {pendiente}');
        INSERT OR IGNORE INTO anticipo_config VALUES('msg_recordatorio_compras',
            'Preparar orden #{orden} para {fecha}. Cliente: {cliente}. Items: {items}');
        INSERT OR IGNORE INTO anticipo_config VALUES('msg_anticipo_vencido',
            'La orden #{orden} de {cliente} vence hoy y el anticipo sigue pendiente.');

        -- Reglas por monto default
        INSERT OR IGNORE INTO anticipo_reglas(tipo,monto_desde,monto_hasta,pct_anticipo,notas)
            VALUES('monto', 0,    500,   0,  'Sin anticipo para montos pequeños');
        INSERT OR IGNORE INTO anticipo_reglas(tipo,monto_desde,monto_hasta,pct_anticipo,notas)
            VALUES('monto', 500,  1500,  20, 'Anticipo básico');
        INSERT OR IGNORE INTO anticipo_reglas(tipo,monto_desde,monto_hasta,pct_anticipo,notas)
            VALUES('monto', 1500, 5000,  30, 'Anticipo estándar');
        INSERT OR IGNORE INTO anticipo_reglas(tipo,monto_desde,monto_hasta,pct_anticipo,notas)
            VALUES('monto', 5000, 15000, 40, 'Anticipo mayor');
        INSERT OR IGNORE INTO anticipo_reglas(tipo,monto_desde,monto_hasta,pct_anticipo,notas)
            VALUES('monto', 15000,NULL,  50, 'Anticipo pedidos grandes');
    """)

    # ── 5. Lotes PDF de tarjetas ──────────────────────────────────────────────
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS lotes_tarjetas_pdf (
            id           TEXT NOT NULL PRIMARY KEY,
            nombre       TEXT,
            cantidad     INTEGER NOT NULL DEFAULT 0,
            nivel        TEXT DEFAULT 'todos',
            filtro       TEXT,
            ruta_pdf     TEXT,
            plantilla    TEXT,
            usuario      TEXT,
            sucursal_id  TEXT,
            created_at   DATETIME DEFAULT (datetime('now'))
        );
    """)

    # ── 6. Permisos granulares ────────────────────────────────────────────────
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS rol_permisos (
            id       TEXT NOT NULL PRIMARY KEY,
            rol_id   TEXT NOT NULL,
            modulo   TEXT NOT NULL,
            accion   TEXT NOT NULL,
            -- ver | crear | editar | eliminar | exportar | aprobar
            permitido INTEGER DEFAULT 1,
            UNIQUE(rol_id, modulo, accion)
        );
        CREATE INDEX IF NOT EXISTS idx_rp_rol
            ON rol_permisos(rol_id, modulo);

        CREATE TABLE IF NOT EXISTS usuarios_sucursales (
            usuario_id   TEXT NOT NULL,
            sucursal_id  TEXT NOT NULL,
            es_principal INTEGER DEFAULT 0,
            fecha_asign  DATETIME DEFAULT (datetime('now')),
            PRIMARY KEY(usuario_id, sucursal_id)
        );
    """)

    # ── 7. Columnas en usuarios ───────────────────────────────────────────────
    for col in [
        "empleado_id TEXT",
        "foto_path TEXT",
        "sucursal_principal_id TEXT",
        "intentos_fallidos INTEGER DEFAULT 0",
        "bloqueado_hasta DATETIME",
        "ultimo_acceso DATETIME",
        "email TEXT",
    ]:
        add_col("usuarios", col)

    # ── 8. Columna usuario_id en personal (RRHH) ──────────────────────────────
    add_col("personal", "usuario_id TEXT")
    add_col("personal", "foto_path TEXT")

    # ── 9. Bot sessions — sucursal elegida ────────────────────────────────────
    add_col("bot_sessions", "sucursal_id TEXT")
    add_col("bot_sessions", "contexto TEXT")  # JSON extra state

    # ── 10. Configuración WhatsApp — escalación pedidos ──────────────────────
    conn.executescript("""
        INSERT OR IGNORE INTO configuraciones(clave,valor,descripcion)
            VALUES('wa_escalacion_min_1','5','Minutos para alerta amarilla pedido sin atender');
        INSERT OR IGNORE INTO configuraciones(clave,valor,descripcion)
            VALUES('wa_escalacion_min_2','15','Minutos para notificar al gerente');
        INSERT OR IGNORE INTO configuraciones(clave,valor,descripcion)
            VALUES('wa_escalacion_min_3','30','Minutos para respuesta automática al cliente');
        INSERT OR IGNORE INTO configuraciones(clave,valor,descripcion)
            VALUES('wa_escalacion_tel_gerente','','Teléfono del gerente para escalación');
        INSERT OR IGNORE INTO configuraciones(clave,valor,descripcion)
            VALUES('wa_msg_escalacion_gerente',
                '⚠️ Pedido #{id} de {cliente} lleva {min} min sin atender. Total: ${total}.',
                'Mensaje al gerente cuando escala un pedido');
        INSERT OR IGNORE INTO configuraciones(clave,valor,descripcion)
            VALUES('wa_msg_respuesta_auto',
                'Hola {nombre}, tu pedido está siendo procesado. Te confirmamos a la brevedad. ¡Gracias!',
                'Respuesta automática al cliente por pedido sin atender');
    """)

    # ── 11. Roles y permisos: seed canónico UUIDv7 en m000 ────────────────────
    # Los roles del sistema y su matriz rol_permisos se siembran born-clean con
    # identidad UUIDv7 en migrations/m000_base_schema.py (_seed_system_roles).
    # Aquí NO se siembran enteros 1..6 (identidad legacy prohibida — REGLA CERO).

    # Ensure ventas has sucursal_id (critical for multi-branch)
    add_col("ventas", "sucursal_id TEXT NOT NULL")
    # (Plan B) ventas.id ES el UUID; sin columna uuid dual.

    # Ensure compras has sucursal_id
    add_col("compras", "sucursal_id TEXT NOT NULL")

    # Ensure lotes has sucursal_id
    add_col("lotes", "sucursal_id TEXT NOT NULL")

    # Ensure caja_operations has sucursal_id
    add_col("caja_operations", "sucursal_id TEXT NOT NULL")

    # Ensure pedidos_whatsapp has sucursal_id
    add_col("pedidos_whatsapp", "sucursal_id TEXT NOT NULL")

    # Ensure delivery_orders has sucursal_id
    add_col("delivery_orders", "sucursal_id TEXT NOT NULL")

    # Ensure proveedores has all expected columns
    for col in [
        "condiciones_pago INTEGER DEFAULT 30",
        "limite_credito REAL DEFAULT 0",
        "banco TEXT",
        "cuenta_bancaria TEXT",
        "contacto TEXT",
    ]:
        col_name = col.split()[0]
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(proveedores)").fetchall()]
            if col_name not in cols:
                conn.execute(f"ALTER TABLE proveedores ADD COLUMN {col}")
        except Exception:
            pass

    # Ensure personal has usuario_id
    add_col("personal", "usuario_id TEXT")
    add_col("personal", "foto_path TEXT")

    # Crear usuario demo si no existe (identidad UUIDv7; sucursal = matriz de
    # instalación, nunca el entero '1').
    try:
        import hashlib
        from backend.shared.ids import new_uuid, INSTALL_BRANCH_UUID
        demo_hash = hashlib.sha256("demo".encode()).hexdigest()
        conn.execute(
            "INSERT OR IGNORE INTO usuarios "
            "(id,nombre,usuario,password_hash,rol,sucursal_id,activo) "
            "VALUES(?,'Usuario Demo','demo',?,?,?,1)",
            (new_uuid(), demo_hash, 'cajero', INSTALL_BRANCH_UUID))
    except Exception: pass

    conn.execute("INSERT OR IGNORE INTO configuraciones(clave,valor) VALUES('app_version','13.0.0')")
    logger.info("047 — v13 schema aplicado")
