/**
 * api.js — SPJ POS Web UI
 * Cliente HTTP centralizado para consumir el backend Python.
 * Todas las llamadas a la API deben pasar por este módulo.
 *
 * Uso:
 *   const kpis = await API.get('/api/dashboard/kpis');
 *   const result = await API.post('/api/pedido', { items: [...] });
 */

const API = (() => {
  /* Base URL del backend — mismo host, puerto 8769 */
  const BASE_URL  = `${window.location.protocol}//${window.location.hostname}:8769`;
  const API_TOKEN = window.SPJ_API_TOKEN || '';

  /* Tiempo de espera máximo por petición (ms) */
  const TIMEOUT_MS = 15_000;

  let _onUnauthorized = null;

  /* ── Headers por defecto ─────────────────────────────────────────────── */
  function _headers(extra = {}) {
    return {
      'Content-Type': 'application/json',
      'Accept':       'application/json',
      ...(API_TOKEN ? { 'X-API-Token': API_TOKEN } : {}),
      ...extra,
    };
  }

  /* ── Fetch con timeout ───────────────────────────────────────────────── */
  async function _fetchWithTimeout(url, options) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    try {
      const res = await fetch(url, { ...options, signal: controller.signal });
      return res;
    } finally {
      clearTimeout(timer);
    }
  }

  /* ── Parsear respuesta ───────────────────────────────────────────────── */
  async function _parse(res) {
    const ct = res.headers.get('Content-Type') || '';
    if (ct.includes('application/json')) {
      const data = await res.json();
      if (!res.ok) throw { status: res.status, data };
      return data;
    }
    if (!res.ok) throw { status: res.status, data: null };
    return null;
  }

  /* ── GET ─────────────────────────────────────────────────────────────── */
  async function get(path, params = {}) {
    const url = new URL(BASE_URL + path);
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
    const res = await _fetchWithTimeout(url.toString(), {
      method:  'GET',
      headers: _headers(),
    });
    if (res.status === 401 && _onUnauthorized) _onUnauthorized();
    return _parse(res);
  }

  /* ── POST ────────────────────────────────────────────────────────────── */
  async function post(path, body = {}) {
    const res = await _fetchWithTimeout(BASE_URL + path, {
      method:  'POST',
      headers: _headers(),
      body:    JSON.stringify(body),
    });
    if (res.status === 401 && _onUnauthorized) _onUnauthorized();
    return _parse(res);
  }

  /* ── PUT ─────────────────────────────────────────────────────────────── */
  async function put(path, body = {}) {
    const res = await _fetchWithTimeout(BASE_URL + path, {
      method:  'PUT',
      headers: _headers(),
      body:    JSON.stringify(body),
    });
    return _parse(res);
  }

  /* ── DELETE ──────────────────────────────────────────────────────────── */
  async function del(path) {
    const res = await _fetchWithTimeout(BASE_URL + path, {
      method:  'DELETE',
      headers: _headers(),
    });
    return _parse(res);
  }

  /* ── Configurable ────────────────────────────────────────────────────── */
  function onUnauthorized(cb) { _onUnauthorized = cb; }

  /* ── Endpoints semánticos ────────────────────────────────────────────── */
  const dashboard = {
    kpis:        (params) => get('/api/dashboard/kpis', params),
    ventasChart: (params) => get('/api/dashboard/ventas-chart', params),
    productosTop:(params) => get('/api/dashboard/productos-top', params),
    inventario:  (params) => get('/api/dashboard/inventario', params),
    alertas:     ()       => get('/api/dashboard/alertas'),
    sucursales:  ()       => get('/api/sucursales'),
  };

  const productos = {
    list:   (params) => get('/api/productos', params),
    get:    (id)     => get(`/api/productos/${id}`),
  };

  const pedidos = {
    crear:  (body)   => post('/api/pedido', body),
    calcular: (body) => post('/api/carrito/calcular', body),
  };

  const qr = {
    info: (uuid) => get('/api/qr', { uuid }),
  };

  return { get, post, put, del, onUnauthorized, dashboard, productos, pedidos, qr };
})();
