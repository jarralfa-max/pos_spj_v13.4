"""Thin page declarations sharing the canonical responsive workspace
shell. "Feature Flags", "Apariencia", "Dispositivos", "Documentos",
"Empresa y sucursales", "General" (Estaciones), "Pantalla del cliente",
"Integraciones", "Notificaciones", and "Offline" get their own pages
(`feature_flags_page.py`/`apariencia_page.py`/`dispositivos_page.py`/
`documentos_page.py`/`empresa_page.py`/`estaciones_page.py`/
`pantalla_cliente_page.py`/`integraciones_page.py`/
`notificaciones_page.py`/`offline_page.py`) because they wire real
write actions — as of SET-23's repegado, EVERY section has a dedicated
page (no more generic-fallback sections remain).
"""
from .apariencia_page import AparienciaPage
from .dispositivos_page import DispositivosPage
from .documentos_page import DocumentosPage
from .empresa_page import EmpresaPage
from .estaciones_page import GeneralPage
from .feature_flags_page import FeatureFlagsPage
from .integraciones_page import IntegracionesPage
from .notificaciones_page import NotificacionesPage
from .offline_page import OfflinePage
from .pantalla_cliente_page import PantallaClientePage
from .usuarios_roles_page import UsuariosRolesPage

PAGE_CLASSES = {page.page_id: page for page in (
    EmpresaPage, GeneralPage, DispositivosPage, DocumentosPage, PantallaClientePage, IntegracionesPage,
    FeatureFlagsPage, AparienciaPage, NotificacionesPage, OfflinePage, UsuariosRolesPage,
)}
