// Service Worker - SCRaices Dashboard PWA
const CACHE_NAME = 'scraices-v9';

// Solo cachear assets estáticos, los datos siempre se cargan frescos
const STATIC_ASSETS = [
  './index_live_v3.html',
  './app_compiled.js',
  './tailwind.css',
  './manifest.json',
  './icon-192.png',
  './icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.all(STATIC_ASSETS.map(url =>
        fetch(new Request(url, {cache: 'reload'})).then(r => r.ok ? cache.put(url, r) : null).catch(() => null)
      ))
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // En localhost el browser no puede resolver CORS para orígenes externos
  // (Apps Script, Firebase), así que los dejamos pasar sin interceptar.
  // En GitHub Pages el SW puede re-fetchear sin problema — no saltar.
  const isLocalhost = ['localhost', '127.0.0.1'].includes(self.location.hostname);
  if (isLocalhost && new URL(event.request.url).origin !== self.location.origin) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Actualizar cache con la respuesta fresca
        if (response.ok && event.request.method === 'GET') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
