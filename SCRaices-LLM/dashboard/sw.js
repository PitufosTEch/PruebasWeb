// Service Worker - SCRaices Dashboard PWA
const CACHE_NAME = 'scraices-v1';

// Solo cachear assets estáticos, los datos siempre se cargan frescos
const STATIC_ASSETS = [
  './index_live_v3.html',
  './manifest.json',
  './icon-192.png',
  './icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
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
  // Siempre network-first para datos frescos, fallback a cache solo para assets
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
