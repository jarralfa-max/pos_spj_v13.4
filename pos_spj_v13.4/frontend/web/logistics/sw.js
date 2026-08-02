<<<<<<< HEAD
const CACHE = "spj-logistics-shell-v2";
const SHELL = ["./", "index.html", "styles.css", "app.js", "api.js", "store.js", "sync.js", "workflow_rules.js", "uuidv7.js", "manifest.webmanifest", "icons/icon.svg"];
=======
const CACHE = "spj-logistics-shell-v1";
const SHELL = ["./", "index.html", "styles.css", "app.js", "api.js", "store.js", "sync.js", "uuidv7.js", "manifest.webmanifest", "icons/icon.svg"];
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith("/api/") || event.request.method !== "GET") return;
  event.respondWith(fetch(event.request).then((response) => {
    const copy = response.clone(); caches.open(CACHE).then((cache) => cache.put(event.request, copy)); return response;
  }).catch(() => caches.match(event.request).then((cached) => cached || caches.match("index.html"))));
});
