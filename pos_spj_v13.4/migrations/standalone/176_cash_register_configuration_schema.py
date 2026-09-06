"""CASH-5 effective, hierarchical and configurable Cash Register catalogs."""
from __future__ import annotations

UUID_CHECK = "length({0})=36 AND lower({0})={0} AND substr({0},15,1)='7'"
U = UUID_CHECK.format
SCOPE = "'SYSTEM','COMPANY','BRANCH','REGISTER','USER'"

DDL = (
    f"""CREATE TABLE IF NOT EXISTS cash_settings (
      id TEXT NOT NULL PRIMARY KEY CHECK({U('id')}), setting_key TEXT NOT NULL CHECK(trim(setting_key)<>''),
      setting_value TEXT NOT NULL, scope_type TEXT NOT NULL CHECK(scope_type IN ({SCOPE})),
      scope_id TEXT, effective_from TEXT NOT NULL, effective_to TEXT, version INTEGER NOT NULL DEFAULT 1 CHECK(version>0),
      created_by TEXT NOT NULL CHECK({U('created_by')}), created_at TEXT NOT NULL,
      CHECK((scope_type='SYSTEM' AND scope_id IS NULL) OR (scope_type<>'SYSTEM' AND {U('scope_id')})),
      CHECK(effective_to IS NULL OR effective_to>effective_from), UNIQUE(setting_key,scope_type,scope_id,effective_from))""",
    f"""CREATE TABLE IF NOT EXISTS cash_denominations (
      id TEXT NOT NULL PRIMARY KEY CHECK({U('id')}), currency_code TEXT NOT NULL CHECK(length(currency_code)=3),
      denomination_value TEXT NOT NULL CHECK(CAST(denomination_value AS NUMERIC)>0), display_name TEXT NOT NULL,
      sort_order INTEGER NOT NULL CHECK(sort_order>=0), active INTEGER NOT NULL CHECK(active IN (0,1)),
      effective_from TEXT NOT NULL, effective_to TEXT, UNIQUE(currency_code,denomination_value,effective_from))""",
    f"""CREATE TABLE IF NOT EXISTS cash_payment_methods (
      id TEXT NOT NULL PRIMARY KEY CHECK({U('id')}), code TEXT NOT NULL, display_name TEXT NOT NULL,
      affects_physical_cash INTEGER NOT NULL CHECK(affects_physical_cash IN (0,1)), active INTEGER NOT NULL CHECK(active IN (0,1)),
      effective_from TEXT NOT NULL, effective_to TEXT, UNIQUE(code,effective_from))""",
    f"""CREATE TABLE IF NOT EXISTS cash_operation_limits (
      id TEXT NOT NULL PRIMARY KEY CHECK({U('id')}), operation_type TEXT NOT NULL,
      approval_threshold TEXT NOT NULL CHECK(CAST(approval_threshold AS NUMERIC)>=0),
      hard_cap TEXT NOT NULL CHECK(CAST(hard_cap AS NUMERIC)>=CAST(approval_threshold AS NUMERIC)),
      scope_type TEXT NOT NULL CHECK(scope_type IN ({SCOPE})), scope_id TEXT,
      effective_from TEXT NOT NULL, effective_to TEXT, created_by TEXT NOT NULL CHECK({U('created_by')}),
      CHECK((scope_type='SYSTEM' AND scope_id IS NULL) OR (scope_type<>'SYSTEM' AND {U('scope_id')})),
      UNIQUE(operation_type,scope_type,scope_id,effective_from))""",
    f"""CREATE TABLE IF NOT EXISTS cash_movement_reasons (
      id TEXT NOT NULL PRIMARY KEY CHECK({U('id')}), code TEXT NOT NULL, display_name TEXT NOT NULL CHECK(trim(display_name)<>''),
      movement_type TEXT NOT NULL CHECK(movement_type IN ('MANUAL_INCOME','MANUAL_WITHDRAWAL','SAFE_DROP')),
      requires_authorization INTEGER NOT NULL CHECK(requires_authorization IN (0,1)),
      active INTEGER NOT NULL CHECK(active IN (0,1)), effective_from TEXT NOT NULL, effective_to TEXT,
      CHECK(effective_to IS NULL OR effective_to>effective_from), UNIQUE(code,effective_from))""",
    f"""CREATE TABLE IF NOT EXISTS cash_alert_rules (
      id TEXT NOT NULL PRIMARY KEY CHECK({U('id')}), event_name TEXT NOT NULL CHECK(event_name LIKE 'CASH_%'),
      severity TEXT NOT NULL CHECK(severity IN ('INFO','WARNING','CRITICAL')),
      channels_json TEXT NOT NULL, scope_type TEXT NOT NULL CHECK(scope_type IN ({SCOPE})), scope_id TEXT,
      active INTEGER NOT NULL CHECK(active IN (0,1)), effective_from TEXT NOT NULL, effective_to TEXT,
      CHECK((scope_type='SYSTEM' AND scope_id IS NULL) OR (scope_type<>'SYSTEM' AND {U('scope_id')})),
      UNIQUE(event_name,scope_type,scope_id,effective_from))""",
    f"""CREATE TABLE IF NOT EXISTS cash_difference_policies (
      id TEXT NOT NULL PRIMARY KEY CHECK({U('id')}), tolerance_amount TEXT NOT NULL CHECK(CAST(tolerance_amount AS NUMERIC)>=0),
      critical_threshold TEXT NOT NULL CHECK(CAST(critical_threshold AS NUMERIC)>=CAST(tolerance_amount AS NUMERIC)),
      recurrence_window_days INTEGER NOT NULL CHECK(recurrence_window_days>0),
      recurrence_threshold INTEGER NOT NULL CHECK(recurrence_threshold>0), channels_json TEXT NOT NULL,
      scope_type TEXT NOT NULL CHECK(scope_type IN ({SCOPE})), scope_id TEXT,
      active INTEGER NOT NULL CHECK(active IN (0,1)), effective_from TEXT NOT NULL, effective_to TEXT,
      CHECK((scope_type='SYSTEM' AND scope_id IS NULL) OR (scope_type<>'SYSTEM' AND {U('scope_id')})),
      UNIQUE(scope_type,scope_id,effective_from))""",
    f"""CREATE TABLE IF NOT EXISTS cash_whatsapp_recipients (
      id TEXT NOT NULL PRIMARY KEY CHECK({U('id')}), alert_rule_id TEXT NOT NULL REFERENCES cash_alert_rules(id) ON DELETE CASCADE,
      phone_e164 TEXT NOT NULL CHECK(phone_e164 LIKE '+%'), display_name TEXT NOT NULL DEFAULT '',
      active INTEGER NOT NULL CHECK(active IN (0,1)), UNIQUE(alert_rule_id,phone_e164))""",
    f"""CREATE TABLE IF NOT EXISTS cash_permission_profiles (
      id TEXT NOT NULL PRIMARY KEY CHECK({U('id')}), name TEXT NOT NULL UNIQUE, description TEXT NOT NULL DEFAULT '',
      active INTEGER NOT NULL CHECK(active IN (0,1)), created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    f"""CREATE TABLE IF NOT EXISTS cash_permission_profile_items (
      id TEXT NOT NULL PRIMARY KEY CHECK({U('id')}), profile_id TEXT NOT NULL REFERENCES cash_permission_profiles(id) ON DELETE CASCADE,
      permission_code TEXT NOT NULL CHECK(permission_code LIKE 'CAJA.%'), UNIQUE(profile_id,permission_code))""",
    f"""CREATE TABLE IF NOT EXISTS cash_in_app_recipients (
      id TEXT NOT NULL PRIMARY KEY CHECK({U('id')}), alert_rule_id TEXT NOT NULL REFERENCES cash_alert_rules(id) ON DELETE CASCADE,
      user_id TEXT NOT NULL CHECK({U('user_id')}), display_name TEXT NOT NULL DEFAULT '',
      active INTEGER NOT NULL CHECK(active IN (0,1)), UNIQUE(alert_rule_id,user_id))""",
    f"""CREATE TABLE IF NOT EXISTS cash_email_recipients (
      id TEXT NOT NULL PRIMARY KEY CHECK({U('id')}), alert_rule_id TEXT NOT NULL REFERENCES cash_alert_rules(id) ON DELETE CASCADE,
      email TEXT NOT NULL CHECK(email LIKE '%_@_%._%'), display_name TEXT NOT NULL DEFAULT '',
      active INTEGER NOT NULL CHECK(active IN (0,1)), UNIQUE(alert_rule_id,email))""",
    f"""CREATE TABLE IF NOT EXISTS cash_notification_jobs (
      id TEXT NOT NULL PRIMARY KEY CHECK({U('id')}), source_event_id TEXT NOT NULL REFERENCES cash_domain_events(id),
      alert_rule_id TEXT NOT NULL REFERENCES cash_alert_rules(id), channel TEXT NOT NULL CHECK(channel IN ('IN_APP','WHATSAPP','EMAIL')),
      recipient TEXT NOT NULL CHECK(trim(recipient)<>''), severity TEXT NOT NULL CHECK(severity IN ('INFO','WARNING','CRITICAL')),
      title TEXT NOT NULL CHECK(trim(title)<>''), body TEXT NOT NULL CHECK(trim(body)<>''),
      status TEXT NOT NULL CHECK(status IN ('PENDING','PROCESSING','DELIVERED','RETRY','SKIPPED','DEAD_LETTER')),
      attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count>=0), next_attempt_at TEXT,
      last_error TEXT, created_at TEXT NOT NULL, delivered_at TEXT,
      UNIQUE(source_event_id,channel,recipient))""",
    f"""CREATE TABLE IF NOT EXISTS cash_notification_attempts (
      id TEXT NOT NULL PRIMARY KEY CHECK({U('id')}), job_id TEXT NOT NULL REFERENCES cash_notification_jobs(id),
      attempt_no INTEGER NOT NULL CHECK(attempt_no>0), status TEXT NOT NULL CHECK(status IN ('DELIVERED','RETRY','SKIPPED','DEAD_LETTER')),
      provider_reference TEXT, error_code TEXT, attempted_at TEXT NOT NULL, UNIQUE(job_id,attempt_no))""",
    f"""CREATE TABLE IF NOT EXISTS cash_in_app_alerts (
      id TEXT NOT NULL PRIMARY KEY CHECK({U('id')}), notification_job_id TEXT NOT NULL UNIQUE REFERENCES cash_notification_jobs(id),
      recipient_user_id TEXT NOT NULL CHECK({U('recipient_user_id')}), severity TEXT NOT NULL CHECK(severity IN ('INFO','WARNING','CRITICAL')),
      title TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL, read_at TEXT)""",
)

INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_cash_settings_resolution ON cash_settings(setting_key,scope_type,scope_id,effective_from,effective_to)",
    "CREATE INDEX IF NOT EXISTS idx_cash_denominations_active ON cash_denominations(currency_code,active,sort_order)",
    "CREATE INDEX IF NOT EXISTS idx_cash_payment_methods_active ON cash_payment_methods(active,code)",
    "CREATE INDEX IF NOT EXISTS idx_cash_limits_resolution ON cash_operation_limits(operation_type,scope_type,scope_id,effective_from,effective_to)",
    "CREATE INDEX IF NOT EXISTS idx_cash_movement_reasons_active ON cash_movement_reasons(movement_type,active,effective_from,effective_to)",
    "CREATE INDEX IF NOT EXISTS idx_cash_alert_resolution ON cash_alert_rules(event_name,scope_type,scope_id,active)",
    "CREATE INDEX IF NOT EXISTS idx_cash_difference_policy_resolution ON cash_difference_policies(scope_type,scope_id,active,effective_from,effective_to)",
    "CREATE INDEX IF NOT EXISTS idx_cash_notification_dispatch ON cash_notification_jobs(status,next_attempt_at,created_at)",
    "CREATE INDEX IF NOT EXISTS idx_cash_in_app_unread ON cash_in_app_alerts(recipient_user_id,read_at,created_at)",
)


def run(connection) -> None:
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        for statement in DDL: connection.execute(statement)
        for statement in INDEXES: connection.execute(statement)
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations: raise RuntimeError(f"CASH-5 foreign-key violations: {violations}")
        connection.commit()
    except Exception:
        connection.rollback()
        raise


up = run
