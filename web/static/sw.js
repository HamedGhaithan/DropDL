// A deliberately empty service worker. Browsers need one before they offer "Install app" and the share-sheet entry.
// It caches nothing and answers nothing, so the page you see is always the one the server has right now.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
