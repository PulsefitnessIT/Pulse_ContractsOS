/* Pulse Contracts OS PWA – offline information only, never customer data. */
'use strict';
const CACHE_NAME = 'pulse-contracts-offline-v1';
const SAFE_ASSETS = ['/static/offline.html', '/static/icons/contracts-192.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(SAFE_ASSETS)));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(key => key.startsWith('pulse-contracts-offline-') && key !== CACHE_NAME).map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});
// Never cache authenticated pages, API responses, exports or customer documents.
self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET' || req.mode !== 'navigate') return;
  event.respondWith(fetch(req).catch(async () => {
    const cache = await caches.open(CACHE_NAME);
    return (await cache.match('/static/offline.html')) || Response.error();
  }));
});
