-- migrations/fix_finanzas_schema.sql — SPJ POS v13.4 ERP Hotfix
-- Columnas faltantes en tablas de finanzas.
-- SQLite 3.35+: ADD COLUMN IF NOT EXISTS
-- Para SQLite < 3.35, usar la migración Python 061_fix_finanzas_schema.py

ALTER TABLE financial_event_log ADD COLUMN IF NOT EXISTS concepto TEXT;

ALTER TABLE accounts_payable ADD COLUMN IF NOT EXISTS folio TEXT;
ALTER TABLE accounts_payable ADD COLUMN IF NOT EXISTS concepto TEXT;
ALTER TABLE accounts_payable ADD COLUMN IF NOT EXISTS ref_type TEXT DEFAULT 'manual';

ALTER TABLE accounts_receivable ADD COLUMN IF NOT EXISTS folio TEXT;
ALTER TABLE accounts_receivable ADD COLUMN IF NOT EXISTS venta_id INTEGER;
