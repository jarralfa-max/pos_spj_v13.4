/**
 * theme.js — SPJ POS Web UI
 * Gestión de temas Dark / Light con persistencia en localStorage.
 * API pública: Theme.toggle(), Theme.set('dark'|'light'), Theme.get()
 */

const Theme = (() => {
  const STORAGE_KEY = 'spj-theme';
  const ATTR         = 'data-theme';
  const root         = document.documentElement;

  const ICONS = { light: '☀️', dark: '🌙' };

  function get() {
    return localStorage.getItem(STORAGE_KEY)
      || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  }

  function set(theme) {
    root.setAttribute(ATTR, theme);
    localStorage.setItem(STORAGE_KEY, theme);
    _updateToggleButton(theme);
    _updateCharts(theme);
    document.dispatchEvent(new CustomEvent('spj:theme-changed', { detail: { theme } }));
  }

  function toggle() {
    set(get() === 'dark' ? 'light' : 'dark');
  }

  function init() {
    set(get());
    /* Escucha preferencia del SO */
    window.matchMedia('(prefers-color-scheme: dark)')
      .addEventListener('change', e => {
        if (!localStorage.getItem(STORAGE_KEY)) set(e.matches ? 'dark' : 'light');
      });
  }

  function _updateToggleButton(theme) {
    const btn = document.getElementById('theme-toggle');
    if (!btn) return;
    btn.textContent = ICONS[theme === 'dark' ? 'light' : 'dark'];
    btn.title = theme === 'dark' ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro';
    btn.setAttribute('aria-label', btn.title);
  }

  /* Notifica a ECharts para re-renderizar con el tema correcto */
  function _updateCharts(theme) {
    if (window.SPJCharts && typeof window.SPJCharts.updateTheme === 'function') {
      window.SPJCharts.updateTheme(theme);
    }
  }

  return { get, set, toggle, init };
})();

/* Auto-init en cuanto carga el script */
Theme.init();
