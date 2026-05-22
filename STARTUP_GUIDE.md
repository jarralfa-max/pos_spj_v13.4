# 🚀 Guía de Arranque — SPJ POS v13.4

## Opción 1: Script de Arranque Rápido (Recomendado)

### Windows
```bash
start_all.bat
```
Esto abre dos ventanas:
1. **Primera ventana**: Microservicio WhatsApp (puerto 8000)
2. **Segunda ventana**: Aplicación POS UI (PyQt5)

### Linux / macOS
```bash
./start_all.sh
```
Ambos servicios arrancan en la misma terminal. Presiona `Ctrl+C` para detener todos.

---

## Opción 2: Arranque Manual Separado

### 1️⃣ Microservicio WhatsApp (Necesario para mensajería WA)

```bash
cd whatsapp_service
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Desarrollo (con auto-reload):**
```bash
uvicorn main:app --port 8000 --reload
```

**Producción:**
```bash
uvicorn main:app --port 8000 --workers 2
```

**Verificar que está listo:**
```bash
curl http://localhost:8000/health
```
Respuesta esperada: `HTTP 200 OK`

### 2️⃣ Aplicación POS

En otra terminal:
```bash
cd pos_spj_v13.4
python main.py
```

---

## Opción 3: Arranque Automático (Incorporado)

La aplicación **intenta iniciar automáticamente** el microservicio si no está corriendo:

1. Abre `pos_spj_v13.4`
2. La aplicación detecta si el microservicio está disponible
3. Si no, intenta iniciarlo en un proceso daemon
4. Si falla, continúa (el módulo WhatsApp funciona en modo degradado)

**Requisitos:**
- `uvicorn` debe estar instalado: `pip install uvicorn fastapi`

---

## 🔍 Diagnóstico de Servicios

Abre el módulo **WhatsApp → Diagnóstico** para verificar:

✅ **Meta Cloud API** — Conectividad a servidores de Meta  
✅ **Microservicio WA** — API local en puerto 8000  
ℹ️ **Rasa NLU** — Sistema de procesamiento de lenguaje natural (opcional)  
✅ **Base de datos ERP** — Conexión a SQLite  

---

## 🐛 Troubleshooting

### Error: "No se puede establecer conexión... puerto 8000"
**Solución:** El microservicio no está corriendo.
```bash
# Inicia manualmente:
cd whatsapp_service && uvicorn main:app --port 8000
```

### Error: "uvicorn: command not found"
**Solución:** Instala las dependencias:
```bash
pip install fastapi uvicorn
```

### El microservicio se detiene inmediatamente
**Solución:** Revisa el log de errores:
```bash
cd whatsapp_service && python -c "import main; print(main.__doc__)"
```

### Puerto 8000 ya en uso
**Solución:** Usa otro puerto:
```bash
uvicorn main:app --port 8001
# Luego actualiza en POS: Módulo WhatsApp → Credenciales → Microservicio URL
```

---

## 📊 Arquitectura

```
┌─────────────────────────────────────┐
│   POS SPJ v13.4 (PyQt5 UI)          │
│   • Módulo WhatsApp con KPI Cards  │
│   • Inventario, Ventas, Finanzas   │
│   Puerto: N/A (Desktop)            │
└──────────────┬──────────────────────┘
               │ REST HTTP:8000
               ↓
┌─────────────────────────────────────┐
│   Microservicio WhatsApp (FastAPI)  │
│   • Webhooks Meta Cloud API         │
│   • Conversaciones WhatsApp         │
│   Puerto: 8000                      │
└──────────────┬──────────────────────┘
               │ SQLite
               ↓
┌─────────────────────────────────────┐
│   Base de Datos (SQLite)            │
│   spj_pos_database.db               │
└─────────────────────────────────────┘
```

---

## 📝 Variables de Entorno (Microservicio)

Crea un archivo `.env` en `whatsapp_service/`:

```env
# Meta Cloud API
META_PHONE_ID=123456789012345
META_TOKEN=EAABa...
WA_APP_SECRET=secret123

# Base de datos ERP
ERP_DB_PATH=../pos_spj_v13.4/pos_spj_v13.4/spj_pos_database.db

# Seguridad
WA_INTERNAL_API_KEY=change_me_generate_a_strong_key

# Logging
LOG_LEVEL=INFO
```

---

## ✅ Checklist de Arranque

- [ ] Python 3.9+ instalado
- [ ] `pip install -r requirements.txt` ejecutado
- [ ] Base de datos SQLite creada (primera ejecución auto-crea)
- [ ] Ejecutar uno de los 3 métodos de arranque arriba
- [ ] Verificar en Módulo WhatsApp → Diagnóstico que servicios están OK
- [ ] ¿Ves un ❌ en "Microservicio WA"? Inicia manualmente (Opción 2)

---

## 🆘 Soporte

Si los servicios no arrancan:

1. Revisa el log: `spj_pos.log` (POS) y terminal del microservicio
2. Verifica puertos disponibles: `lsof -i :8000` (macOS/Linux) o `netstat -ano | findstr :8000` (Windows)
3. Reinstala dependencias: `pip install --force-reinstall fastapi uvicorn`
