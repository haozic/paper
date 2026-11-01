#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Service Worker 导航处理体检：防"首页入口打不开"这一类回归

真实事故（2026-10-30，用户报"首页底部的备考指南和备考全书打不开"）
------------------------------------------------------------------
现象：点首页底部两个入口卡片 → 打开了新页面，但**空白、没有样式**。

因果链（已在浏览器 + 本地复现环境逐环验证）：

  1. Cloudflare Workers Static Assets 的 html_handling 会把 `.html` 路径
     **308 重定向**到无扩展名路径（/x/x.html → /x/x）。
  2. Service Worker 接管导航时，旧代码直接 `fetch(request)`。
     而在 Service Worker 里 fetch 一个 mode 为 navigate 的请求，**只要该地址
     发生跳转**，Fetch 规范就会把响应过滤成 opaque：
         status=0、ok=false、redirected=false、type='opaque'
     （实测诊断输出：BRANCH=not-ok / response.status=0 / response.redirected=false）
  3. 旧代码把 `!response.ok` 一律当成"断网"，于是回落到缓存的 index.html，
     把**首页 HTML 塞到了子页面地址上**。
  4. index.html 的 assets/css、assets/js 都是**相对路径**，在
     /linxuan-beikao-zhinan/ 目录下全部 404 —— 样式没了、app 没启动、
     body 几乎是空的 → 用户看到的就是"空白页 + 没有样式"。
  5. 缓存里查不到 index.html 时，SW 返回 Response.error()，
     浏览器直接 net::ERR_FAILED（chrome-error://chromewebdata/）。

本脚本做的是**行为级**检查，不是文本匹配：
把仓库里真正的 sw.js 装进一个 mock 的 Service Worker 环境，用一个会按
Fetch 规范"在 navigate 模式下把重定向响应过滤成 opaque"的假 fetch，
真的跑一遍导航，然后断言：

  T1  首页 `/` 正常联网 → 返回网络响应，而不是缓存里的 index.html
  T2  外壳路径 `/index.html`（线上会 308）→ 返回**不带 redirected 标记**的
      干净响应，且绝不是缓存里的 index.html
  T3  非外壳路径（备考指南等独立静态页）→ SW **不接管**，直接放行给网络
  T4  断网时首页 → 回落到缓存里的 index.html（离线能力不能丢）
  T5  缓存写入停滞时首页 → 仍立即返回网络响应

用法：
  python scripts/check_sw_navigate.py              # 跑行为检查（需要 node）
  python scripts/check_sw_navigate.py --self-test  # 反向自检（证明有鉴别力）
  python scripts/check_sw_navigate.py --list       # 列出用例

有问题返回非 0 退出码。
"""

import os
import subprocess
import sys
import tempfile

# Windows 控制台默认 GBK，直接打印中文会抛 UnicodeEncodeError。
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, ValueError):      # Python < 3.7 / 非标准流
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SW_REL = 'sw.js'


# --------------------------------------------------------------- node harness
#
# mock 的 Service Worker 全局环境：
#   * self         —— addEventListener / skipWaiting / clients.claim
#   * caches       —— open/match，match 命中时返回哨兵 CACHED_INDEX
#   * fetch        —— 按 Fetch 规范模拟"navigate 模式 + 跳转 → opaque 响应"
#   * Request/Response —— 轻量替身，够 sw.js 用
#
# 关键点：假 fetch 会**按请求的 mode 决定给不给真响应**。
# mode 为 navigate 且地址发生跳转 → 返回 opaque（status 0）。
# 这正是浏览器里的真实行为，也是本 bug 的触发条件。

NODE_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');

const swPath = process.argv[1];

const ORIGIN = 'https://example.invalid';
const listeners = {};

/* ---- 哨兵：缓存里的 index.html ---- */
const CACHED_INDEX = { __sentinel: 'CACHED_INDEX' };

/* ---- 轻量 Request ---- */
function MockRequest(url, init) {
  init = init || {};
  this.url = String(url);
  this.method = init.method || 'GET';
  this.mode = init.mode || 'no-cors';
  this.redirect = init.redirect || 'follow';
  this.credentials = init.credentials || 'same-origin';
  this.headers = { get: function () { return null; } };
}

/* ---- 轻量 Response ---- */
function MockResponse(init) {
  init = init || {};
  this.ok = init.ok !== undefined ? init.ok : true;
  this.status = init.status !== undefined ? init.status : 200;
  this.url = init.url || '';
  this.redirected = !!init.redirected;
  this.type = init.type || 'basic';
  this.headers = { get: function (k) { return init.headers ? init.headers[k] : null; } };
  this.clone = function () { return new MockResponse(init); };
}
MockResponse.error = function () {
  const r = new MockResponse({ ok: false, status: 0, type: 'error' });
  r.__isError = true;
  return r;
};

/* ---- 假 fetch：按 Fetch 规范模拟 navigate 模式下的 opaque 过滤 ---- */
let networkFails = false;
let cacheWriteStalls = false;
function mockFetch(input, init) {
  init = init || {};
  let url, mode;
  if (typeof input === 'string') {
    url = input;
    mode = init.mode || 'same-origin';
  } else {
    url = input.url;
    mode = init.mode || input.mode || 'same-origin';
  }
  if (networkFails) {
    return Promise.reject(new TypeError('Failed to fetch'));
  }
  const path = url.replace(ORIGIN, '');
  const isRedirectTarget = /\.html$/.test(path);

  if (mode === 'navigate' && isRedirectTarget) {
    /* Fetch 规范：navigate 模式下的重定向响应被过滤成 opaque */
    return Promise.resolve(new MockResponse({
      ok: false, status: 0, redirected: false, type: 'opaque', url: url
    }));
  }
  if (isRedirectTarget) {
    /* 普通模式：跳转被跟随，返回带 redirected 标记的最终响应 */
    const finalUrl = ORIGIN + path.replace(/\.html$/, '');
    return Promise.resolve(new MockResponse({
      ok: true, status: 200, redirected: true, type: 'basic', url: finalUrl
    }));
  }
  return Promise.resolve(new MockResponse({
    ok: true, status: 200, redirected: false, type: 'basic', url: url
  }));
}

/* ---- mock caches ---- */
const cacheStore = {};
const mockCaches = {
  open: function (name) {
    return Promise.resolve({
      put: function (k, v) {
        if (cacheWriteStalls) return new Promise(function () {});
        cacheStore[name + '|' + (k.url || k)] = v;
        return Promise.resolve();
      },
      keys: function () { return Promise.resolve([]); },
      delete: function () { return Promise.resolve(false); }
    });
  },
  keys: function () { return Promise.resolve([]); },
  match: function (req) {
    const u = typeof req === 'string' ? req : req.url;
    if (u === './index.html' || /\/index\.html$/.test(u) || /\/$/.test(u)) {
      return Promise.resolve(CACHED_INDEX);
    }
    return Promise.resolve(null);
  },
  delete: function () { return Promise.resolve(false); }
};

const ctx = {
  console: { log(){}, warn(){}, error(){} },
  URL, Promise, RegExp, JSON, Math, Date,
  Object, Array, String, Number, Boolean, Error, TypeError,
  decodeURIComponent, encodeURIComponent, setTimeout, clearTimeout,
  Request: MockRequest,
  Response: MockResponse,
  fetch: mockFetch,
  caches: mockCaches,
  self: {
    location: { search: '?v=test', origin: ORIGIN },
    addEventListener: function (t, f) { listeners[t] = f; },
    skipWaiting: function () { return Promise.resolve(); },
    clients: { claim: function () { return Promise.resolve(); } }
  }
};

vm.createContext(ctx);
try {
  vm.runInContext(fs.readFileSync(swPath, 'utf8'), ctx, { filename: swPath });
} catch (e) {
  console.log(JSON.stringify({ fatal: 'EVAL_FAILED ' + (e && e.name) + ': ' + (e && e.message) }));
  process.exit(1);
}

if (!listeners.fetch) {
  console.log(JSON.stringify({ fatal: 'MISSING_FETCH_LISTENER' }));
  process.exit(1);
}

/* ---- 跑一个导航用例 ---- */
function runNavigate(path, opts) {
  opts = opts || {};
  if (opts.offline) networkFails = true;
  cacheWriteStalls = !!opts.stallCache;
  const url = ORIGIN + path;
  const request = new MockRequest(url, { mode: 'navigate' });
  let responded = false;
  let result = null;
  let errored = null;

  const event = {
    request: request,
    waitUntil: function () {},
    respondWith: function (p) {
      responded = true;
      result = p;
    }
  };
  listeners.fetch(event);
  const response = opts.stallCache
    ? Promise.race([Promise.resolve(result), new Promise(function (resolve) {
        setTimeout(function () { resolve({ __stalled: true }); }, 150);
      })])
    : Promise.resolve(result);
  return response
    .catch(function (e) { errored = (e && e.name) + ': ' + (e && e.message); return null; })
    .then(function (resolved) {
      networkFails = false;
      cacheWriteStalls = false;
      let kind = 'none';
      if (errored) kind = 'rejected';
      else if (!responded) kind = 'not-handled';
      else if (resolved && resolved.__stalled) kind = 'cache-stalled';
      else if (resolved && resolved.__sentinel) kind = 'cached-index';
      else if (resolved && resolved.__isError) kind = 'response-error';
      else if (resolved && resolved.redirected) kind = 'redirected';
      else if (resolved && resolved.ok) kind = 'ok';
      else if (resolved && resolved.status === 0) kind = 'opaque';
      else kind = 'other';
      return { kind: kind, url: resolved && resolved.url ? resolved.url : '', error: errored };
    });
}

const cases = [];
Promise.resolve()
  .then(function () { return runNavigate('/'); })
  .then(function (r) { cases.push({ id: 'T1', ...r }); return runNavigate('/index.html'); })
  .then(function (r) { cases.push({ id: 'T2', ...r }); return runNavigate('/linxuan-beikao-zhinan/linxuan-beikao-zhinan.html'); })
  .then(function (r) { cases.push({ id: 'T3', ...r }); return runNavigate('/', { offline: true }); })
  .then(function (r) { cases.push({ id: 'T4', ...r }); return runNavigate('/', { stallCache: true }); })
  .then(function (r) { cases.push({ id: 'T5', ...r }); })
  .then(function () { console.log(JSON.stringify({ cases: cases })); })
  .catch(function (e) {
    console.log(JSON.stringify({ fatal: 'HARNESS_ERROR ' + (e && e.message) }));
    process.exit(1);
  });
"""


# 期望值：id -> (期望 kind, 说明)
EXPECT = {
    'T1': ('ok', '首页正常联网，应返回网络响应（不能是缓存里的 index.html）'),
    'T2': ('ok', '外壳路径 /index.html 线上会 308：应返回干净响应，既不能是缓存首页，也不能是带 redirected 标记的响应'),
    'T3': ('not-handled', '非外壳路径（备考指南等）应由 SW 放行，不接管导航'),
    'T4': ('cached-index', '断网时应回落到缓存里的 index.html（离线能力不能丢）'),
    'T5': ('ok', '缓存写入卡住时，首页网络响应仍应立即返回'),
}

# 判定"干净响应"：kind == 'ok'
KIND_OK = 'ok'


def sw_path():
    return os.path.join(BASE_DIR, SW_REL.replace('/', os.sep))


def run_harness(path):
    """在 mock SW 环境里跑 sw.js，返回 (ok, payload)。"""
    try:
        proc = subprocess.run(
            ['node', '-e', NODE_HARNESS, path],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        return None, '跳过：未找到 node'
    except subprocess.TimeoutExpired:
        return False, 'harness 超时（60 秒）'

    out = (proc.stdout or '').strip()
    err = (proc.stderr or '').strip()
    if proc.returncode != 0 and not out:
        return False, (err.split('\n')[0] if err else ('退出码 %s' % proc.returncode))

    import json
    line = out.split('\n')[-1] if out else ''
    try:
        payload = json.loads(line)
    except ValueError:
        return False, 'harness 输出无法解析：%s' % (line[:200] or err[:200])

    if 'fatal' in payload:
        return False, payload['fatal']
    return True, payload


def judge(payload):
    """把 harness 输出判成 [(用例id, 通过?, 说明)]。"""
    results = []
    got = {c['id']: c for c in payload.get('cases', [])}
    for cid in ('T1', 'T2', 'T3', 'T4', 'T5'):
        want, desc = EXPECT[cid]
        c = got.get(cid)
        if c is None:
            results.append((cid, False, '用例没有产出结果'))
            continue
        if c['kind'] == want:
            detail = ''
            if c['kind'] == KIND_OK and c.get('url'):
                detail = '（最终地址 %s）' % c['url']
            results.append((cid, True, desc + detail))
        else:
            results.append((cid, False, '%s；实际 kind=%s' % (desc, c['kind'])))
    return results


# ---------------------------------------------------------------- 反向自检

def self_test():
    """反向自检：把已知的事故形态注回去，本脚本必须抓得到。"""
    print('=' * 72)
    print('SW 导航体检 · 反向自检')
    print('=' * 72)

    passed = 0
    failed = 0

    real = sw_path()
    if not os.path.isfile(real):
        print('  SKIP 未找到 sw.js')
        return 1

    with open(real, encoding='utf-8') as f:
        good_src = f.read()

    # 注入事故形态：把导航抓取改回"用 navigate 模式直接 fetch"，
    # 也就是 2026-10-30 出事前的老写法。
    bad_src = good_src.replace("mode: 'same-origin'", "mode: 'navigate'")
    if bad_src == good_src:
        print('  SKIP 无法注入事故形态（sw.js 里没有 mode: \'same-origin\'）')
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        bad_path = os.path.join(tmp, 'sw-bad.js')
        with open(bad_path, 'w', encoding='utf-8') as f:
            f.write(bad_src)

        ok_bad, payload_bad = run_harness(bad_path)
        ok_good, payload_good = run_harness(real)

    if ok_bad is not True:
        print('  FAIL 注入事故形态后 harness 自身报错：%s' % payload_bad)
        failed += 1
    else:
        res_bad = judge(payload_bad)
        bad_ids = [cid for (cid, good, _) in res_bad if not good]
        c1 = 'T2' in bad_ids
        print('  %s 注入"navigate 模式直取"后 T2 必须失败（实际失败用例：%s）'
              % ('OK  ' if c1 else 'FAIL', ','.join(bad_ids) or '无'))
        passed += 1 if c1 else 0
        failed += 0 if c1 else 1

    if ok_good is not True:
        print('  FAIL 当前 sw.js 跑不通 harness：%s' % payload_good)
        failed += 1
    else:
        res_good = judge(payload_good)
        bad_ids = [cid for (cid, good, _) in res_good if not good]
        c2 = not bad_ids
        print('  %s 当前 sw.js 必须全部用例通过（实际失败用例：%s）'
              % ('OK  ' if c2 else 'FAIL', ','.join(bad_ids) or '无'))
        passed += 1 if c2 else 0
        failed += 0 if c2 else 1

    print('')
    print('%d/%d 通过' % (passed, passed + failed))
    return 0 if failed == 0 else 1


# ---------------------------------------------------------------- 主流程

def main():
    argv = sys.argv[1:]

    if '--self-test' in argv:
        return self_test()

    print('=' * 72)
    print('Service Worker 导航处理体检')
    print('=' * 72)

    if '--list' in argv:
        for cid in ('T1', 'T2', 'T3', 'T4', 'T5'):
            print('  %s  %s' % (cid, EXPECT[cid][1]))
        print('')
        return 0

    path = sw_path()
    if not os.path.isfile(path):
        print('跳过：未找到 sw.js')
        return 0

    ok, payload = run_harness(path)
    if ok is None:
        print('跳过：%s' % payload)
        return 0
    if ok is False:
        print('❌ harness 执行失败：%s' % payload)
        return 1

    results = judge(payload)
    failed = 0
    for (cid, good, desc) in results:
        print('%s %s' % ('✅' if good else '❌', cid + '：' + desc))
        if not good:
            failed += 1

    print('')
    if failed:
        print('❌ 体检未通过：%d 个用例失败' % failed)
        return 1
    print('✅ 体检通过：%d 个用例全部符合预期' % len(results))
    return 0


if __name__ == '__main__':
    sys.exit(main())
