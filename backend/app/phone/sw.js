// Minimal service worker. Browsers only allow installing a web app (and adding it to the
// share sheet) when one exists; Phone Link always talks to the PC live, so nothing is cached.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
