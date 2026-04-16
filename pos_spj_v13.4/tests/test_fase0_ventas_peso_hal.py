import ast
from pathlib import Path


def _leer_peso_func():
    src = Path('modulos/ventas.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'leer_peso':
            return node
    raise AssertionError('No se encontró ModuloVentas.leer_peso')


def test_leer_peso_usa_api_unificada_get_weight():
    func = _leer_peso_func()
    calls = [n for n in ast.walk(func) if isinstance(n, ast.Call)]
    attrs = [c.func.attr for c in calls if isinstance(c.func, ast.Attribute)]
    assert 'get_weight' in attrs, 'leer_peso debe usar hardware_service.get_weight()'
    assert 'read_scale' not in attrs, 'leer_peso no debe depender de read_scale() directo'
    get_weight_calls = [
        c for c in calls
        if isinstance(c.func, ast.Attribute) and c.func.attr == 'get_weight'
    ]
    assert get_weight_calls, 'Se esperaba al menos una llamada a get_weight()'
    arg0 = get_weight_calls[0].args[0]
    assert isinstance(arg0, ast.Constant) and float(arg0.value) == 0.0, (
        'leer_peso debe pedir fallback manual en 0.0 para no reciclar lecturas viejas'
    )


def test_leer_peso_mantiene_fallback_baud_seguro():
    src = Path('modulos/ventas.py').read_text(encoding='utf-8')
    assert 'baud = 9600' in src


def test_leer_peso_declara_guardia_serial_no_disponible():
    src = Path('modulos/ventas.py').read_text(encoding='utf-8')
    assert 'Báscula: ⚠️ Serial no disponible' in src
