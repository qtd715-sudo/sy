// Service Worker — Stale-While-Revalidate
//
// 전략:
//  - 정적 자산 (HTML/JS/CSS/icon/manifest): 캐시 즉시 반환 + 백그라운드 갱신
//      → 재방문/페이지 이동 모두 0ms 로딩
//  - API GET 응답: 캐시 즉시 반환 + 백그라운드 갱신
//      → 화면이 비어 있는 시간이 없어짐. 최신 데이터는 다음 요청에 반영
//      → 단, 캐시가 너무 오래되면(>5분) 캐시 무시하고 네트워크 우선 (실시간성 보장)
//  - /api/admin/*, /api/prefetch 는 캐시하지 않음 (인증/사이드이펙트)
//
// 캐시 키 'sy-v5' — 이전 버전 캐시는 activate 시 모두 삭제됨.
const CACHE = 'sy-v5';
const API_FRESH_MS = 5 * 60 * 1000; // 5분 이상 묵으면 캐시 무시

const PRECACHE = [
  '/',
  '/index.html',
  '/style.css',
  '/app.js',
  '/manifest.json',
  '/icon-192.svg',
  '/icon-512.svg',
];

// 첫 진입 후 백그라운드로 미리 받아두면 페이지 이동 시 즉시 렌더되는 API들
const WARMUP_APIS = [
  '/api/health',
  '/api/commodities',
  '/api/undervalued?n=5',
  '/api/undervalued?n=10',
  '/api/news/market?n=4',
  '/api/news/topics?n=4',
  '/api/sy/undervalued?n=10',
  '/api/youtube/grouped',
];

self.addEventListener('install', e => {
  // cache: 'reload' — 브라우저 HTTP 캐시(1일짜리)를 건너뛰고 네트워크에서
  // 직접 받아옴. 새 SW 버전(CACHE 키 bump) 마다 정적 자산도 강제 갱신.
  const reqs = PRECACHE.map(u => new Request(u, { cache: 'reload' }));
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(reqs).catch(() => {})) // 일부 실패해도 SW 설치는 진행
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
      .then(() => warmup())
  );
});

// 백그라운드 워밍업 — activate 후 자주 쓰는 API 미리 받아둠
async function warmup() {
  try {
    const cache = await caches.open(CACHE);
    await Promise.all(WARMUP_APIS.map(url =>
      fetch(url, { credentials: 'same-origin' })
        .then(res => { if (res.ok) cache.put(url, res.clone()); })
        .catch(() => {})
    ));
  } catch {}
}

function shouldBypass(url) {
  if (url.pathname.startsWith('/api/admin/')) return true;
  if (url.pathname.startsWith('/api/prefetch')) return true;
  return false;
}

function isApi(url) {
  return url.pathname.startsWith('/api/');
}

// stale-while-revalidate: 캐시 즉시 + 백그라운드 갱신
async function swr(request, opts = {}) {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(request);
  const maxAge = opts.maxAge || 0;

  // 캐시가 너무 오래됐으면 네트워크 우선
  if (cached && maxAge > 0) {
    const dateHdr = cached.headers.get('sw-cached-at');
    const age = dateHdr ? (Date.now() - Number(dateHdr)) : Infinity;
    if (age > maxAge) {
      try {
        const fresh = await fetch(request);
        if (fresh.ok && request.method === 'GET') {
          cache.put(request, stamp(fresh.clone()));
        }
        return fresh;
      } catch {
        return cached; // 네트워크 실패 시 묵은 캐시라도 반환
      }
    }
  }

  // 백그라운드 갱신
  const networkPromise = fetch(request).then(res => {
    if (res.ok && request.method === 'GET') {
      cache.put(request, stamp(res.clone()));
    }
    return res;
  }).catch(() => null);

  return cached || networkPromise || new Response('offline', { status: 503 });
}

// Response 에 sw-cached-at 헤더 부착 (age 추적용)
function stamp(res) {
  const headers = new Headers(res.headers);
  headers.set('sw-cached-at', String(Date.now()));
  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers,
  });
}

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);

  // cross-origin 은 패스
  if (url.origin !== location.origin) return;

  // bypass 대상은 SW 가 건드리지 않음
  if (shouldBypass(url)) return;

  if (isApi(url)) {
    e.respondWith(swr(e.request, { maxAge: API_FRESH_MS }));
  } else {
    // 정적: SWR 무제한 (수동 새로고침 시 SW activate → 캐시 자동 갱신)
    e.respondWith(swr(e.request, { maxAge: 0 }));
  }
});

// 메시지: 클라이언트가 강제 캐시 비우기 요청 시
self.addEventListener('message', e => {
  if (e.data && e.data.type === 'CLEAR_CACHE') {
    caches.delete(CACHE).then(() => e.source && e.source.postMessage({ ok: true }));
  }
});
