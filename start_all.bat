@echo off
REM start_all.bat — Inicia POS SPJ + Microservicio WhatsApp (Windows)

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo 🚀 Iniciando SPJ POS v13.4 con Microservicio WhatsApp...
echo.

REM ── Microservicio WhatsApp ──────────────────────────────────────────────────
echo [1/2] Iniciando Microservicio WhatsApp en puerto 8000...
start "WhatsApp Microservice" cmd /k "cd whatsapp_service && uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 3 /nobreak

REM ── Aplicación Principal ────────────────────────────────────────────────────
echo [2/2] Iniciando POS SPJ UI...
start "POS SPJ v13.4" cmd /k "cd pos_spj_v13.4 && python main.py"

echo.
echo ✅ Ambos servicios iniciados en ventanas separadas
echo    • POS SPJ:         UI PyQt5 (segunda ventana)
echo    • WhatsApp:        http://localhost:8000 (primera ventana)
echo    • Webhook handler: http://localhost:8000/webhook
echo.
echo Cierra cualquier ventana para detener ese servicio
echo.
pause
