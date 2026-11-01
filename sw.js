/* Service Worker —— 离线阅读（P2-1）
 *
 * 目标
 * ----
 * 1. 应用外壳（index.html / CSS / JS / manifest / 图标 / 封面）预缓存，
 *    断网也能正常打开并显示完整样式；
 * 2. 三刊的 meta 在后台预缓存；搜索索引和文章索引按需加载，避免每次更新重下大文件；
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
        return m ? decodeURIComponent(m[1]) : '20261101x';
    } catch (e) {
        return '20261101x';
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
    './assets/css/books.css?v=' + VERSION,
    './assets/css/one.css?v=' + VERSION,
    './assets/css/system.css?v=' + VERSION,
    './assets/css/modern.css?v=' + VERSION,
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

/* 三刊元数据：activate 后台补齐；大索引在首次使用时再缓存。 */
var DATA_ASSETS = [
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
    var copy;
    try {
        key = cacheKeyFor(request);
        copy = response.clone();
    } catch (e) {
        return Promise.resolve(null);
    }
    return caches.open(cacheName).then(function (cache) {
        return cache.put(key, copy).then(function () {
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

/* 应用外壳路由：只有首页由 SW 接管导航。
   其余路径（备考指南等独立静态页）一律放行给网络，
   浏览器自己处理 Cloudflare 的 .html -> 无扩展名 308 重定向。 */
function isShellPath(pathname) {
    return pathname === '/' || pathname === '/index.html';
}

/* 取一份可用于"导航响应"的正文；拿不到可用正文时返回 null。
 *
 * 两个必须绕开的坑：
 *
 * 1) 不能直接 fetch(导航请求)。在 Service Worker 里 fetch 一个 mode 为
 *    navigate 的请求时，只要该地址发生跳转（Cloudflare Workers Static
 *    Assets 会把 .html 308 重定向到无扩展名路径），Fetch 规范会把响应
 *    过滤成 opaque：status=0、ok=false、redirected=false。
 *    旧代码把 !response.ok 一律当成"断网"，于是回落到缓存的 index.html，
 *    把首页 HTML 塞到子页面地址上；首页的 assets/ 是相对路径，
 *    在子目录下全部 404 —— 用户看到的就是"打开新页面但空白、没有样式"。
 *    所以这里改用 mode:'same-origin' 的普通 GET，跳转会被正常跟随，
 *    拿到 status 200 的真实响应。
 *
 * 2) 跟随跳转后拿到的响应带 redirected 标记，部分浏览器不收这种导航响应。
 *    所以再按最终地址补抓一次，拿到不带 redirected 的干净响应。
 */
function fetchShell(request) {
    var plain;
    try {
        plain = new Request(request.url, {
            method: 'GET',
            mode: 'same-origin',
            credentials: 'same-origin',
            redirect: 'follow'
        });
    } catch (e) {
        plain = request;
    }
    return fetch(plain).then(function (response) {
        if (!response || !response.ok || response.status === 0) return null;
        if (response.redirected && response.url) {
            return fetch(response.url, { credentials: 'same-origin' })
                .then(function (clean) {
                    return (clean && clean.ok && clean.status !== 0) ? clean : response;
                })
                .catch(function () {
                    return response;
                });
        }
        return response;
    });
}

/* 导航请求：优先联网拿最新版，断网时回落到缓存的首页 */
function handleNavigate(request, event) {
    var key;
    try {
        key = cacheKeyFor(request);
    } catch (e) {
        key = request;
    }
    var network = fetchShell(request);
    if (event && event.waitUntil) {
        event.waitUntil(network.then(function (response) {
            return response ? putInRuntime(SHELL_CACHE, key, response, 9999) : null;
        }).catch(function () { return null; }));
    }
    return network.then(function (response) {
        if (response) return response;
        /* 没拿到正文：回落到缓存里的首页（仅限应用外壳路由） */
        return caches.match('./index.html').then(function (fallback) {
            return fallback || Response.error();
        });
    }).catch(function () {
        return caches.match('./index.html').then(function (fallback) {
            return fallback || Response.error();
        });
    });
}

/* 静态资源与数据：缓存优先 */
function handleCacheFirst(request, event) {
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

    var fromNetwork = null;
    var result = caches.match(key).then(function (cached) {
        if (cached) return cached;
        return fetch(request).then(function (response) {
            /* Cloudflare Pages 的 SPA 回退会把 404 变成 200 的 index.html。
               若照单全收，HTML 会被缓存到 .json / .md 的键上，
               文章页就会把整页 HTML 当正文渲染。所以这里做一次类型校验。 */
            if (response && response.ok && !contentTypeMatches(path, response)) {
                return new Response('', { status: 404, statusText: 'Not Found' });
            }
            fromNetwork = response;
            return response;
        }).catch(function () {
            return Response.error();
        });
    });
    if (event && event.waitUntil) {
        event.waitUntil(result.then(function (response) {
            return response && response === fromNetwork ? putInRuntime(cacheName, key, response, max) : null;
        }).catch(function () { return null; }));
    }
    return result;
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
        /* 只有应用外壳路由才接管导航；备考指南等独立静态页放行给网络，
           避免 SW 参与它们的 308 重定向处理（见 fetchShell 注释里的坑 1）。 */
        if (!isShellPath(url.pathname)) return;
        event.respondWith(handleNavigate(request, event));
        return;
    }
    event.respondWith(handleCacheFirst(request, event));
});

/* 允许页面主动要求新 SW 立即生效 */
self.addEventListener('message', function (event) {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});
