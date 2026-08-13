"""Read adapter for the CASH-5 configuration projection."""
from __future__ import annotations

import json


class CashConfigurationReadRepository:
    _QUERIES = {
        "hierarchy": "SELECT id,setting_key name,setting_value value,scope_type scope,effective_from,COALESCE(effective_to,'') effective_to,'VIGENTE' status FROM cash_settings ORDER BY setting_key,scope_type",
        "validity": "SELECT id,setting_key name,setting_value value,scope_type scope,effective_from,COALESCE(effective_to,'') effective_to,CASE WHEN effective_to IS NULL THEN 'ABIERTA' ELSE 'DEFINIDA' END status FROM cash_settings ORDER BY effective_from DESC",
        "denominations": "SELECT id,display_name name,denomination_value value,currency_code scope,effective_from,COALESCE(effective_to,'') effective_to,CASE active WHEN 1 THEN 'ACTIVA' ELSE 'INACTIVA' END status FROM cash_denominations ORDER BY sort_order",
        "payment_methods": "SELECT id,display_name name,code value,CASE affects_physical_cash WHEN 1 THEN 'EFECTIVO' ELSE 'NO EFECTIVO' END scope,effective_from,COALESCE(effective_to,'') effective_to,CASE active WHEN 1 THEN 'ACTIVO' ELSE 'INACTIVO' END status FROM cash_payment_methods ORDER BY code",
        "limits": "SELECT id,operation_type name,approval_threshold||' / '||hard_cap value,scope_type scope,effective_from,COALESCE(effective_to,'') effective_to,'VIGENTE' status FROM cash_operation_limits ORDER BY operation_type",
        "alerts": "SELECT id,event_name name,severity||' '||channels_json value,scope_type scope,effective_from,COALESCE(effective_to,'') effective_to,CASE active WHEN 1 THEN 'ACTIVA' ELSE 'INACTIVA' END status FROM cash_alert_rules ORDER BY event_name",
        "whatsapp": "SELECT r.id,r.display_name name,r.phone_e164 value,a.event_name scope,a.effective_from,COALESCE(a.effective_to,'') effective_to,CASE r.active WHEN 1 THEN 'ACTIVO' ELSE 'INACTIVO' END status FROM cash_whatsapp_recipients r JOIN cash_alert_rules a ON a.id=r.alert_rule_id ORDER BY a.event_name,r.display_name",
        "permissions": "SELECT p.id,p.name,p.description value,'PERFIL' scope,p.created_at effective_from,'' effective_to,CASE p.active WHEN 1 THEN 'ACTIVO' ELSE 'INACTIVO' END status FROM cash_permission_profiles p ORDER BY p.name",
    }

    def __init__(self, connection) -> None:
        self._connection = connection

    def list_configuration_rows(self, section: str) -> list[dict]:
        sql = self._QUERIES.get(section)
        if sql is None:
            raise ValueError(f"Unknown configuration section: {section}")
        cursor = self._connection.execute(sql)
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


class CashConfigurationWriteRepository:
    """Mutation adapter for effective CASH-5 configuration catalogs.

    It deliberately does not commit; CashRegisterUnitOfWork owns the
    transaction when this repository is used from application services.
    """

    def __init__(self, connection) -> None:
        self._connection = connection

    def execute(self, sql: str, params: tuple = ()):
        return self._connection.execute(sql, params)

    def add_setting(self, *, row_id: str, setting_key: str,
                    setting_value: str, scope_type: str, scope_id: str | None,
                    effective_from: str, effective_to: str | None,
                    created_by: str) -> None:
        self.execute(
            """INSERT INTO cash_settings
            (id,setting_key,setting_value,scope_type,scope_id,effective_from,
             effective_to,created_by,created_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (row_id, setting_key, setting_value, scope_type, scope_id,
             effective_from, effective_to, created_by, effective_from),
        )

    def add_denomination(self, *, row_id: str, currency_code: str,
                         value: str, label: str, sort_order: int,
                         effective_from: str, effective_to: str | None) -> None:
        self.execute(
            """INSERT INTO cash_denominations
            (id,currency_code,denomination_value,display_name,sort_order,active,
             effective_from,effective_to)
            VALUES(?,?,?,?,?,1,?,?)""",
            (row_id, currency_code, value, label, sort_order,
             effective_from, effective_to),
        )

    def add_payment_method(self, *, row_id: str, code: str,
                           display_name: str, affects_physical_cash: bool,
                           effective_from: str, effective_to: str | None) -> None:
        self.execute(
            """INSERT INTO cash_payment_methods
            (id,code,display_name,affects_physical_cash,active,effective_from,
             effective_to)
            VALUES(?,?,?,?,1,?,?)""",
            (row_id, code, display_name, 1 if affects_physical_cash else 0,
             effective_from, effective_to),
        )

    def add_operation_limit(self, *, row_id: str, operation_type: str,
                            approval_threshold: str, hard_cap: str,
                            scope_type: str, scope_id: str | None,
                            effective_from: str, effective_to: str | None,
                            created_by: str) -> None:
        self.execute(
            """INSERT INTO cash_operation_limits
            (id,operation_type,approval_threshold,hard_cap,scope_type,scope_id,
             effective_from,effective_to,created_by)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (row_id, operation_type, approval_threshold, hard_cap, scope_type,
             scope_id, effective_from, effective_to, created_by),
        )

    def add_alert_rule(self, *, row_id: str, event_name: str,
                       severity: str, channels: tuple[str, ...],
                       scope_type: str, scope_id: str | None,
                       effective_from: str, effective_to: str | None) -> None:
        self.execute(
            """INSERT INTO cash_alert_rules
            (id,event_name,severity,channels_json,scope_type,scope_id,active,
             effective_from,effective_to)
            VALUES(?,?,?,?,?,?,1,?,?)""",
            (row_id, event_name, severity,
             json.dumps(tuple(channels), ensure_ascii=False), scope_type,
             scope_id, effective_from, effective_to),
        )

