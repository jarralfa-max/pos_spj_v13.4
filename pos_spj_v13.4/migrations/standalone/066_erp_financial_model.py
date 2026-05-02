# migrations/standalone/066_erp_financial_model.py
# ERP FASE — Modelo financiero auditable tipo ERP (Issue #104)
# Implementa: terceros, cuentas_financieras, documentos_financieros,
#             pagos_cobros, pagos_cobros_aplicaciones, movimientos_financieros,
#             ledger_financiero, auditoria_eventos, cortes_caja,
#             conciliaciones_financieras
# Regla central: ninguna operación crítica se borra — sólo se reversa.

import logging
logger = logging.getLogger("spj.migrations.066")


def run(conn):
    c = conn.cursor()

    # ── 1. TERCEROS ──────────────────────────────────────────────────────────
    c.executescript("""
        CREATE TABLE IF NOT EXISTS terceros (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo_tercero     TEXT    NOT NULL DEFAULT 'cliente'
                                     CHECK(tipo_tercero IN ('cliente','proveedor','empleado','mixto')),
            nombre           TEXT    NOT NULL,
            razon_social     TEXT,
            rfc              TEXT,
            telefono         TEXT,
            correo           TEXT,
            direccion        TEXT,
            estado           TEXT    NOT NULL DEFAULT 'activo'
                                     CHECK(estado IN ('activo','inactivo','bloqueado')),
            limite_credito   REAL    NOT NULL DEFAULT 0,
            dias_credito     INTEGER NOT NULL DEFAULT 0,
            sucursal_id      INTEGER NOT NULL DEFAULT 1,
            created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_terceros_tipo   ON terceros(tipo_tercero);
        CREATE INDEX IF NOT EXISTS idx_terceros_estado ON terceros(estado);
        CREATE INDEX IF NOT EXISTS idx_terceros_rfc    ON terceros(rfc);
    """)

    # ── 2. CUENTAS FINANCIERAS ───────────────────────────────────────────────
    c.executescript("""
        CREATE TABLE IF NOT EXISTS cuentas_financieras (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre        TEXT NOT NULL,
            tipo          TEXT NOT NULL DEFAULT 'caja'
                               CHECK(tipo IN ('caja','banco','efectivo','terminal','cuenta_interna')),
            sucursal_id   INTEGER NOT NULL DEFAULT 1,
            moneda        TEXT NOT NULL DEFAULT 'MXN',
            estado        TEXT NOT NULL DEFAULT 'activo'
                               CHECK(estado IN ('activo','inactivo')),
            saldo_inicial REAL NOT NULL DEFAULT 0,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_cuentas_fin_sucursal ON cuentas_financieras(sucursal_id);
    """)

    # ── 3. CATÁLOGO DE CUENTAS CONTABLES ────────────────────────────────────
    c.executescript("""
        CREATE TABLE IF NOT EXISTS catalogo_cuentas_contables (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo         TEXT    NOT NULL UNIQUE,
            nombre         TEXT    NOT NULL,
            tipo           TEXT    NOT NULL
                                   CHECK(tipo IN ('activo','pasivo','capital','ingreso','costo','gasto')),
            cuenta_padre_id INTEGER REFERENCES catalogo_cuentas_contables(id),
            estado         TEXT    NOT NULL DEFAULT 'activo'
                                   CHECK(estado IN ('activo','inactivo')),
            created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_cat_cuentas_codigo ON catalogo_cuentas_contables(codigo);
        CREATE INDEX IF NOT EXISTS idx_cat_cuentas_tipo   ON catalogo_cuentas_contables(tipo);
    """)

    # ── 4. DOCUMENTOS FINANCIEROS ────────────────────────────────────────────
    c.executescript("""
        CREATE TABLE IF NOT EXISTS documentos_financieros (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            folio               TEXT    NOT NULL UNIQUE,
            tipo_documento      TEXT    NOT NULL
                                        CHECK(tipo_documento IN (
                                            'venta','compra','devolucion_venta','devolucion_compra',
                                            'nota_credito','nota_debito','merma','produccion',
                                            'ajuste','anticipo'
                                        )),
            tercero_id          INTEGER REFERENCES terceros(id),
            tercero_tipo        TEXT    NOT NULL DEFAULT 'cliente'
                                        CHECK(tercero_tipo IN ('cliente','proveedor','interno')),
            modulo_origen       TEXT    NOT NULL DEFAULT 'ventas',
            documento_origen_id INTEGER,
            fecha_emision       TEXT    NOT NULL DEFAULT (date('now')),
            fecha_vencimiento   TEXT,
            subtotal            REAL    NOT NULL DEFAULT 0,
            impuestos           REAL    NOT NULL DEFAULT 0,
            descuentos          REAL    NOT NULL DEFAULT 0,
            total               REAL    NOT NULL DEFAULT 0,
            saldo_pendiente     REAL    NOT NULL DEFAULT 0,
            estado              TEXT    NOT NULL DEFAULT 'borrador'
                                        CHECK(estado IN (
                                            'borrador','confirmado','parcial','pagado',
                                            'cancelado','reversado'
                                        )),
            usuario_id          INTEGER,
            sucursal_id         INTEGER NOT NULL DEFAULT 1,
            caja_id             INTEGER,
            referencia          TEXT,
            created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_doc_fin_tipo      ON documentos_financieros(tipo_documento);
        CREATE INDEX IF NOT EXISTS idx_doc_fin_tercero   ON documentos_financieros(tercero_id);
        CREATE INDEX IF NOT EXISTS idx_doc_fin_estado    ON documentos_financieros(estado);
        CREATE INDEX IF NOT EXISTS idx_doc_fin_emision   ON documentos_financieros(fecha_emision);
        CREATE INDEX IF NOT EXISTS idx_doc_fin_sucursal  ON documentos_financieros(sucursal_id);
        CREATE INDEX IF NOT EXISTS idx_doc_fin_modulo    ON documentos_financieros(modulo_origen);
    """)

    # ── 5. PAGOS Y COBROS ────────────────────────────────────────────────────
    c.executescript("""
        CREATE TABLE IF NOT EXISTS pagos_cobros (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            folio               TEXT    NOT NULL UNIQUE,
            tipo_operacion      TEXT    NOT NULL
                                        CHECK(tipo_operacion IN (
                                            'cobro_cliente','pago_proveedor',
                                            'anticipo_cliente','anticipo_proveedor',
                                            'ajuste_financiero'
                                        )),
            tercero_id          INTEGER REFERENCES terceros(id),
            tercero_tipo        TEXT    NOT NULL DEFAULT 'cliente'
                                        CHECK(tercero_tipo IN ('cliente','proveedor')),
            monto_total         REAL    NOT NULL DEFAULT 0,
            forma_pago          TEXT    NOT NULL DEFAULT 'efectivo'
                                        CHECK(forma_pago IN (
                                            'efectivo','tarjeta','transferencia','credito','mixto'
                                        )),
            cuenta_financiera_id INTEGER REFERENCES cuentas_financieras(id),
            fecha               TEXT    NOT NULL DEFAULT (date('now')),
            usuario_id          INTEGER,
            sucursal_id         INTEGER NOT NULL DEFAULT 1,
            caja_id             INTEGER,
            estado              TEXT    NOT NULL DEFAULT 'registrado'
                                        CHECK(estado IN (
                                            'registrado','aplicado','parcial','cancelado','reversado'
                                        )),
            referencia          TEXT,
            observaciones       TEXT,
            created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_pagos_cobros_tipo      ON pagos_cobros(tipo_operacion);
        CREATE INDEX IF NOT EXISTS idx_pagos_cobros_tercero   ON pagos_cobros(tercero_id);
        CREATE INDEX IF NOT EXISTS idx_pagos_cobros_fecha     ON pagos_cobros(fecha);
        CREATE INDEX IF NOT EXISTS idx_pagos_cobros_estado    ON pagos_cobros(estado);
        CREATE INDEX IF NOT EXISTS idx_pagos_cobros_sucursal  ON pagos_cobros(sucursal_id);
    """)

    # ── 6. APLICACIONES DE PAGO/COBRO ────────────────────────────────────────
    c.executescript("""
        CREATE TABLE IF NOT EXISTS pagos_cobros_aplicaciones (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            pago_cobro_id            INTEGER NOT NULL REFERENCES pagos_cobros(id),
            documento_financiero_id  INTEGER NOT NULL REFERENCES documentos_financieros(id),
            monto_aplicado           REAL    NOT NULL DEFAULT 0,
            saldo_anterior_documento REAL    NOT NULL DEFAULT 0,
            saldo_posterior_documento REAL   NOT NULL DEFAULT 0,
            usuario_id               INTEGER,
            created_at               TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_pca_pago      ON pagos_cobros_aplicaciones(pago_cobro_id);
        CREATE INDEX IF NOT EXISTS idx_pca_documento ON pagos_cobros_aplicaciones(documento_financiero_id);
    """)

    # ── 7. MOVIMIENTOS FINANCIEROS ───────────────────────────────────────────
    c.executescript("""
        CREATE TABLE IF NOT EXISTS movimientos_financieros (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            folio                TEXT    NOT NULL UNIQUE,
            tipo_movimiento      TEXT    NOT NULL
                                         CHECK(tipo_movimiento IN (
                                             'entrada','salida','transferencia','ajuste','reversa'
                                         )),
            cuenta_financiera_id INTEGER REFERENCES cuentas_financieras(id),
            monto                REAL    NOT NULL DEFAULT 0,
            moneda               TEXT    NOT NULL DEFAULT 'MXN',
            metodo_pago          TEXT,
            origen_modulo        TEXT,
            origen_id            INTEGER,
            tercero_id           INTEGER REFERENCES terceros(id),
            usuario_id           INTEGER,
            sucursal_id          INTEGER NOT NULL DEFAULT 1,
            caja_id              INTEGER,
            estado               TEXT    NOT NULL DEFAULT 'registrado',
            fecha                TEXT    NOT NULL DEFAULT (datetime('now')),
            referencia           TEXT,
            created_at           TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_mov_fin_tipo      ON movimientos_financieros(tipo_movimiento);
        CREATE INDEX IF NOT EXISTS idx_mov_fin_cuenta    ON movimientos_financieros(cuenta_financiera_id);
        CREATE INDEX IF NOT EXISTS idx_mov_fin_fecha     ON movimientos_financieros(fecha);
        CREATE INDEX IF NOT EXISTS idx_mov_fin_sucursal  ON movimientos_financieros(sucursal_id);
        CREATE INDEX IF NOT EXISTS idx_mov_fin_modulo    ON movimientos_financieros(origen_modulo);
    """)

    # ── 8. LEDGER FINANCIERO (INMUTABLE) ────────────────────────────────────
    c.executescript("""
        CREATE TABLE IF NOT EXISTS ledger_financiero (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            evento         TEXT    NOT NULL,
            entidad_tipo   TEXT,
            entidad_id     INTEGER,
            modulo_origen  TEXT,
            tercero_id     INTEGER,
            monto          REAL    NOT NULL DEFAULT 0,
            moneda         TEXT    NOT NULL DEFAULT 'MXN',
            saldo_anterior REAL    NOT NULL DEFAULT 0,
            saldo_posterior REAL   NOT NULL DEFAULT 0,
            usuario_id     INTEGER,
            sucursal_id    INTEGER NOT NULL DEFAULT 1,
            caja_id        INTEGER,
            timestamp      TEXT    NOT NULL DEFAULT (datetime('now')),
            referencia     TEXT,
            metadata_json  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ledger_evento    ON ledger_financiero(evento);
        CREATE INDEX IF NOT EXISTS idx_ledger_entidad   ON ledger_financiero(entidad_tipo, entidad_id);
        CREATE INDEX IF NOT EXISTS idx_ledger_timestamp ON ledger_financiero(timestamp);
        CREATE INDEX IF NOT EXISTS idx_ledger_tercero   ON ledger_financiero(tercero_id);
        CREATE INDEX IF NOT EXISTS idx_ledger_sucursal  ON ledger_financiero(sucursal_id);
    """)

    # ── 9. AUDITORÍA DE EVENTOS ───────────────────────────────────────────────
    c.executescript("""
        CREATE TABLE IF NOT EXISTS auditoria_eventos (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id           INTEGER,
            accion               TEXT    NOT NULL
                                         CHECK(accion IN (
                                             'crear','editar','cancelar','reversar','aprobar',
                                             'rechazar','consultar','exportar'
                                         )),
            entidad_tipo         TEXT,
            entidad_id           INTEGER,
            modulo               TEXT,
            valor_anterior_json  TEXT,
            valor_nuevo_json     TEXT,
            motivo               TEXT,
            ip                   TEXT,
            terminal             TEXT,
            timestamp            TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_audit_usuario   ON auditoria_eventos(usuario_id);
        CREATE INDEX IF NOT EXISTS idx_audit_entidad   ON auditoria_eventos(entidad_tipo, entidad_id);
        CREATE INDEX IF NOT EXISTS idx_audit_accion    ON auditoria_eventos(accion);
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON auditoria_eventos(timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_modulo    ON auditoria_eventos(modulo);
    """)

    # ── 10. CORTES DE CAJA ───────────────────────────────────────────────────
    c.executescript("""
        CREATE TABLE IF NOT EXISTS cortes_caja_erp (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            folio             TEXT    NOT NULL UNIQUE,
            caja_id           INTEGER,
            usuario_id        INTEGER,
            sucursal_id       INTEGER NOT NULL DEFAULT 1,
            fecha_apertura    TEXT    NOT NULL DEFAULT (datetime('now')),
            fecha_cierre      TEXT,
            saldo_inicial     REAL    NOT NULL DEFAULT 0,
            total_ventas      REAL    NOT NULL DEFAULT 0,
            total_cobros      REAL    NOT NULL DEFAULT 0,
            total_pagos       REAL    NOT NULL DEFAULT 0,
            total_retiros     REAL    NOT NULL DEFAULT 0,
            efectivo_esperado REAL    NOT NULL DEFAULT 0,
            efectivo_contado  REAL    NOT NULL DEFAULT 0,
            diferencia        REAL    NOT NULL DEFAULT 0,
            estado            TEXT    NOT NULL DEFAULT 'abierto'
                                       CHECK(estado IN ('abierto','cerrado','conciliado')),
            created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_cortes_erp_sucursal ON cortes_caja_erp(sucursal_id);
        CREATE INDEX IF NOT EXISTS idx_cortes_erp_estado   ON cortes_caja_erp(estado);
    """)

    # ── 11. CONCILIACIONES FINANCIERAS ──────────────────────────────────────
    c.executescript("""
        CREATE TABLE IF NOT EXISTS conciliaciones_financieras (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            folio                TEXT    NOT NULL UNIQUE,
            cuenta_financiera_id INTEGER REFERENCES cuentas_financieras(id),
            periodo              TEXT    NOT NULL,
            saldo_sistema        REAL    NOT NULL DEFAULT 0,
            saldo_real           REAL    NOT NULL DEFAULT 0,
            diferencia           REAL    NOT NULL DEFAULT 0,
            estado               TEXT    NOT NULL DEFAULT 'pendiente'
                                          CHECK(estado IN ('pendiente','conciliado','con_diferencia')),
            usuario_id           INTEGER,
            sucursal_id          INTEGER NOT NULL DEFAULT 1,
            fecha                TEXT    NOT NULL DEFAULT (date('now')),
            notas                TEXT,
            created_at           TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_concil_cuenta   ON conciliaciones_financieras(cuenta_financiera_id);
        CREATE INDEX IF NOT EXISTS idx_concil_periodo  ON conciliaciones_financieras(periodo);
        CREATE INDEX IF NOT EXISTS idx_concil_estado   ON conciliaciones_financieras(estado);
    """)

    conn.commit()
    logger.info("066_erp_financial_model: todas las tablas ERP financiero creadas/verificadas.")
