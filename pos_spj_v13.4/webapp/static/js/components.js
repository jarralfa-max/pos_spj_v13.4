/**
 * components.js — SPJ POS Web UI
 * Biblioteca de componentes JS reutilizables:
 * Toast, Modal, Tabs, Sidebar, DataTable, Loader, Confirm
 */

/* ════════════════════════════════════════════════════════════════════════════
   TOAST
   ════════════════════════════════════════════════════════════════════════════ */

const Toast = (() => {
  let container;

  const ICONS = {
    success: '✓',
    danger:  '✕',
    warning: '⚠',
    info:    'ℹ',
  };

  function _getContainer() {
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      document.body.appendChild(container);
    }
    return container;
  }

  function show({ type = 'info', title = '', message = '', duration = 4000 }) {
    const c = _getContainer();
    const el = document.createElement('div');
    el.className = `toast toast-${type} slide-down`;
    el.innerHTML = `
      <div class="toast-icon">${ICONS[type] || 'ℹ'}</div>
      <div class="toast-body">
        ${title    ? `<div class="toast-title">${_esc(title)}</div>`   : ''}
        ${message  ? `<div class="toast-msg">${_esc(message)}</div>`  : ''}
      </div>
    `;
    c.appendChild(el);

    if (duration > 0) {
      setTimeout(() => _remove(el), duration);
    }
    return el;
  }

  function _remove(el) {
    el.classList.add('removing');
    el.addEventListener('transitionend', () => el.remove(), { once: true });
  }

  function _esc(str) {
    return String(str)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  const success = (title, msg, d)  => show({ type:'success', title, message: msg, duration: d });
  const danger  = (title, msg, d)  => show({ type:'danger',  title, message: msg, duration: d });
  const warning = (title, msg, d)  => show({ type:'warning', title, message: msg, duration: d });
  const info    = (title, msg, d)  => show({ type:'info',    title, message: msg, duration: d });

  return { show, success, danger, warning, info };
})();


/* ════════════════════════════════════════════════════════════════════════════
   MODAL
   ════════════════════════════════════════════════════════════════════════════ */

const Modal = (() => {
  let _current = null;

  function open({ id, title, content, size = 'md', footer = '', onClose = null }) {
    close(); // cerrar previo

    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop';
    backdrop.id = id || 'modal-dynamic';
    backdrop.innerHTML = `
      <div class="modal modal-${size}" role="dialog" aria-modal="true">
        <div class="modal-header">
          <h3 class="modal-title">${title || ''}</h3>
          <button class="modal-close" aria-label="Cerrar">✕</button>
        </div>
        <div class="modal-body">${content || ''}</div>
        ${footer ? `<div class="modal-footer">${footer}</div>` : ''}
      </div>
    `;

    backdrop.querySelector('.modal-close').addEventListener('click', () => {
      close();
      if (onClose) onClose();
    });
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) { close(); if (onClose) onClose(); }
    });

    document.body.appendChild(backdrop);
    document.body.style.overflow = 'hidden';
    _current = { backdrop, onClose };

    /* Escuchar Escape */
    const handler = (e) => { if (e.key === 'Escape') { close(); if (onClose) onClose(); } };
    document.addEventListener('keydown', handler, { once: true });

    return backdrop;
  }

  function close() {
    if (_current) {
      _current.backdrop.remove();
      document.body.style.overflow = '';
      _current = null;
    }
  }

  function confirm({ title, message, confirmText = 'Confirmar', cancelText = 'Cancelar',
                     type = 'primary' }) {
    return new Promise((resolve) => {
      const footer = `
        <button class="btn btn-secondary" id="modal-cancel">${cancelText}</button>
        <button class="btn btn-${type}"   id="modal-confirm">${confirmText}</button>
      `;
      const modal = open({ title, content: `<p>${message}</p>`, size: 'sm', footer,
                           onClose: () => resolve(false) });
      modal.querySelector('#modal-confirm').addEventListener('click', () => { close(); resolve(true); });
      modal.querySelector('#modal-cancel').addEventListener('click',  () => { close(); resolve(false); });
    });
  }

  return { open, close, confirm };
})();


/* ════════════════════════════════════════════════════════════════════════════
   TABS
   ════════════════════════════════════════════════════════════════════════════ */

function initTabs(containerEl) {
  const triggers = containerEl.querySelectorAll('[data-tab]');
  const panels   = containerEl.querySelectorAll('[data-tab-panel]');

  function activate(tabId) {
    triggers.forEach(t => t.classList.toggle('active', t.dataset.tab === tabId));
    panels.forEach(p   => p.classList.toggle('active', p.dataset.tabPanel === tabId));
  }

  triggers.forEach(t => t.addEventListener('click', () => activate(t.dataset.tab)));

  /* Activar el primero por defecto */
  if (triggers.length > 0) activate(triggers[0].dataset.tab);
}


/* ════════════════════════════════════════════════════════════════════════════
   SIDEBAR MANAGER
   ════════════════════════════════════════════════════════════════════════════ */

const Sidebar = (() => {
  const STORAGE_KEY = 'spj-sidebar-collapsed';
  let sidebar, mainContent, overlay;

  function _isMobile() { return window.innerWidth <= 768; }

  function init() {
    sidebar     = document.querySelector('.sidebar');
    mainContent = document.querySelector('.main-content');

    /* Overlay para móvil */
    overlay = document.createElement('div');
    overlay.className = 'sidebar-overlay';
    overlay.addEventListener('click', close);
    document.body.appendChild(overlay);

    /* Toggle button */
    document.querySelectorAll('.sidebar-toggle').forEach(btn =>
      btn.addEventListener('click', toggle)
    );

    /* Restaurar estado en escritorio */
    if (!_isMobile() && localStorage.getItem(STORAGE_KEY) === 'true') {
      sidebar.classList.add('collapsed');
    }

    /* Nav items: routing */
    document.querySelectorAll('.nav-item[data-view]').forEach(item => {
      item.addEventListener('click', () => {
        const view = item.dataset.view;
        Router.navigate(view);
        if (_isMobile()) close();
      });
    });

    window.addEventListener('resize', () => {
      if (!_isMobile()) overlay.classList.remove('visible');
    });
  }

  function toggle() {
    if (_isMobile()) {
      sidebar.classList.toggle('mobile-open');
      overlay.classList.toggle('visible', sidebar.classList.contains('mobile-open'));
    } else {
      const isNowCollapsed = sidebar.classList.toggle('collapsed');
      localStorage.setItem(STORAGE_KEY, isNowCollapsed);
    }
  }

  function close() {
    sidebar.classList.remove('mobile-open');
    overlay.classList.remove('visible');
  }

  function setActiveItem(view) {
    document.querySelectorAll('.nav-item').forEach(el => {
      el.classList.toggle('active', el.dataset.view === view);
    });
  }

  return { init, toggle, close, setActiveItem };
})();


/* ════════════════════════════════════════════════════════════════════════════
   ROUTER (SPA mínimo)
   ════════════════════════════════════════════════════════════════════════════ */

const Router = (() => {
  const views    = {};
  let   _current = null;

  function register(name, { load, title }) {
    views[name] = { load, title };
  }

  async function navigate(name) {
    const view = views[name];
    if (!view) return console.warn('Vista desconocida:', name);

    const container = document.getElementById('view-container');
    if (!container) return;

    /* Loader */
    container.innerHTML = `
      <div class="page-loading fade-in">
        <div class="spinner"></div>
        <span>Cargando...</span>
      </div>
    `;

    /* Actualizar URL hash */
    history.replaceState(null, '', '#' + name);

    /* Actualizar topbar title */
    const topbarTitle = document.getElementById('topbar-title');
    if (topbarTitle) topbarTitle.textContent = view.title || name;

    /* Sidebar */
    Sidebar.setActiveItem(name);
    _current = name;

    try {
      await view.load(container);
    } catch (err) {
      container.innerHTML = `
        <div class="empty-state fade-in">
          <div class="empty-icon">⚠️</div>
          <div class="empty-title">Error al cargar la vista</div>
          <div class="empty-msg">${err.message || err}</div>
        </div>
      `;
    }
  }

  function current() { return _current; }

  function initFromHash() {
    const hash = location.hash.replace('#', '') || 'dashboard';
    navigate(hash);
  }

  window.addEventListener('popstate', initFromHash);

  return { register, navigate, current, initFromHash };
})();


/* ════════════════════════════════════════════════════════════════════════════
   DATA TABLE con búsqueda y ordenamiento
   ════════════════════════════════════════════════════════════════════════════ */

function DataTable({ container, columns, rows, searchable = true, pageSize = 20 }) {
  let _filtered   = [...rows];
  let _sortCol    = null;
  let _sortDir    = 'asc';
  let _page       = 1;
  let _query      = '';

  function _render() {
    container.innerHTML = _buildHTML();
    _bindEvents();
  }

  function _buildHTML() {
    const start = (_page - 1) * pageSize;
    const slice = _filtered.slice(start, start + pageSize);
    const totalPages = Math.ceil(_filtered.length / pageSize);

    const search = searchable ? `
      <div class="filter-bar" style="margin-bottom:var(--space-3)">
        <div class="input-wrapper flex-1">
          <span class="input-icon">🔍</span>
          <input class="form-input dt-search" placeholder="Buscar..." value="${_esc(_query)}">
        </div>
        <span class="text-muted text-xs">${_filtered.length} resultados</span>
      </div>` : '';

    const thead = `<thead><tr>${columns.map(c => `
      <th class="${c.align === 'right' ? 'num' : ''} ${c.sortable !== false ? 'sortable' : ''} ${_sortCol === c.key ? ('sort-' + _sortDir) : ''}"
          data-col="${c.key}">${c.label}</th>`).join('')}</tr></thead>`;

    const tbody = slice.length > 0
      ? `<tbody>${slice.map(row => `<tr>${columns.map(c => `
          <td class="${c.align === 'right' ? 'num' : ''} ${c.class || ''}">${
            c.render ? c.render(row[c.key], row) : _esc(row[c.key] ?? '')
          }</td>`).join('')}</tr>`).join('')}</tbody>`
      : `<tbody><tr><td colspan="${columns.length}">
           <div class="empty-state"><div class="empty-icon">📭</div>
           <div class="empty-title">Sin resultados</div></div>
         </td></tr></tbody>`;

    const pagination = totalPages > 1 ? `
      <div class="flex items-center justify-between p-3" style="border-top:1px solid var(--border-color)">
        <span class="text-xs text-muted">Página ${_page} de ${totalPages}</span>
        <div class="flex gap-2">
          <button class="btn btn-sm btn-secondary dt-prev" ${_page <= 1 ? 'disabled' : ''}>← Ant</button>
          <button class="btn btn-sm btn-secondary dt-next" ${_page >= totalPages ? 'disabled' : ''}>Sig →</button>
        </div>
      </div>` : '';

    return `${search}
      <div class="table-container">
        <table class="table">${thead}${tbody}</table>
        ${pagination}
      </div>`;
  }

  function _bindEvents() {
    const searchEl = container.querySelector('.dt-search');
    if (searchEl) {
      searchEl.addEventListener('input', (e) => {
        _query = e.target.value;
        _page  = 1;
        _filter();
        _render();
        searchEl.focus();
      });
    }

    container.querySelectorAll('th.sortable').forEach(th => {
      th.addEventListener('click', () => {
        const col = th.dataset.col;
        if (_sortCol === col) {
          _sortDir = _sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          _sortCol = col;
          _sortDir = 'asc';
        }
        _sort();
        _render();
      });
    });

    const prev = container.querySelector('.dt-prev');
    const next = container.querySelector('.dt-next');
    if (prev) prev.addEventListener('click', () => { _page--; _render(); });
    if (next) next.addEventListener('click', () => { _page++; _render(); });
  }

  function _filter() {
    if (!_query) { _filtered = [...rows]; return; }
    const q = _query.toLowerCase();
    _filtered = rows.filter(row =>
      columns.some(c => String(row[c.key] ?? '').toLowerCase().includes(q))
    );
  }

  function _sort() {
    if (!_sortCol) return;
    _filtered.sort((a, b) => {
      const va = a[_sortCol] ?? '';
      const vb = b[_sortCol] ?? '';
      const cmp = typeof va === 'number'
        ? va - vb
        : String(va).localeCompare(String(vb), 'es', { numeric: true });
      return _sortDir === 'asc' ? cmp : -cmp;
    });
  }

  function update(newRows) {
    rows = newRows;
    _filter();
    _render();
  }

  function _esc(str) {
    return String(str)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  _render();
  return { update };
}


/* ════════════════════════════════════════════════════════════════════════════
   LOADER DE SECCIÓN
   ════════════════════════════════════════════════════════════════════════════ */

function showLoader(container, msg = 'Cargando...') {
  container.innerHTML = `
    <div class="page-loading fade-in">
      <div class="spinner"></div>
      <span class="text-muted text-sm">${msg}</span>
    </div>`;
}

function showError(container, msg = 'Error al cargar datos') {
  container.innerHTML = `
    <div class="empty-state fade-in">
      <div class="empty-icon">⚠️</div>
      <div class="empty-title">Error</div>
      <div class="empty-msg">${msg}</div>
    </div>`;
}


/* ════════════════════════════════════════════════════════════════════════════
   NÚMERO FORMATEADO (moneda MXN)
   ════════════════════════════════════════════════════════════════════════════ */

const Fmt = {
  money: (n) => new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(n ?? 0),
  number: (n, dec = 0) => new Intl.NumberFormat('es-MX', { minimumFractionDigits: dec, maximumFractionDigits: dec }).format(n ?? 0),
  percent: (n) => `${(n ?? 0).toFixed(1)}%`,
  date: (d) => d ? new Date(d).toLocaleDateString('es-MX', { day:'2-digit', month:'short', year:'numeric' }) : '—',
  datetime: (d) => d ? new Date(d).toLocaleString('es-MX', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' }) : '—',
};


/* ════════════════════════════════════════════════════════════════════════════
   KPI CARD BUILDER
   ════════════════════════════════════════════════════════════════════════════ */

function buildKpiCard({ label, value, delta, deltaLabel, icon, color = 'primary' }) {
  const deltaClass  = delta > 0 ? 'positive' : delta < 0 ? 'negative' : 'neutral';
  const deltaSign   = delta > 0 ? '↑' : delta < 0 ? '↓' : '→';
  const deltaText   = delta != null
    ? `<span class="kpi-delta ${deltaClass}">${deltaSign} ${Math.abs(delta).toFixed(1)}% ${deltaLabel || 'vs ayer'}</span>` : '';

  return `
    <div class="kpi-card fade-in">
      <div class="kpi-accent-bar" style="background:var(--color-${color})"></div>
      <div class="kpi-label">${label}</div>
      <div class="kpi-value">${value}</div>
      ${deltaText}
      <div class="kpi-icon">${icon || ''}</div>
    </div>`;
}
