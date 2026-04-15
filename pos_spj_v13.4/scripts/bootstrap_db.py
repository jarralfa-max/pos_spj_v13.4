"""
bootstrap_db.py — Inicializa la base de datos SQLite con las tablas críticas.
Este script es ejecutado al iniciar la aplicación para asegurar que la BD exista.
"""
import sqlite3
import os
from datetime import datetime


def bootstrap_database(db_path: str) -> None:
    """
    Crea la base de datos y las tablas críticas si no existen.
    Es idempotente: puede ejecutarse múltiples veces sin errores.
    
    Args:
        db_path: Ruta completa al archivo .db
    """
    # Asegurar que el directorio existe
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # ── Tabla: usuarios ─────────────────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                nombre_completo TEXT,
                rol TEXT DEFAULT 'vendedor',
                activo INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ── Tabla: productos ───────────────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_barras TEXT UNIQUE,
                nombre TEXT NOT NULL,
                descripcion TEXT,
                costo REAL DEFAULT 0,
                precio_venta REAL DEFAULT 0,
                stock_actual REAL DEFAULT 0,
                stock_minimo REAL DEFAULT 0,
                categoria_id INTEGER,
                unidad_medida TEXT DEFAULT 'pz',
                activo INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ── Tabla: clientes ────────────────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfc TEXT UNIQUE,
                nombre TEXT NOT NULL,
                razon_social TEXT,
                email TEXT,
                telefono TEXT,
                calle TEXT,
                numero_exterior TEXT,
                numero_interior TEXT,
                colonia TEXT,
                ciudad TEXT,
                estado TEXT,
                codigo_postal TEXT,
                pais TEXT DEFAULT 'México',
                credito_limite REAL DEFAULT 0,
                credito_usado REAL DEFAULT 0,
                puntos_acumulados INTEGER DEFAULT 0,
                nivel_fidelidad TEXT DEFAULT 'Bronce',
                activo INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ── Tabla: ventas ──────────────────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folio TEXT UNIQUE NOT NULL,
                cliente_id INTEGER,
                usuario_id INTEGER NOT NULL,
                subtotal REAL DEFAULT 0,
                descuento REAL DEFAULT 0,
                impuestos REAL DEFAULT 0,
                total REAL DEFAULT 0,
                metodo_pago TEXT DEFAULT 'efectivo',
                estado TEXT DEFAULT 'completada',
                comentario TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id),
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
        """)
        
        # ── Tabla: detalles_venta ──────────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS detalles_venta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venta_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                cantidad REAL DEFAULT 1,
                precio_unitario REAL DEFAULT 0,
                descuento REAL DEFAULT 0,
                subtotal REAL DEFAULT 0,
                total REAL DEFAULT 0,
                FOREIGN KEY (venta_id) REFERENCES ventas(id) ON DELETE CASCADE,
                FOREIGN KEY (producto_id) REFERENCES productos(id)
            )
        """)
        
        # ── Tabla: configuraciones ─────────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS configuraciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clave TEXT UNIQUE NOT NULL,
                valor TEXT,
                tipo TEXT DEFAULT 'string',
                descripcion TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ── Tabla: categorias ──────────────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                descripcion TEXT,
                padre_id INTEGER,
                activo INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (padre_id) REFERENCES categorias(id)
            )
        """)
        
        # ── Tabla: proveedores ─────────────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS proveedores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfc TEXT UNIQUE,
                nombre TEXT NOT NULL,
                razon_social TEXT,
                email TEXT,
                telefono TEXT,
                contacto TEXT,
                calle TEXT,
                numero_exterior TEXT,
                colonia TEXT,
                ciudad TEXT,
                estado TEXT,
                codigo_postal TEXT,
                pais TEXT DEFAULT 'México',
                activo INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ── Tabla: compras ─────────────────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS compras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folio TEXT UNIQUE NOT NULL,
                proveedor_id INTEGER NOT NULL,
                usuario_id INTEGER NOT NULL,
                subtotal REAL DEFAULT 0,
                descuento REAL DEFAULT 0,
                impuestos REAL DEFAULT 0,
                total REAL DEFAULT 0,
                estado TEXT DEFAULT 'completada',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (proveedor_id) REFERENCES proveedores(id),
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
        """)
        
        # ── Tabla: movimientos_inventario ──────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS movimientos_inventario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id INTEGER NOT NULL,
                tipo_movimiento TEXT NOT NULL,
                cantidad REAL NOT NULL,
                saldo_anterior REAL DEFAULT 0,
                saldo_nuevo REAL DEFAULT 0,
                referencia_tipo TEXT,
                referencia_id INTEGER,
                usuario_id INTEGER,
                comentario TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (producto_id) REFERENCES productos(id),
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
        """)
        
        # ── Tabla: cotizaciones ────────────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cotizaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folio TEXT UNIQUE NOT NULL,
                cliente_id INTEGER NOT NULL,
                usuario_id INTEGER NOT NULL,
                subtotal REAL DEFAULT 0,
                descuento REAL DEFAULT 0,
                impuestos REAL DEFAULT 0,
                total REAL DEFAULT 0,
                validez_dias INTEGER DEFAULT 7,
                estado TEXT DEFAULT 'pendiente',
                comentario TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id),
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
        """)
        
        # ── Insertar configuración por defecto si no existe ────────────────────
        configs_default = [
            ('nombre_empresa', 'SPJ POS', 'string', 'Nombre de la empresa'),
            ('rfc_empresa', '', 'string', 'RFC de la empresa'),
            ('moneda', 'MXN', 'string', 'Moneda del sistema'),
            ('impuesto_porcentaje', '16', 'float', 'Porcentaje de IVA'),
            ('ticket_cabecera', '¡Gracias por su compra!', 'string', 'Texto cabecera ticket'),
            ('ticket_pie', 'Vuelva pronto', 'string', 'Texto pie ticket'),
            ('permite_ventas_credito', '1', 'bool', 'Permitir ventas a crédito'),
            ('puntos_por_pesos', '1', 'integer', 'Puntos por cada $10 de compra'),
        ]
        
        for clave, valor, tipo, desc in configs_default:
            cursor.execute("""
                INSERT OR IGNORE INTO configuraciones (clave, valor, tipo, descripcion)
                VALUES (?, ?, ?, ?)
            """, (clave, valor, tipo, desc))
        
        # ── Insertar usuario admin por defecto si no existe ────────────────────
        # Password: 'admin123' (hash simple para bootstrap, debe cambiarse)
        cursor.execute("""
            INSERT OR IGNORE INTO usuarios (username, password_hash, nombre_completo, rol)
            VALUES (?, ?, ?, ?)
        """, ('admin', 'admin123', 'Administrador Principal', 'admin'))
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


if __name__ == "__main__":
    # Ejecución directa para testing
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    print(f"Creando base de datos de prueba en: {db_path}")
    bootstrap_database(db_path)
    print("✓ Base de datos creada exitosamente")
    
    # Verificar tablas creadas
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tablas = [row[0] for row in cursor.fetchall()]
    print(f"Tablas creadas: {', '.join(tablas)}")
    conn.close()
    
    # Limpiar
    os.unlink(db_path)
    print("✓ Test completado - archivo temporal eliminado")
