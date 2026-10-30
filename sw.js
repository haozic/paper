/* Service Worker —— 离线阅读（P2-1）
 *
 * 目标
 * ----
 * 1. 应用外壳（index.html / CSS / JS / manifest / 图标 / 封面）预缓存，
 *    断网也能正常打开并显示完整样式；
 * 2. 三刊的 meta / article_index 预缓存，断网后仍能浏览目录、打开已读文章；
 * 3. 用户读过的正文（articles 目录下的 .md）与正文分片（data 各刊的 issues 目录）运行时缓存，
 *    断网后仍可阅读已缓存的正文。
 *
 * 版本与缓存失效
 * --------------
 * 本文件通过 URL 查询串拿版本：注册时用 sw.js?v=<DATA_VERSION>，与 index.html /
 * app.js 用的是**同一个版本常量**。版本一变 → 浏览器装上新的 SW → 新 SW 的
 * activate 会清掉旧版本的外壳与数据缓存，保证不会把上一期的 meta / 索引当新数据用。
 * 正文 md 放在不带版本号的缓存里（内容不可变），跨版本保留。
 *
 * 缓存键规则（避免"版本号一变全量重下"，也避免"永远读到旧数据"）
 * --------------------------------------------------------------
 *   index.html / 导航         按路径
 *   assets/css, assets/js     完整 URL（含 ?v=）—— 版本号变了就是新资源，必须重下
 *   assets/img 下的图片        按路径 —— 封面图各带各的版本号，按路径存最省事
 *   data/counts.json          完整 URL
 *   data 下各刊的 meta.json    完整 URL —— 元数据每次发版都会变
 *   data/article_index.json   完整 URL
 *   data 下的 issues 分片      按路径 —— 分片内容实际不变
 *   articles 下的 .md         按路径 —— 正文不可变
 *
 * Chrome 69
 * ---------
 * Service Worker 自 Chrome 40+ 起支持。本文件只用 ES5/ES6 语法与 Promise，
 * 不含可选链（?.）、空值合并（??）等 Chrome 80+ 才有的语法。
 * Chrome 69 不认 manifest（Chrome 72 前才有），只是无法"安装到桌面"，不影响离线阅读。
 */

'use strict';

/* 版本：优先从自身 URL 的 ?v= 取，取不到时用兜底值 */
var VERSION = (function () {
    try {
        var m = /[?&]v=([^&]+)/.exec(self.location.search);
        return m ? decodeURIComponent(m[1]) : '20261030d';
    } catch (e) {
        return '20261030d';
    }
})();

var SHELL_CACHE = 'djyj-shell-' + VERSION;
var RT_CACHE = 'djyj-rt-' + VERSION;
var MD_CACHE = 'djyj-md';           /* 正文不可变，跨版本保留 */
var KEEP_CACHES = [SHELL_CACHE, RT_CACHE, MD_CACHE];

/* 应用外壳：安装时预缓存（必须能离线打开并显示完整样式） */
var SHELL_ASSETS = [
    './',
    './index.html',
    './manifest.webmanifest?v=' + VERSION,
    './assets/css/style.css?v=' + VERSION,
    './assets/js/app.js?v=' + VERSION,
    './assets/img/icon-192.png',
    './assets/img/icon-512.png',
    './assets/img/icon-maskable-512.png',
    './assets/img/apple-touch-icon.png',
    './assets/img/cover_qs.jpg',
    './assets/img/cover_hqwg.jpg',
    './assets/img/cover_djyj.jpg',
    './data/counts.json?v=' + VERSION
];

/* 三刊元数据与索引：activate 后台补齐（断网后仍能浏览目录） */
var DATA_ASSETS = [
    './data/article_index.json?v=' + VERSION,
    './data/meta.json?v=' + VERSION,
    './data/qs/meta.json?v=' + VERSION,
    './data/hqwg/meta.json?v=' + VERSION
];

/* 运行时缓存条目上限，超出后按插入顺序淘汰最旧的，防止无限膨胀 */
var MAX_RT_ENTRIES = 200;
var MAX_MD_ENTRIES = 250;

/* 计算缓存键：见文件头"缓存键规则" */
function cacheKeyFor(request) {
    var url = new URL(request.url);
    var p = url.pathname;

    if (p === '/' || p === '/index.html') {
        return new Request(url.origin + p);
    }
    if (p.indexOf('/assets/img/') === 0) {
        return new Request(url.origin + p);
    }
    if (p.indexOf('/data/') === 0 && p.indexOf('/issues/') === -1) {
        return request;              /* counts / meta / article_index：带版本号 */
    }
    if (p.indexOf('/data/') === 0) {
        return new Request(url.origin + p);   /* 正文分片：按路径 */
    }
    if (p.indexOf('/articles/') === 0) {
        return new Request(url.origin + p);   /* 正文 md：按路径 */
    }
    return request;                  /* CSS / JS 等：完整 URL */
}

function trimCache(cacheName, max) {
    return caches.open(cacheName).then(function (cache) {
        return cache.keys().then(function (keys) {
            if (keys.length <= max) return null;
            var victims = keys.slice(0, keys.length - max);
            return Promise.all(victims.map(function (k) {
                return cache.delete(k);
            }));
        });
    });
}

/* 把响应写进运行时缓存，并顺手做一次容量控制 */
function putInRuntime(cacheName, request, response, max) {
    if (!response || !response.ok) return Promise.resolve(null);
    var key;
    try {
        key = cacheKeyFor(request);
    } catch (e) {
        return Promise.resolve(null);
    }
    return caches.open(cacheName).then(function (cache) {
        return cache.put(key, response.clone()).then(function () {
            return trimCache(cacheName, max);
        });
    }).catch(function () {
        return null;
    });
}

/* 预缓存。单个资源失败不应让整次安装失败。 */
function cacheAssets(cacheName, list) {
    return caches.open(cacheName).then(function (cache) {
        return Promise.all(list.map(function (url) {
            return cache.add(new Request(url, { cache: 'reload' })).catch(function (e) {
                console.warn('[sw] 预缓存失败：' + url, e);
            });
        }));
    });
}

/* 清理旧版本缓存（正文 md 缓存跨版本保留） */
function cleanOldCaches() {
    return caches.keys().then(function (names) {
        return Promise.all(names.map(function (name) {
            if (KEEP_CACHES.indexOf(name) >= 0) return null;
            return caches.delete(name);
        }));
    });
}

self.addEventListener('install', function (event) {
    event.waitUntil(
        cacheAssets(SHELL_CACHE, SHELL_ASSETS).then(function () {
            return self.skipWaiting();
        })
    );
});

self.addEventListener('activate', function (event) {
    event.waitUntil(
        cleanOldCaches()
            .then(function () { return self.clients.claim(); })
            /* 先接管页面，再后台补齐三刊元数据（不阻塞用户操作） */
            .then(function () { return cacheAssets(SHELL_CACHE, DATA_ASSETS); })
    );
});

function isSameOrigin(url) {
    return url.origin === self.location.origin;
}

/* 响应类型校验：.json 要 JSON、.md 要文本，不能是 HTML */
function contentTypeMatches(path, response) {
    var ct = (response.headers.get('content-type') || '').toLowerCase();
    if (ct.indexOf('text/html') === 0) return false;
    if (/\.json$/.test(path) && ct.indexOf('json') === -1) return false;
    return true;
}

/* 导航请求：优先联网拿最新版，断网时回落到缓存的首页 */
function handleNavigate(request) {
    var key;
    try {
        key = cacheKeyFor(request);
    } catch (e) {
        key = request;
    }
    return fetch(request).then(function (response) {
        if (response && response.ok) {
            return putInRuntime(SHELL_CACHE, key, response, 9999).then(function () {
                return response;
            });
        }
        return caches.match(key).then(function (cached) {
            if (cached) return cached;
            return caches.match('./index.html').then(function (fallback) {
                if (fallback) return fallback;
                return response;
            });
        });
    }).catch(function () {
        return caches.match('./index.html').then(function (fallback) {
            return fallback || Response.error();
        });
    });
}

/* 静态资源与数据：缓存优先 */
function handleCacheFirst(request) {
    var key;
    try {
        key = cacheKeyFor(request);
    } catch (e) {
        key = request;
    }
    var path = new URL(request.url).pathname;
    var isMd = path.indexOf('/articles/') === 0;
    var cacheName = isMd ? MD_CACHE : RT_CACHE;
    var max = isMd ? MAX_MD_ENTRIES : MAX_RT_ENTRIES;

    return caches.match(key).then(function (cached) {
        if (cached) return cached;
        return fetch(request).then(function (response) {
            /* Cloudflare Pages 的 SPA 回退会把 404 变成 200 的 index.html。
               若照单全收，HTML 会被缓存到 .json / .md 的键上，
               文章页就会把整页 HTML 当正文渲染。所以这里做一次类型校验。 */
            if (response && response.ok && !contentTypeMatches(path, response)) {
                return new Response('', { status: 404, statusText: 'Not Found' });
            }
            return putInRuntime(cacheName, key, response, max).then(function () {
                return response;
            });
        }).catch(function () {
            return Response.error();
        });
    });
}

self.addEventListener('fetch', function (event) {
    var request = event.request;
    if (request.method !== 'GET') return;

    var url;
    try {
        url = new URL(request.url);
    } catch (e) {
        return;
    }
    if (!isSameOrigin(url)) return;          /* 跨域请求不接管 */

    if (request.mode === 'navigate') {
        event.respondWith(handleNavigate(request));
        return;
    }
    event.respondWith(handleCacheFirst(request));
});

/* 允许页面主动要求新 SW 立即生效 */
self.addEventListener('message', function (event) {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});
