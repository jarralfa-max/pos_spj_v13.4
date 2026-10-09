"""Read adapter for the CASH-5 configuration projection."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class CashConfigurationReadRepository:
    _QUERIES = {
        "hierarchy": "SELECT id,setting_key name,setting_value value,scope_type scope,effective_from,COALESCE(effective_to,'') effective_to,'VIGENTE' status FROM cash_settings ORDER BY setting_key,scope_type",
        "validity": "SELECT id,setting_key name,setting_value value,scope_type scope,effective_from,COALESCE(effective_to,'') effective_to,CASE WHEN effective_to IS NULL THEN 'ABIERTA' ELSE 'DEFINIDA' END status FROM cash_settings ORDER BY effective_from DESC",
        "denominations": "SELECT id,display_name name,denomination_value value,currency_code scope,effective_from,COALESCE(effective_to,'') effective_to,CASE active WHEN 1 THEN 'ACTIVA' ELSE 'INACTIVA' END status FROM cash_denominations ORDER BY sort_order",
        "payment_methods": "SELECT id,display_name name,code value,CASE affects_physical_cash WHEN 1 THEN 'EFECTIVO' ELSE 'NO EFECTIVO' END scope,effective_from,COALESCE(effective_to,'') effective_to,CASE active WHEN 1 THEN 'ACTIVO' ELSE 'INACTIVO' END status FROM cash_payment_methods ORDER BY code",
        "limits": "SELECT id,operation_type name,approval_threshold||' / '||hard_cap value,scope_type scope,effective_from,COALESCE(effective_to,'') effective_to,'VIGENTE' status FROM cash_operation_limits ORDER BY operation_type",
        "alerts": "SELECT id,event_name name,severity||' '||channels_json value,scope_type scope,effective_from,COALESCE(effective_to,'') effective_to,CASE active WHEN 1 THEN 'ACTIVA' ELSE 'INACTIVA' END status FROM cash_alert_rules ORDER BY event_name",
        "whatsapp": "SELECT r.id,r.display_name name,r.phone_e164 value,a.event_name scope,a.effective_from,COALESCE(a.effective_to,'') effective_to,CASE r.active WHEN 1 THEN 'ACTIVO' ELSE 'INACTIVO' END status FROM cash_whatsapp_recipients r JOIN cash_alert_rules a ON a.id=r.alert_rule_id ORDER BY a.event_name,r.display_name",
        # Destinatarios de avisos (CASH-26 bloque 2): en el sistema y WhatsApp.
        "recipients": "SELECT r.id,r.display_name name,'En el sistema' value,a.event_name scope,a.effective_from,COALESCE(a.effective_to,'') effective_to,CASE r.active WHEN 1 THEN 'ACTIVO' ELSE 'INACTIVO' END status FROM cash_in_app_recipients r JOIN cash_alert_rules a ON a.id=r.alert_rule_id UNION ALL SELECT r.id,r.display_name,'WhatsApp '||r.phone_e164,a.event_name,a.effective_from,COALESCE(a.effective_to,''),CASE r.active WHEN 1 THEN 'ACTIVO' ELSE 'INACTIVO' END FROM cash_whatsapp_recipients r JOIN cash_alert_rules a ON a.id=r.alert_rule_id ORDER BY 4,2",
        "permissions": "SELECT p.id,p.name,p.description value,'PERFIL' scope,p.created_at effective_from,'' effective_to,CASE p.active WHEN 1 THEN 'ACTIVO' ELSE 'INACTIVO' END status FROM cash_permission_profiles p ORDER BY p.name",
        "reasons": "SELECT id,display_name name,code||CASE requires_authorization WHEN 1 THEN ' (requiere autorizacion)' ELSE '' END value,movement_type scope,effective_from,COALESCE(effective_to,'') effective_to,CASE active WHEN 1 THEN 'ACTIVO' ELSE 'INACTIVO' END status FROM cash_movement_reasons ORDER BY movement_type,display_name",
        "tolerances": "SELECT id,'Tolerancia '||tolerance_amount||' / critica '||critical_threshold name,recurrence_threshold||' en '||recurrence_window_days||' dias, '||channels_json value,scope_type scope,effective_from,COALESCE(effective_to,'') effective_to,CASE active WHEN 1 THEN 'VIGENTE' ELSE 'INACTIVA' END status FROM cash_difference_policies ORDER BY effective_from DESC",
    }

    def __init__(self, connection) -> None:
        self._connection = connection

    def list_configuration_rows(self, section: str) -> list[dict]:
        sql = self._QUERIES.get(section)
        if sql is None:
            raise ValueError(f"Unknown configuration section: {section}")
        cursor = self._connection.execute(sql)
        columns = [item[0] for item in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        # Una fila con vigencia cerrada ya no aplica, diga lo que diga `active`.
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for row in rows:
            if row.get("effective_to") and str(row["effective_to"]) <= now:
                row["status"] = "VENCIDA"
        return rows

    def alert_rule_options(self) -> list[dict]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = self._connection.execute(
            """SELECT id,event_name,channels_json FROM cash_alert_rules
            WHERE active=1 AND effective_from<=? AND (effective_to IS NULL OR effective_to>?)
            ORDER BY event_name""", (now, now)).fetchall()
        return [{"id": r[0], "event_name": r[1], "channels": tuple(json.loads(r[2]))}
                for r in rows]

    def user_options(self) -> list[dict]:
        rows = self._connection.execute(
            """SELECT id,COALESCE(NULLIF(trim(nombre),''),usuario) FROM usuarios
            WHERE activo=1 ORDER BY 2""").fetchall()
        return [{"id": r[0], "name": r[1]} for r in rows]


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

    #: Tablas de destinatarios por canal: (tabla, columna de la dirección).
    _RECIPIENTS = {
        "IN_APP": ("cash_in_app_recipients", "user_id"),
        "WHATSAPP": ("cash_whatsapp_recipients", "phone_e164"),
        "EMAIL": ("cash_email_recipients", "email"),
    }

    def supersede_alert_rule(self, *, new_rule_id: str, event_name: str, scope_type: str,
                             scope_id: str | None, effective_from: str) -> None:
        """Cierra la regla vigente del mismo evento y alcance, y le pasa sus
        destinatarios activos a la nueva: cambiar la severidad o los canales
        no debe dejar el aviso sin nadie que lo reciba."""
        previas = [row[0] for row in self.execute(
            """SELECT id FROM cash_alert_rules
            WHERE event_name=? AND scope_type=? AND scope_id IS ? AND id<>?
              AND effective_from<=? AND (effective_to IS NULL OR effective_to>?)""",
            (event_name, scope_type, scope_id, new_rule_id, effective_from,
             effective_from)).fetchall()]
        for previous_id in previas:
            self.execute("UPDATE cash_alert_rules SET effective_to=? WHERE id=?",
                         (effective_from, previous_id))
            for table, column in self._RECIPIENTS.values():
                for address, name in self.execute(
                        f"SELECT {column},display_name FROM {table}"
                        " WHERE alert_rule_id=? AND active=1", (previous_id,)).fetchall():
                    self.execute(
                        f"""INSERT INTO {table} (id,alert_rule_id,{column},display_name,active)
                        VALUES(?,?,?,?,1) ON CONFLICT(alert_rule_id,{column}) DO NOTHING""",
                        (new_uuid(), new_rule_id, address, name))

    def add_alert_recipient(self, *, row_id: str, alert_rule_id: str, channel: str,
                            address: str, display_name: str) -> str:
        """Alta (o reactivación) de un destinatario; devuelve el id de la fila."""
        table, column = self._RECIPIENTS[channel]
        self.execute(
            f"""INSERT INTO {table} (id,alert_rule_id,{column},display_name,active)
            VALUES(?,?,?,?,1)
            ON CONFLICT(alert_rule_id,{column}) DO UPDATE
            SET active=1,display_name=excluded.display_name""",
            (row_id, alert_rule_id, address, display_name))
        return str(self.execute(
            f"SELECT id FROM {table} WHERE alert_rule_id=? AND {column}=?",
            (alert_rule_id, address)).fetchone()[0])

    def deactivate_alert_recipient(self, row_id: str) -> bool:
        changed = 0
        for table, _column in self._RECIPIENTS.values():
            changed += self.execute(
                f"UPDATE {table} SET active=0 WHERE id=? AND active=1", (row_id,)).rowcount
        return changed == 1

    def active_alert_rule(self, rule_id: str, *, at: str):
        row = self.execute(
            """SELECT id,event_name,channels_json FROM cash_alert_rules
            WHERE id=? AND active=1 AND effective_from<=?
              AND (effective_to IS NULL OR effective_to>?)""", (rule_id, at, at)).fetchone()
        return None if row is None else {
            "id": row[0], "event_name": row[1], "channels": tuple(json.loads(row[2]))}

    def user_display_name(self, user_id: str) -> str | None:
        row = self.execute(
            "SELECT COALESCE(NULLIF(trim(nombre),''), usuario) FROM usuarios"
            " WHERE id=? AND activo=1", (user_id,)).fetchone()
        return None if row is None else str(row[0])

    def add_movement_reason(self, *, row_id: str, code: str, display_name: str,
                            movement_type: str, requires_authorization: bool,
                            effective_from: str, effective_to: str | None) -> None:
        self.execute(
            """INSERT INTO cash_movement_reasons
            (id,code,display_name,movement_type,requires_authorization,active,
             effective_from,effective_to)
            VALUES(?,?,?,?,?,1,?,?)""",
            (row_id, code, display_name, movement_type, 1 if requires_authorization else 0,
             effective_from, effective_to),
        )

    def add_difference_policy(self, *, row_id: str, tolerance: str,
                              critical_threshold: str, recurrence_window_days: int,
                              recurrence_threshold: int, channels: tuple[str, ...],
                              scope_type: str, scope_id: str | None,
                              effective_from: str, effective_to: str | None) -> None:
        self.execute(
            """INSERT INTO cash_difference_policies
            (id,tolerance_amount,critical_threshold,recurrence_window_days,
             recurrence_threshold,channels_json,scope_type,scope_id,active,
             effective_from,effective_to)
            VALUES(?,?,?,?,?,?,?,?,1,?,?)""",
            (row_id, tolerance, critical_threshold, recurrence_window_days,
             recurrence_threshold, json.dumps(list(channels)), scope_type, scope_id,
             effective_from, effective_to),
        )

    # Una fila nueva REEMPLAZA a la vigente del mismo concepto: se cierra la anterior
    # en lugar de dejar dos vigentes (dos denominaciones de $500 se contarían doble).
    def close_previous_denomination(self, *, currency_code: str, value: str,
                                    effective_from: str) -> None:
        self.execute(
            """UPDATE cash_denominations SET effective_to=?
            WHERE currency_code=? AND CAST(denomination_value AS NUMERIC)=CAST(? AS NUMERIC)
              AND effective_from<? AND (effective_to IS NULL OR effective_to>?)""",
            (effective_from, currency_code, value, effective_from, effective_from))

    def close_previous_limit(self, *, operation_type: str, scope_type: str,
                             scope_id: str | None, effective_from: str) -> None:
        self.execute(
            """UPDATE cash_operation_limits SET effective_to=?
            WHERE operation_type=? AND scope_type=? AND scope_id IS ?
              AND effective_from<? AND (effective_to IS NULL OR effective_to>?)""",
            (effective_from, operation_type, scope_type, scope_id, effective_from,
             effective_from))

    def close_previous_reason(self, *, code: str, effective_from: str) -> None:
        self.execute(
            """UPDATE cash_movement_reasons SET effective_to=?
            WHERE code=? AND effective_from<? AND (effective_to IS NULL OR effective_to>?)""",
            (effective_from, code, effective_from, effective_from))

    def close_previous_difference_policy(self, *, scope_type: str, scope_id: str | None,
                                         effective_from: str) -> None:
        self.execute(
            """UPDATE cash_difference_policies SET effective_to=?
            WHERE scope_type=? AND scope_id IS ?
              AND effective_from<? AND (effective_to IS NULL OR effective_to>?)""",
            (effective_from, scope_type, scope_id, effective_from, effective_from))

    _DEACTIVATABLE = frozenset({
        "cash_denominations", "cash_payment_methods", "cash_operation_limits",
        "cash_alert_rules", "cash_movement_reasons", "cash_difference_policies",
    })

    def end_validity(self, *, table: str, row_id: str, at: str) -> bool:
        if table not in self._DEACTIVATABLE:
            raise ValueError("Tabla de configuracion no administrable")
        cursor = self.execute(
            f"""UPDATE {table} SET effective_to=?
            WHERE id=? AND effective_from<? AND (effective_to IS NULL OR effective_to>?)""",
            (at, row_id, at, at))
        return cursor.rowcount == 1
