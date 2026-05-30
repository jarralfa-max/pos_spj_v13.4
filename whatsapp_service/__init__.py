"""SPJ POS WhatsApp microservice package.

This package is importable both by the standalone FastAPI service and by the
ERP desktop application. Internal modules should prefer package-qualified imports
(`whatsapp_service.*`) to avoid collisions with ERP modules such as `config.py`.
"""
