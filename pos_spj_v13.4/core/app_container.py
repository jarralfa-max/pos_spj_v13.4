
# core/app_container.py
import sqlite3
import logging

# --- IMPORTACIONES DE REPOSITORIOS (CAPA 1) ---
from repositories.config_repository import ConfigRepository
from repositories.security_repository import SecurityRepository
from repositories.auth_repository import AuthRepository
from repositories.inventory_repository import InventoryRepository
from repositories.recipe_repository import RecipeRepository
from repositories.finance_repository import FinanceRepository
from repositories.sales_repository import SalesRepository
from repositories.purchase_repository import PurchaseRepository
# Si tienes estos, descoméntalos; si no, coméntalos para que no den error:
from repositories.promotion_repository import PromotionRepository
from repositories.bi_repository import BIRepository
from repositories.sync_repository import SyncRepository

# --- IMPORTACIONES DE SERVICIOS (CAPAS 2 Y 3) ---
from core.services.audit_service import AuditService
from repositories.audit_repository import AuditRepository
from core.services.config_service import ConfigService
from core.services.feature_flag_service import FeatureFlagService
from core.services.security_service import SecurityService
from core.services.auth_service import AuthService

from core.services.inventory_service import InventoryService
from core.services.finance_service import FinanceService
from core.services.loyalty_service import LoyaltyService
from core.services.production_service import ProductionService
from core.engines.template_engine import TicketTemplateEngine
from core.services.whatsapp_service import WhatsAppService
from core.services.sales_service import SalesService
# Si tienes estos, descoméntalos; si no, coméntalos:
from core.engines.promotion_engine import PromotionEngine
from core.services.sync_service import SyncService
from core.services.purchase_service import PurchaseService

logger = logging.getLogger(__name__)

class AppContainer:
    """
    Contenedor de Inyección de Dependencias (Enterprise Architecture).
    Inicializa todos los motores en el orden estricto necesario.
    """
    def __init__(self, db_path: str):
        # v13.4: SessionContext — fuente única de verdad para user/branch/permisos
        from core.session_context import SessionContext
        self.session = SessionContext()

        # sucursal_id dinámico — proxy al SessionContext (compat con módulos existentes)
        self.sucursal_id: int = 1
        self.sucursal_nombre: str = "Principal"
        logger.info("Inicializando AppContainer...")

        # 0. CONEXIÓN A BASE DE DATOS
        # Usar el pool canónico con WAL, busy_timeout=5000ms y foreign_keys=ON.
        # Esto reemplaza el sqlite3.connect() desnudo que no tenía ninguna de esas garantías.
        from core.db.connection import set_db_path, get_connection
        self.db_path = db_path
        set_db_path(db_path)          # registra la ruta en el módulo canónico
        self.db = get_connection()    # WAL + NORMAL sync + FK + busy_timeout

        # =========================================================
        # CAPA 1: REPOSITORIOS (Acceso crudo a las tablas)
        # =========================================================
        self.config_repo = ConfigRepository(self.db)
        self.security_repo = SecurityRepository(self.db)
        self.auth_repo = AuthRepository(self.db)
        self.inventory_repo = InventoryRepository(self.db)
        self.recipe_repo = RecipeRepository(self.db)
        self.finance_repo = FinanceRepository(self.db)
        self.sales_repo = SalesRepository(self.db)
        self.purchase_repo = PurchaseRepository(self.db)
        
        # Opcionales (depende de qué tan avanzados vayan tus módulos)
        self.promo_repo = PromotionRepository(self.db)
        self.bi_repo = BIRepository(self.db)
        self.sync_repo = SyncRepository(self.db)
        from repositories.cliente_repository import ClienteRepository
        self.cliente_repo = ClienteRepository(self.db)

        # MercadoPago (pagos digitales con link)
        try:
            from services.mercado_pago_service import MercadoPagoService
            self.mercado_pago_service = MercadoPagoService(conn=self.db)
        except Exception as _e:
            self.mercado_pago_service = None
            import logging; logging.getLogger(__name__).debug("MercadoPago no cargado: %s", _e)

        # =========================================================
        # CAPA 2: SERVICIOS FUNDAMENTALES (Auditoría, Seguridad, Config)
        # =========================================================
        # El Auditor va primero porque todos lo usan para registrar sus acciones
        self.audit_repo    = AuditRepository(self.db)
        self.audit_service = AuditService(self.audit_repo)
        
        # Configuraciones globales y Flags
        self.config_service = ConfigService(self.config_repo)
        from repositories.feature_flag_repository import FeatureFlagRepository
        self.feature_flag_repo = FeatureFlagRepository(self.db)
        self.feature_flag_service = FeatureFlagService(self.feature_flag_repo)
        
        # Seguridad y control de accesos
        self.security_service = SecurityService(self.security_repo)
        
        # Autenticación de Usuarios (Ya tiene todo inyectado correctamente)
        self.auth_service = AuthService(
            auth_repo=self.auth_repo,
            security_service=self.security_service,
            audit_service=self.audit_service
        )

        ## =========================================================
        # CAPA 3: SERVICIOS DE NEGOCIO (Los motores del ERP)
        # =========================================================
        self.inventory_service = InventoryService(self.db, self.inventory_repo)
        self.inventory_service.audit_service = self.audit_service # Inyectar auditoría manualmente
        
        self.finance_service = FinanceService(self.db) # Solo recibe 1 parámetro
        self.loyalty_service = LoyaltyService(self.db)  # module_config set below
        self.production_service = ProductionService(self.db, self.inventory_service)
        
        # Motores visuales y de comunicación
        self.ticket_template_engine = TicketTemplateEngine(db_conn=self.db)
        self.whatsapp_service = WhatsAppService(
            conn=self.db,                      # Cola persistente + config desde BD
            feature_service=self.feature_flag_service
        )
        # Arrancar worker de cola en background (daemon — no bloquea UI)
        self.whatsapp_service.start_worker()

        # ── NotificationService — capa de enrutamiento de notificaciones ──────
        from core.services.notification_service import NotificationService
        self.notification_service = NotificationService(
            db                = self.db,
            whatsapp_service  = self.whatsapp_service,
            sucursal_id       = self.sucursal_id,
        )

        # Servidor webhook para mensajes entrantes (Rasa + pedidos WhatsApp)
        # Se instancia aquí pero se inicia desde main.py si está habilitado
        from core.services.whatsapp_service import WhatsAppWebhookServer
        self.whatsapp_webhook = WhatsAppWebhookServer(
            port=8767,
            whatsapp_svc=self.whatsapp_service
        )
        
        # Opcionales
        self.promotion_engine = PromotionEngine(self.promo_repo)
        self.sync_service = SyncService(self.sync_repo)
        self.purchase_service = PurchaseService(self.db, self.purchase_repo, self.inventory_service, self.finance_service)

        # =========================================================
        # CAPA 4: EL ORQUESTADOR PRINCIPAL (Ventas)
        # =========================================================
        # Servicio de devoluciones / reversiones (cancel_sale, refund_items, credit_note)
        # SalesReversalService usa db.transaction() y db.conn — lo envolvemos en el shim
        from core.services.sales_reversal_service import SalesReversalService
        from core.db.connection import _DatabaseShim
        _db_shim = _DatabaseShim(self.db_path)
        self.sales_reversal_service = SalesReversalService(
            db=_db_shim, branch_id=1
        )

        from core.services.pricing_service import PricingService
        self.pricing_service = PricingService(self.db)

        from core.services.moneda_service import MonedaService
        self.moneda_service = MonedaService(self.db)

        self.sales_service = SalesService(
            db_conn=self.db,
            sales_repo=self.sales_repo,
            recipe_repo=self.recipe_repo,
            inventory_service=self.inventory_service,
            finance_service=self.finance_service,
            loyalty_service=self.loyalty_service,
            promotion_engine=self.promotion_engine,
            sync_service=None,
            ticket_template_engine=self.ticket_template_engine,
            whatsapp_service=self.whatsapp_service,
            config_service=self.config_service,
            feature_flag_service=self.feature_flag_service,
            pricing_service=self.pricing_service,
            growth_engine=getattr(self, 'growth_engine', None),
            notification_service=getattr(self, 'notification_service', None),
        )
        
        # ── Servicios adicionales (v12) ───────────────────────────────────
        from core.services.hardware_service import HardwareService
        self.hardware_service = HardwareService(self.db)

        # v13.4 Fase 1: ModuleConfig (toggles globales) — antes de otros servicios
        from core.module_config import ModuleConfig
        self.module_config = ModuleConfig(self.db)

        # v13.4 Fase 3: TreasuryService (Tesorería Central / CAPEX)
        from core.services.treasury_service import TreasuryService
        self.treasury_service = TreasuryService(self.db, self.module_config)

        from core.services.hr_rule_engine import HRRuleEngine
        self.hr_rule_engine = HRRuleEngine(
            db_conn=self.db,
            module_config=self.module_config,
        )

        from core.services.rrhh_service import RRHHService
        self.rrhh_service = RRHHService(
            db_conn=self.db,
            treasury_service=self.treasury_service,
            whatsapp_service=self.whatsapp_service,
            template_engine=None,
            hr_rule_engine=self.hr_rule_engine,
        )

        from core.services.bi_service import BIService
        self.bi_service = BIService(self.bi_repo, self.feature_flag_service)

        from core.services.theme_service import ThemeService
        self.theme_service = ThemeService(self.db)

        # v13.4 Fase 1: PrinterService unificado
        from core.services.printer_service import PrinterService
        self.printer_service = PrinterService(self.db, self.module_config)

        # v13.4 Fase 1.5: QRParserService (separar client_id de nombre)
        from core.services.qr_parser_service import QRParserService
        self.qr_parser = QRParserService(self.db)

        # v13.4 Fase 2: Conectar module_config a LoyaltyService
        self.loyalty_service._module_config = self.module_config

        # v13.4 Fase 4: AlertEngine (alertas inteligentes)
        from core.services.alert_engine import AlertEngine
        self.alert_engine = AlertEngine(
            db_conn=self.db,
            treasury_service=self.treasury_service,
            loyalty_service=self.loyalty_service,
            alertas_service=getattr(self, 'alertas_service', None),
            module_config=self.module_config)

        # v13.4 Fase 5: DecisionEngine (sugerencias — NO ejecuta)
        from core.services.decision_engine import DecisionEngine
        self.decision_engine = DecisionEngine(
            db_conn=self.db,
            treasury_service=self.treasury_service,
            loyalty_service=self.loyalty_service,
            alert_engine=self.alert_engine,
            module_config=self.module_config)

        # v13.4 Fase 6: ActionableForecastService
        from core.services.actionable_forecast import ActionableForecastService
        self.actionable_forecast = ActionableForecastService(
            db_conn=self.db,
            treasury_service=self.treasury_service,
            module_config=self.module_config)

        # v13.4 Fase 7: FinancialSimulator
        from core.services.financial_simulator import FinancialSimulator
        self.financial_simulator = FinancialSimulator(
            db_conn=self.db,
            treasury_service=self.treasury_service,
            module_config=self.module_config)

        # v13.4 Fase 8: AIAdvisor (DeepSeek/Ollama — opcional)
        from core.services.ai_advisor import AIAdvisor
        self.ai_advisor = AIAdvisor(
            db_conn=self.db,
            treasury_service=self.treasury_service,
            alert_engine=self.alert_engine,
            decision_engine=self.decision_engine,
            module_config=self.module_config)

        # v13.4 Fase 9: CEODashboard
        from core.services.ceo_dashboard import CEODashboard
        self.ceo_dashboard = CEODashboard(
            db_conn=self.db,
            treasury_service=self.treasury_service,
            alert_engine=self.alert_engine,
            decision_engine=self.decision_engine,
            actionable_forecast=self.actionable_forecast,
            simulator=self.financial_simulator,
            ai_advisor=self.ai_advisor,
            loyalty_service=self.loyalty_service)

        # v13.4 Fase 10: FranchiseManager
        from core.services.franchise_manager import FranchiseManager
        self.franchise_manager = FranchiseManager(
            db_conn=self.db,
            treasury_service=self.treasury_service,
            module_config=self.module_config)

        # v13.4 Fase 11: ExpansionAnalyzer
        from core.services.expansion_analyzer import ExpansionAnalyzer
        self.expansion_analyzer = ExpansionAnalyzer(
            db_conn=self.db,
            treasury_service=self.treasury_service,
            simulator=self.financial_simulator,
            franchise_manager=self.franchise_manager,
            ai_advisor=self.ai_advisor,
            module_config=self.module_config)

        from core.services.cotizacion_service import CotizacionService
        self.cotizacion_service = CotizacionService(
            conn=self.db, sucursal_id=self.sucursal_id, usuario="Sistema"
        )

        # v13.4 FASE 1: ERPApplicationService — punto único de escritura
        from core.services.erp_application_service import ERPApplicationService
        self.app_service = ERPApplicationService(
            db_conn=self.db,
            inventory_service=self.inventory_service,
            treasury_service=self.treasury_service,
            loyalty_service=self.loyalty_service,
            sucursal_id=self.sucursal_id)

        # Notificar backup_engine la ruta real de la BD
        try:
            from modulos.sistema import backup_engine as _be
            _be.set_db_path(self.db_path)
        except Exception:
            pass

        from core.services.comisiones_service import ComisionesService
        self.comisiones_service = ComisionesService(self.db)

        from core.services.anticipo_service import AnticipoCotizacionService
        self.anticipo_service = AnticipoCotizacionService(self.db)

        # ── v13.1: Casos de uso (capa de orquestación) ───────────────────────
        try:
            from core.use_cases.venta import ProcesarVentaUC
            from core.use_cases.pedido_wa import ProcesarPedidoWAUC
            from core.use_cases.inventario import GestionarInventarioUC
            self.uc_venta     = ProcesarVentaUC.desde_container(self)
            self.uc_pedido_wa = ProcesarPedidoWAUC.desde_container(self)
            self.uc_inventario = GestionarInventarioUC.desde_container(self)
        except Exception as _uc_err:
            import logging as _luc
            _luc.getLogger("spj.container").warning("Use cases: %s", _uc_err)
            self.uc_venta = self.uc_pedido_wa = self.uc_inventario = None

        # ── v13.4: Use Case producción cárnica ──────────────────────────────
        try:
            from core.use_cases.produccion import GestionarProduccionUC
            self.uc_produccion = GestionarProduccionUC.desde_container(self)
        except Exception as _uc_p:
            self.uc_produccion = None
            logger.debug("uc_produccion: %s", _uc_p)

        # ── v13.4: EventLogger para sync (usado por handlers del EventBus) ──
        try:
            from sync.event_logger import EventLogger
            self.event_logger = EventLogger(self.db)
        except Exception as _el_err:
            self.event_logger = None
            logger.debug("event_logger: %s", _el_err)

        from core.services.cfdi_service import CFDIService
        self.cfdi_service = CFDIService(self.db)

        # ── Enterprise engines (lazy-registered) ─────────────────────────────
        try:
            from core.services.enterprise.report_engine_v2 import ReportEngineV2
            self.report_engine = ReportEngineV2(self.db)
        except Exception as _e:
            self.report_engine = None
            import logging as _lr; _lr.getLogger("spj.container").debug("ReportEngineV2: %s", _e)

        try:
            from core.services.enterprise.demand_forecasting import DemandForecastingEngine
            self.forecast_engine = DemandForecastingEngine(self.db)
        except Exception as _e:
            self.forecast_engine = None
            import logging as _lf; _lf.getLogger("spj.container").debug("ForecastEngine: %s", _e)

        # Wire bot_pedidos container reference (so bot can use UC)
        try:
            from services.bot_pedidos import BotPedidosWA
            BotPedidosWA._default_container = self  # class-level ref for new instances
        except Exception:
            pass

        # Wire EventBus handlers
        try:
            self._wire_event_bus()
        except Exception as _e:
            import logging as _l2
            _l2.getLogger("spj.container").warning("_wire_event_bus: %s", _e)

        from core.services.happy_hour_service import HappyHourService
        self.happy_hour_service = HappyHourService(
            db_conn=self.db,
            whatsapp_service=self.whatsapp_service,
            sucursal_id=self.sucursal_id
        )

        # Wire kitchen printer and comisiones to sales_service
        try:
            self.sales_service._hw_svc = self.hardware_service
            self.sales_service._comisiones_svc = self.comisiones_service
            self.sales_service._happy_hour_svc = self.happy_hour_service
        except Exception:
            pass

                # ── EventBus: conectar handlers de refresh tras cada venta ────────────
        # Esto hace que inventario, BI y reportes se recarguen automáticamente
        # sin que el cajero tenga que navegar y volver.
        from core.events.event_bus import get_bus, VENTA_COMPLETADA, STOCK_BAJO_MINIMO
        from security.rbac import inicializar_rbac
        bus = get_bus()
        bus.subscribe(
            VENTA_COMPLETADA,
            lambda p: logger.debug("VENTA_COMPLETADA bus: folio=%s", p.get('folio')),
            label="container.log_venta", priority=0
        )
        # Invalidar caché BI tras cada venta (bi_service registrado después)
        bus.subscribe(
            VENTA_COMPLETADA,
            lambda p: (
                getattr(getattr(self, 'bi_service', None), 'invalidar_cache', lambda *a: None)
                (p.get('branch_id', 1))
            ),
            label="bi.cache_invalidate", priority=-1
        )
        # Sembrar RBAC (roles/permisos) si la BD está recién creada
        try:
            inicializar_rbac(self.db)
        except Exception as e:
            logger.warning("inicializar_rbac: %s", e)

        # ── SchedulerService con alertas + backup automático ────────────────
        from core.services.scheduler_service import SchedulerService
        from core.db.connection import get_connection  # AÑADIR ESTA IMPORTACIÓN
        
        # PASAR EL conn_factory AL CONSTRUCTOR
        self.scheduler_service = SchedulerService(conn_factory=lambda: get_connection(self.db_path))
        self._configurar_scheduler()
        self.scheduler_service.start()

        # ── Growth Engine ──────────────────────────────────────────────
        try:
            from modulos.growth_engine import GrowthEngine
            self.growth_engine = GrowthEngine(
                db=self.db,
                sucursal_id=1,
                whatsapp_service=self.whatsapp_service,
            )
        except Exception as _ge:
            self.growth_engine = None
            logger.warning("GrowthEngine no inicializado: %s", _ge)

        # ── DiscountGuard (motor financiero de descuentos) ────────────
        try:
            from core.services.discount_guard import DiscountGuard
            self.discount_guard = DiscountGuard(self.db)
        except Exception as _dg:
            self.discount_guard = None
            logger.debug("DiscountGuard: %s", _dg)

        logger.info("✅ AppContainer inicializado con éxito. Todos los motores en línea.")

    def _configurar_scheduler(self) -> None:
        """Registra tareas periódicas: alertas (5 min) + backup (3am)."""
        from core.services.alertas_service import AlertasService
        from modulos.sistema.backup_engine import crear_backup
        import logging as _log

        alertas_svc = AlertasService(self.db, sucursal_id=self.sucursal_id)
        alertas_svc.notification_service = self.notification_service

        def _run_alertas():
            try:
                alertas_svc.run_checks()
                # Propagar alertas de stock al NotificationService
                productos_bajo = self.db.execute(
                    "SELECT nombre, existencia, stock_minimo, unidad "
                    "FROM productos WHERE activo=1 AND existencia<=COALESCE(stock_minimo,5)"
                ).fetchall()
                if productos_bajo:
                    self.notification_service.notificar_stock_bajo(
                        [dict(p) for p in productos_bajo], sucursal_id=self.sucursal_id
                    )
            except Exception as e:
                _log.getLogger("spj.scheduler").warning("alertas: %s", e)
            # v13.4 Fase 4: AlertEngine (checks financieros e inteligentes)
            try:
                if hasattr(self, 'alert_engine') and self.alert_engine.enabled:
                    self.alert_engine.run_all_checks(self.sucursal_id)
            except Exception as e:
                _log.getLogger("spj.scheduler").debug("alert_engine: %s", e)

        def _run_backup():
            try:
                # Usar backup incremental (no bloquea la BD)
                try:
                    from modulos.sistema.backup_engine import crear_backup_incremental
                    ruta = crear_backup_incremental(prefijo="auto")
                except Exception:
                    ruta = crear_backup(prefijo="auto")
                _log.getLogger("spj.scheduler").info("Backup automático: %s", ruta)
            except Exception as e:
                _log.getLogger("spj.scheduler").error("Backup fallido: %s", e)
                try:
                    self.notification_service.notificar_backup_fallido(str(e))
                except Exception:
                    pass

        self.scheduler_service.registrar_defaults()
        def _run_depreciacion():
            """Corre el día 1 de cada mes — aplica depreciación a activos."""
            from datetime import datetime as _dt
            if _dt.now().day != 1: return
            try:
                from modulos.activos import calcular_depreciacion_mensual
                results = calcular_depreciacion_mensual(self.db, self.sucursal_id)
                if results:
                    _log.getLogger("spj.scheduler").info(
                        "Depreciacion mensual: %d activos", len(results))
            except Exception as _de:
                _log.getLogger("spj.scheduler").warning("depreciacion: %s", _de)

        self.scheduler_service.registrar(
            "alertas_check", _run_alertas, intervalo_seg=300   # cada 5 min
        )
        self.scheduler_service.registrar(
            "depreciacion_activos", _run_depreciacion, intervalo_seg=86400  # diario
        )

        # This file is injected into app_container.py
        # Escalación pedidos WA + recordatorios órdenes cotización

        def _check_escalacion_pedidos():
            try:
                def get_min(clave, default):
                    try:
                        row = self.db.execute(
                            "SELECT valor FROM configuraciones WHERE clave=?", (clave,)
                        ).fetchone()
                        return int(row[0]) if row else default
                    except Exception:
                        return default

                min1 = get_min('wa_escalacion_min_1', 5)
                min2 = get_min('wa_escalacion_min_2', 15)
                min3 = get_min('wa_escalacion_min_3', 30)

                pedidos = self.db.execute(
                    "SELECT id, numero_whatsapp, cliente_nombre, total,"
                    " CAST((julianday('now') - julianday(fecha)) * 1440 AS INTEGER) as mins,"
                    " notificado_gerente, respuesta_auto_enviada"
                    " FROM pedidos_whatsapp"
                    " WHERE estado IN ('nuevo','confirmado') AND leido=1"
                ).fetchall()

                for p in pedidos:
                    pid, tel, nombre, total, mins, notif_g, resp_auto = (
                        p[0], p[1], p[2], p[3], int(p[4] or 0), p[5], p[6])

                    if mins >= min2 and not notif_g:
                        try:
                            tel_g = self.db.execute(
                                "SELECT valor FROM configuraciones WHERE clave='wa_escalacion_tel_gerente'"
                            ).fetchone()
                            if tel_g and tel_g[0]:
                                msg = (f"Pedido #{pid} de {nombre or tel} "
                                       f"lleva {mins} min sin atender. Total: ${float(total or 0):.2f}.")
                                self.whatsapp_service.send_message(phone_number=tel_g[0], message=msg)
                            self.db.execute(
                                "UPDATE pedidos_whatsapp SET notificado_gerente=1 WHERE id=?", (pid,))
                            try: self.db.commit()
                            except Exception: pass
                        except Exception as _e:
                            import logging; logging.getLogger("spj.scheduler").debug("escal_gerente: %s", _e)

                    if mins >= min3 and not resp_auto:
                        try:
                            nombre_c = nombre or "cliente"
                            msg = f"Hola {nombre_c}, tu pedido está siendo procesado. Te confirmamos a la brevedad."
                            self.whatsapp_service.send_message(phone_number=tel, message=msg)
                            self.db.execute(
                                "UPDATE pedidos_whatsapp SET respuesta_auto_enviada=1 WHERE id=?", (pid,))
                            try: self.db.commit()
                            except Exception: pass
                        except Exception as _e:
                            import logging; logging.getLogger("spj.scheduler").debug("escal_auto: %s", _e)
            except Exception as _e:
                import logging; logging.getLogger("spj.scheduler").debug("escalacion: %s", _e)

        self.scheduler_service.registrar(
            "escalacion_pedidos_wa", _check_escalacion_pedidos, intervalo_seg=60)

        def _check_recordatorios_ordenes():
            try:
                from core.services.anticipo_service import AnticipoCotizacionService
                ant_svc = AnticipoCotizacionService(self.db)
                for dias in [2, 1]:
                    ordenes = ant_svc.get_ordenes_pendientes_recordatorio(dias)
                    for orden in ordenes:
                        try:
                            cli_row = (self.db.execute(
                                "SELECT telefono, nombre FROM clientes WHERE id=?",
                                (orden.get("cliente_id"),)
                            ).fetchone() if orden.get("cliente_id") else None)
                            tel        = cli_row[0] if cli_row else None
                            nombre_cli = cli_row[1] if cli_row else "cliente"
                            pendiente  = float(orden.get("monto_anticipo", 0)) - float(orden.get("anticipo_pagado", 0))
                            estado_txt = (f"Saldo pendiente: ${pendiente:.2f}" if pendiente > 0.01 else "Todo listo")
                            if tel:
                                msg = (f"Recordatorio: tu orden {orden['numero_orden']} "
                                       f"es para el {orden.get('fecha_entrega','pronto')}. {estado_txt}")
                                self.whatsapp_service.send_message(phone_number=tel, message=msg)
                            tel_cp = self.db.execute(
                                "SELECT valor FROM anticipo_config WHERE clave='tel_encargado_compras'"
                            ).fetchone()
                            if tel_cp and tel_cp[0]:
                                self.whatsapp_service.send_message(
                                    phone_number=tel_cp[0],
                                    message=f"Preparar orden {orden['numero_orden']} para {orden.get('fecha_entrega','pronto')}. Cliente: {nombre_cli}")
                            campo = f"recordatorio_d{dias}_enviado"
                            self.db.execute(
                                f"UPDATE ordenes_cotizacion SET {campo}=1 WHERE id=?",
                                (orden["id"],))
                            try: self.db.commit()
                            except Exception: pass
                        except Exception as _e:
                            import logging; logging.getLogger("spj.scheduler").debug("recordatorio: %s", _e)
            except Exception as _e:
                import logging; logging.getLogger("spj.scheduler").debug("recordatorios: %s", _e)

        self.scheduler_service.registrar(
            "recordatorios_ordenes", _check_recordatorios_ordenes, intervalo_seg=3600)

        # Verificar mensajes WhatsApp fallidos cada hora
        def _check_wa_fallidos():
            try:
                n = self.db.execute(
                    "SELECT COUNT(*) FROM whatsapp_queue WHERE estado='fallido'"
                ).fetchone()[0]
                if n > 0 and n % 5 == 0:
                    self.notification_service.notificar_backup_fallido(
                        f"{n} mensajes WhatsApp no pudieron enviarse")
            except Exception:
                pass

        self.scheduler_service.registrar(
            "wa_fallidos_check", _check_wa_fallidos, intervalo_seg=3600
        )

        # Verificar y activar Happy Hour cada minuto
        _hh_activas_prev = set()

        def _check_happy_hour():
            nonlocal _hh_activas_prev
            try:
                hs = getattr(self, 'happy_hour_service', None)
                if not hs:
                    return
                activas = hs.get_reglas_activas_ahora()
                activas_ids = {r['id'] for r in activas}
                # Nuevas reglas que acaban de activarse
                nuevas = activas_ids - _hh_activas_prev
                for r in activas:
                    if r['id'] in nuevas and r.get('mensaje_wa'):
                        try:
                            hs.enviar_promo_whatsapp(r['id'], limite=200)
                            _log.getLogger('spj.scheduler').info(
                                "Happy Hour '%s' iniciado — WA enviados", r['nombre'])
                        except Exception as _e:
                            _log.getLogger('spj.scheduler').debug(
                                "happy_hour WA: %s", _e)
                _hh_activas_prev = activas_ids
            except Exception:
                pass

        self.scheduler_service.registrar(
            "happy_hour_check", _check_happy_hour, intervalo_seg=60
        )
        self.scheduler_service.registrar(
            "backup_diario", _run_backup, intervalo_seg=86400,
            solo_offpeak=True   # entre 22:00–06:00
        )

        # Expiración de estrellas Growth Engine (una vez al día off-peak)
        def _run_expiracion():
            try:
                ge = getattr(self, 'growth_engine', None)
                if ge:
                    n = ge.ejecutar_expiracion_nocturna()
                    if n > 0:
                        _log.getLogger("spj.scheduler").info(
                            "Growth Engine: %d clientes con estrellas expiradas", n)
            except Exception as e:
                _log.getLogger("spj.scheduler").debug("expiracion estrellas: %s", e)

        self.scheduler_service.registrar(
            "expiracion_estrellas", _run_expiracion, intervalo_seg=86400,
            solo_offpeak=True
        )

        # Mantenimiento semanal: VACUUM + ANALYZE
        def _mantenimiento_semanal():
            from datetime import datetime
            # Solo los domingos en la madrugada
            if datetime.now().weekday() != 6:
                return
            try:
                import logging as _log2
                _log2.getLogger("spj.maint").info("Ejecutando VACUUM y ANALYZE...")
                self.db.execute("PRAGMA wal_checkpoint(FULL)")
                self.db.execute("ANALYZE")
                # VACUUM no se puede ejecutar en transacción, usar conexión separada
                import sqlite3, os
                db_path = getattr(self, 'db_path', 'spj_pos_database.db')
                conn2 = sqlite3.connect(db_path, isolation_level=None)
                conn2.execute("VACUUM")
                conn2.close()
                _log2.getLogger("spj.maint").info("VACUUM y ANALYZE completados")
            except Exception as _e:
                import logging as _log2
                _log2.getLogger("spj.maint").warning("mantenimiento_semanal: %s", _e)

        self.scheduler_service.registrar(
            "mantenimiento_semanal", _mantenimiento_semanal, intervalo_seg=86400)

        # ── Auto-cierre de turno a medianoche ─────────────────────────────
        def _auto_cierre_turno():
            from datetime import datetime
            ahora = datetime.now()
            # Solo actúa entre 23:50 y 00:10
            if not (ahora.hour == 23 and ahora.minute >= 50) and not (ahora.hour == 0 and ahora.minute <= 10):
                return
            try:
                from core.services.cierre_caja_service import CierreCajaService
                # Verificar sucursales con turno abierto
                sucursales = self.db.execute(
                    "SELECT DISTINCT sucursal_id FROM turno_actual WHERE abierto=1"
                ).fetchall()
                for row in sucursales:
                    suc_id = row[0]
                    svc = CierreCajaService(conn=self.db, sucursal_id=suc_id, usuario="SISTEMA")
                    if svc.turno_activo():
                        svc.corte_z(efectivo_contado=0.0,
                                    comentarios="Cierre automático por sistema — medianoche")
                        _log.getLogger("spj.scheduler").warning(
                            "Turno sucursal %d cerrado automáticamente a medianoche", suc_id)
            except Exception as e:
                _log.getLogger("spj.scheduler").debug("auto_cierre_turno: %s", e)

        self.scheduler_service.registrar(
            "auto_cierre_turno", _auto_cierre_turno, intervalo_seg=600  # cada 10 min
        )

        # ── Reporte nocturno por email al gerente ─────────────────────────
        def _run_reporte_email():
            try:
                from core.services.reporte_email_service import ReporteEmailService
                svc = ReporteEmailService(conn=self.db)
                svc.enviar_resumen_diario(sucursal_id=self.sucursal_id)
            except Exception as e:
                _log.getLogger("spj.scheduler").debug("reporte_email: %s", e)

        self.scheduler_service.registrar(
            "reporte_email_diario", _run_reporte_email,
            intervalo_seg=86400, solo_offpeak=True
        )

    def _wire_event_bus(self) -> None:
        """
        Conecta handlers al EventBus.
        v13.4: Delegado a core/events/wiring.py para reducir tamaño de AppContainer.
        Handlers incluyen: sync, auditoría, fidelidad, notificaciones, stock bajo.
        """
        try:
            from core.events.wiring import wire_all
            wire_all(self)
        except Exception as _e:
            import logging as _l
            _l.getLogger("spj.container").warning("EventBus wiring: %s", _e)

    def set_sucursal_activa(self, sucursal_id: int, nombre: str = "") -> None:
        """
        Cambia la sucursal activa del sistema.
        Propaga a SessionContext + todos los servicios.
        """
        self.sucursal_id = sucursal_id
        self.sucursal_nombre = nombre

        # v13.4: Sincronizar con SessionContext
        if hasattr(self, 'session'):
            self.session.set_sucursal(sucursal_id, nombre)

        # Actualizar servicios que usan sucursal_id
        for svc_name in ['inventory_service', 'sales_service', 'treasury_service',
                          'happy_hour_service', 'comisiones_service',
                          'loyalty_service', 'anticipo_service']:
            svc = getattr(self, svc_name, None)
            if svc and hasattr(svc, 'sucursal_id'):
                svc.sucursal_id = sucursal_id
            if svc and hasattr(svc, 'set_sucursal'):
                try: svc.set_sucursal(sucursal_id)
                except Exception: pass

        logger.info("Sucursal activa: %s (%s)", sucursal_id, nombre)

    def set_session_user(self, user_data: dict) -> None:
        """
        v13.4: Configura el usuario en el SessionContext centralizado.
        Se llama desde MainWindow._propagar_usuario() después del login.
        """
        if hasattr(self, 'session'):
            self.session.set_user(user_data)
            # Sincronizar compat attrs
            self.sucursal_id = self.session.sucursal_id
            self.sucursal_nombre = self.session.sucursal_nombre

    def clear_session(self) -> None:
        """v13.4: Limpia la sesión (logout)."""
        if hasattr(self, 'session'):
            self.session.clear()
        self.sucursal_id = 1
        self.sucursal_nombre = "Principal"

    def close(self):
        """Cierra la base de datos limpiamente al apagar el ERP."""
        try:
            if hasattr(self, 'printer_service'):
                self.printer_service.close()
        except Exception:
            pass
        try:
            if hasattr(self, 'scheduler_service'):
                self.scheduler_service.stop()
        except Exception:
            pass
        self.db.close()