/* Anchor service worker — offline shell + network-first APIs.
 *
 * Strategy:
 *  - Static shell (HTML, CSS, JS, fonts, icons, portraits, music) is
 *    cache-first with stale-while-revalidate. The device can reopen
 *    Anchor on a train, with a neighbour's flakey Wi-Fi, or mid-power-
 *    cut with no network, and still get the full visual interface and
 *    Margaret's music library.
 *  - API calls (/api/*) are network-first. If the device is offline,
 *    the patient can still hear her daily brief and play music; she
 *    can't get fresh LLM replies, but the resting screen and familiar
 *    elements stay warm.
 */

const VERSION = 'anchor-v2-2026-04-18';
const SHELL_CACHE = `${VERSION}-shell`;
const API_CACHE   = `${VERSION}-api`;

const SHELL_URLS = [
  '/',
  '/family',
  '/music',
  '/carer',
  '/safety',
  '/logs',
  '/privacy',
  '/static/styles.css',
  '/static/patient.js',
  '/static/manifest.webmanifest',
  '/static/assets/ack.wav',
  '/static/assets/chime.wav',
  '/static/assets/icons/anchor-192.png',
  '/static/assets/icons/anchor-512.png',
  '/static/assets/icons/anchor-maskable-512.png',
  '/static/assets/family/priya.jpg',
  '/static/assets/family/david.jpg',
  '/static/assets/family/james.jpg',
  '/static/assets/music/gentle_hymn.mp3',
  '/static/assets/music/dance_memory.mp3',
  '/static/assets/music/evening_calm.mp3',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then(async (cache) => {
      // Individual adds so one 404 doesn't nuke the whole install.
      await Promise.all(SHELL_URLS.map(async (url) => {
        try { await cache.add(url); }
        catch (e) { console.warn('[sw] shell add failed', url, e); }
      }));
      self.skipWaiting();
    })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names
      .filter(n => !n.startsWith(VERSION))
      .map(n => caches.delete(n)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // API: network-first, fall back to last cached response if offline
  if (url.pathname.startsWith('/api/')) {
    event.respondWith((async () => {
      try {
        const resp = await fetch(req);
        // Only cache success + GET; never cache escalation or mutating endpoints.
        // status === 200 (not resp.ok) because Cache API rejects 206 Partial Content,
        // which audio range requests return.
        if (resp.status === 200) {
          const cache = await caches.open(API_CACHE);
          cache.put(req, resp.clone());
        }
        return resp;
      } catch (e) {
        const cached = await caches.match(req);
        if (cached) return cached;
        return new Response(
          JSON.stringify({ offline: true, error: 'Anchor is offline' }),
          { status: 503, headers: { 'Content-Type': 'application/json' } }
        );
      }
    })());
    return;
  }

  // Shell: stale-while-revalidate
  event.respondWith((async () => {
    const cache = await caches.open(SHELL_CACHE);
    const cached = await cache.match(req);
    const networkFetch = fetch(req).then((resp) => {
      // Skip 206 Partial Content (audio range requests) — Cache API throws on them.
      if (resp.status === 200) cache.put(req, resp.clone());
      return resp;
    }).catch(() => cached);
    return cached || networkFetch;
  })());
});
