// Service Worker — LeadGen EU PWA
const CACHE = 'leadgen-v1';
const SHELL = [
  '/',
  '/web/css/app.css',
  '/web/js/api.js',
  '/web/js/app.js',
  '/web/js/dashboard.js',
  '/web/js/leads.js',
  '/web/js/lead-detail.js',
  '/web/js/campaign.js',
  '/web/js/reports.js',
  '/web/js/settings.js',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);

  // API klici — network first, brez cache
  if (url.pathname.startsWith('/api/') || url.pathname === '/ws') {
    e.respondWith(fetch(e.request).catch(() => new Response('{"error":"offline"}', {
      headers: { 'Content-Type': 'application/json' }
    })));
    return;
  }

  // Statični resursi — cache first
  e.respondWith(
    caches.match(e.request).then((cached) => {
      if (cached) return cached;
      return fetch(e.request).then((res) => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, clone));
        }
        return res;
      });
    })
  );
});
