
# core/ui/module_loader.py
from __future__ import annotations
import logging
from typing import Dict, Optional
from PyQt5.QtWidgets import QWidget

logger = logging.getLogger("spj.ui.loader")

MODULE_REGISTRY = {
    "ventas":           ("ModuloVentas",              "modulos.ventas",                 []),
    "caja":             ("ModuloCaja",                "modulos.caja",                   []),
    "inventario":       ("ModuloInventarioLocal",     "modulos.inventario_local",       []),
    "inventario_enterprise":("ModuloInventarioEnterprise","modulos.inventario_enterprise",[]),
    "productos":        ("ModuloProductos",           "modulos.productos",              []),
    "clientes":         ("ModuloClientes",            "modulos.clientes",               []),
    "recetas":          ("ModuloRecetas",             "modulos.recetas",                []),
    "produccion":       ("ModuloProduccion",          "modulos.produccion",             []),
    "inv_industrial":   ("ModuloInventarioIndustrial","modulos.inventario_industrial",  []),
    "prod_carnica":     ("ModuloProduccionCarnica",   "modulos.produccion_carnica",     []),
    "planeacion":       ("ModuloPlaneacionCompras",   "modulos.planeacion_compras",     []),
    "bi":               ("ModuloReportesBi",          "modulos.reportes_bi",            []),
    "transferencias":   ("ModuloTransferencias",      "modulos.transferencias",         []),
    "fidelidad":        ("ModuloFidelidad",           "modulos.fidelidad",              []),
    "reportes":         ("ModuloReportes",            "modulos.reportes",               []),
    "gastos":           ("ModuloFinanzas",            "modulos.finanzas",               []),
    "tarjetas":         ("ModuloTarjetas",            "modulos.tarjetas",               []),
    "configuraciones":    ("Moduloconfiguraciones",       "modulos.configuraciones",          []),
    "delivery":         ("ModuloDelivery",            "modulos.delivery",               ["usuario"]),
    "rrhh":             ("ModuloRRHH",                "modulos.rrhh",                   ["usuario"]),
    "bi_v2":            ("ModuloReportesBIv2",        "modulos.reportes_bi_v2",         ["usuario"]),
    "ticket_designer":  ("ModuloTicketDesigner",      "modulos.ticket_designer",        ["usuario"]),
    "loyalty_card":     ("ModuloLoyaltyCardDesigner", "modulos.loyalty_card_designer",  ["usuario"]),
    "sistema":          ("ModuleSistema",             "modulos.sistema_dashboard",      ["usuario"]),
    "compras_pro":      ("ModuloComprasPro",          "modulos.compras_pro",            ["usuario"]),
    "activos":          ("ModuloActivos",             "modulos.activos",                ["usuario"]),
}

class ModuleLoader:
    def __init__(self, conexion, parent=None, usuario="admin"):
        self.conexion = conexion
        self.parent   = parent
        self.usuario  = usuario
        self._loaded: Dict[str, QWidget] = {}
        self._failed: Dict[str, str]     = {}

    def get(self, nombre):
        if nombre in self._loaded: return self._loaded[nombre]
        if nombre in self._failed: return None
        return self._load(nombre)

    def get_all(self):
        for n in MODULE_REGISTRY:
            if n not in self._loaded and n not in self._failed:
                self._load(n)
        return dict(self._loaded)

    def _load(self, nombre):
        if nombre not in MODULE_REGISTRY:
            logger.warning("Modulo desconocido: %s", nombre); return None
        clase_nombre, path, extras = MODULE_REGISTRY[nombre]
        try:
            import importlib
            mod  = importlib.import_module(path)
            cls  = getattr(mod, clase_nombre)
            args = [self.conexion]
            if "usuario" in extras: args.append(self.usuario)
            if self.parent:         args.append(self.parent)
            w = cls(*args)
            w._nav_key = nombre
            self._loaded[nombre] = w
            logger.debug("Cargado: %s", nombre)
            return w
        except Exception as e:
            self._failed[nombre] = str(e)
            logger.warning("Fallo al cargar %s: %s", nombre, e)
            return None

    def get_failed(self): return dict(self._failed)

    def reload(self, nombre):
        self._failed.pop(nombre,None); self._loaded.pop(nombre,None)
        return self._load(nombre)
