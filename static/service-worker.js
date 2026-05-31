const CACHE_NAME = "hardware-ai-doc-engine-v4";
const APP_SHELL = [
  "/",
  "/manifest.webmanifest",
  "/static/styles.css",
  "/static/app.js",
  "/static/assets/app-icon.svg",
  "/static/assets/hardware-workbench.jpg"
];
const PRIVATE_PATH_PREFIXES = ["/api/", "/outputs/"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);
  if (url.origin === self.location.origin && PRIVATE_PATH_PREFIXES.some((prefix) => url.pathname.startsWith(prefix))) {
    event.respondWith(fetch(request));
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) {
        return cached;
      }
      return fetch(request).then((response) => {
        if (url.origin === self.location.origin && response.ok && isAppShellPath(url.pathname)) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        }
        return response;
      });
    }).catch(() => caches.match("/"))
  );
});

function isAppShellPath(pathname) {
  return APP_SHELL.includes(pathname) || pathname.startsWith("/static/");
}
