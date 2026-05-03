#!/usr/bin/env python3
"""
pos_spj_v13.4 — Verificador de instalación
Ejecuta: python actualizar.py
"""
import os, sys, shutil, glob

def main():
    print("=" * 50)
    print("  POS SPJ v13.4 — VERIFICADOR")
    print("=" * 50)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cwd = os.getcwd()
    print(f"\n  Carpeta actual:  {cwd}")
    print(f"  Carpeta script:  {script_dir}")
    
    if cwd != script_dir:
        os.chdir(script_dir)
        print(f"  → Cambiado a: {script_dir}")
    
    sys.path.insert(0, '.')
    
    # Versión
    print(f"\n── Versión ──")
    try:
        from version import __version__
        print(f"  Versión: {__version__}")
        if "13.4" in __version__:
            print(f"  ✅ CÓDIGO v13.4 DETECTADO")
        else:
            print(f"  ❌ VERSIÓN INCORRECTA: {__version__}")
    except Exception as e:
        print(f"  ❌ {e}")
    
    # Limpiar cache
    print(f"\n── Limpiando cache ──")
    n = 0
    for root, dirs, files in os.walk('.'):
        if '__pycache__' in dirs:
            shutil.rmtree(os.path.join(root, '__pycache__'), True)
            n += 1
    print(f"  {n} directorios __pycache__ eliminados")
    
    # Archivos nuevos
    print(f"\n── Archivos nuevos v13.4 ──")
    for f in ['core/module_config.py', 'core/services/printer_service.py',
              'core/services/treasury_service.py', 'core/services/alert_engine.py',
              'core/services/qr_parser_service.py', 'core/services/ceo_dashboard.py',
              'hardware/scale_reader.py']:
        print(f"  {'✅' if os.path.exists(f) else '❌'} {f}")
    
    # Archivos viejos
    print(f"\n── Archivos viejos (NO deben existir) ──")
    for f in ['hardware_utils.py', 'core/engines/loyalty_engine.py',
              'core/services/fidelidad_engine.py', 'core/services/ticket_printer.py']:
        if os.path.exists(f):
            print(f"  ❌ {f} — BÓRRALO MANUALMENTE")
        else:
            print(f"  ✅ {f} eliminado")
    
    # BD
    print(f"\n── Base de datos ──")
    db = 'spj_pos_database.db'
    if os.path.exists(db):
        sz = os.path.getsize(db) / 1024 / 1024
        print(f"  ✅ {db} ({sz:.1f} MB)")
    else:
        print(f"  ❌ {db} NO ENCONTRADA")
        print(f"     Copia tu BD aquí")
    
    print(f"\n{'='*50}")
    print(f"  Ahora ejecuta: python main.py")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
