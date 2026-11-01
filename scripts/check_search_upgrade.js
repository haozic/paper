#!/usr/bin/env node
/**
 * 跨刊检索内核体检
 *
 * 为什么需要这个脚本
 * ------------------
 * 跨刊标题检索是本轮新增的核心能力，有三条容易悄悄坏掉、且肉眼看不出来的性质：
 *
 *   1. 分组顺序必须是刊物展示顺序（qs → hqwg → djyj），组内必须年降期降；
 *   2. **跨刊命中必须是单刊「仅标题」命中的子集** —— 单刊匹配的是
 *      标题 + 作者 + 板块三者，跨刊只匹配标题，所以跨刊更窄。
 *      这条性质一旦破了，UI 文案「跨刊结果包含本刊全部命中」就会变成假话；
 *   3. 正文搜索窗口必须从「该刊数据里的最新年份」起算 3 年，
 *      不能读浏览器时间（用户机器日期是 2027 时窗口会算错）。
 *
 * 本脚本把 assets/js/app.js 里的实现**原样抽出来**跑，而不是另写一份，
 * 免得两边各改各的、悄悄漂移。做法沿用 scripts/check_related.js 的既有模式：
 * 正则抽出函数 → 丢进 vm 沙箱 → 用假实现顶掉 DOM 相关部分。
 *
 * 断言到**规则编号**一级：反向自检注入"已知坏数据"后，
 * 必须报出**它该报的那条规则**，否则用例假绿。
 *
 * 用法：
 *   node scripts/check_search_upgrade.js            # 体检，有问题返回非 0 退出码
 */

'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');
const APP_JS = path.join(ROOT, 'assets', 'js', 'app.js');
const INDEX_JSON = path.join(ROOT, 'data', 'search_index.json');

const MAG_ORDER = ['qs', 'hqwg', 'djyj'];

/* 从 app.js 里原样抽出指定函数 */
function grab(src, name) {
  const re = new RegExp('(?:^|\\n)(?:async )?function ' + name + '\\([\\s\\S]*?\\n}');
  const m = src.match(re);
  if (!m) throw new Error('在 assets/js/app.js 里找不到函数：' + name);
  return m[0].replace(/^\n/, '');
}

/* 从 app.js 里原样抽出指定常量声明 */
function grabConst(src, name) {
  const re = new RegExp('(?:^|\\n)const ' + name + ' = [^;]+;');
  const m = src.match(re);
  if (!m) throw new Error('在 assets/js/app.js 里找不到常量：' + name);
  return m[0].replace(/^\n/, '');
}

/* 载入 app.js 中与跨刊检索有关的纯函数 */
function loadApi() {
  const src = fs.readFileSync(APP_JS, 'utf8');
  const code = [
    grabConst(src, 'MAGAZINES'),
    grab(src, 'searchAllTitles'),
    grab(src, 'groupCrossMagResults'),
    grab(src, 'pickBodyWindow'),
    grab(src, 'formatBytes'),
    grab(src, 'articleMatches'),
    'globalThis.__api = { searchAllTitles, groupCrossMagResults, pickBodyWindow, formatBytes, articleMatches };',
  ].join('\n');

  const ctx = {
    console: console,
    Math: Math, Object: Object, Array: Array, String: String, Number: Number, JSON: JSON,
    Boolean: Boolean,
  };
  vm.createContext(ctx);
  vm.runInContext(code, ctx, { filename: 'app.js#search-upgrade' });
  return ctx.__api;
}

/* 一份结构完全合规的索引（正对照用） */
function makeIndex() {
  const rows = [];
  // qs：2020 年两期 + 2019 年一期，年降期降
  rows.push(['qs', 2020, 2, '求是新篇甲', 'http://q/2020-2-a']);
  rows.push(['qs', 2020, 1, '求是新篇乙', 'http://q/2020-1-a']);
  rows.push(['qs', 2019, 1, '求是旧篇', 'http://q/2019-1-a']);
  // hqwg：两期
  rows.push(['hqwg', 2021, 1, '红旗新篇甲', 'http://h/2021-1-a']);
  rows.push(['hqwg', 2020, 1, '红旗旧篇', 'http://h/2020-1-a']);
  // djyj：一期
  rows.push(['djyj', 2022, 1, '党建新篇甲', 'http://d/2022-1-a']);
  return { v: 'test', cols: ['m', 'y', 'i', 't', 'u'], rows: rows };
}

/* 单刊「仅标题」命中的实现口径：标题 + 作者 + 板块（与 app.js 的 articleMatches 一致）。
   查询词要小写化 —— app.js 的 performSearch 也是先小写再传给 articleMatches。 */
function singleMagHits(api, meta, query) {
  const ms = { meta: meta, bodyText: {} };
  const q = String(query || '').trim().toLowerCase();
  return meta.filter(function (a) {
    return api.articleMatches(a, q, 'title', ms);
  });
}

/* =====================================================================
 * 正文搜索显式触发部分
 * =====================================================================
 *
 * 「开始搜正文 / 继续搜索更早年份 / 停止」是**用户能点的开关**。
 * 这类开关最危险的坏法不是报错，而是"点了之后没有任何可测量的差异"：
 * 变量改了、函数跑了，界面文案却纹丝不动，用户只会觉得"这站坏了"。
 *
 * 所以这里断言：四种形态的按钮文案必须**互不相同**，
 * 并且每种形态的期数 / 字节数 / 年份区间必须与真实窗口算出来的一致。
 */

/* 造一份假 meta：2017~2026 每年一期，共 10 期 */
function fakeMeta() {
  const rows = [];
  for (let y = 2026; y >= 2017; y--) {
    rows.push({ y: y, i: 1, t: '标题' + y, a: '某作者', s: '某板块', u: 'http://x/' + y, h: 1 });
  }
  return rows;
}

function makeBodyEnv(opts) {
  const o = opts || {};
  const box = { innerHTML: '', hidden: false };
  const env = {
    scope: o.scope || 'all',
    magScope: o.magScope || 'current',
    query: o.query === undefined ? '中国' : o.query,
    bo: !!o.bo,
    ms: o.ms === undefined ? { meta: fakeMeta(), bodyText: {} } : o.ms,
    box: box,
    state: {
      currentMag: o.mag || 'qs',
      searchToken: 0,
      searchResults: [],
      bodySearchKey: '',
      bodySearchCursor: o.cursor || 0,
      bodySearchTotal: 0,
      bodySearchRunning: !!o.running,
      bodySearchDone: o.done || 0,
    },
  };
  return env;
}

/* 把正文搜索相关的实现原样抽出来跑，DOM 与状态用桩顶掉。
   overrides.pickBodyWindow 可以换成坏实现（反向自检用）。 */
function loadBodyApi(env, overrides) {
  const src = fs.readFileSync(APP_JS, 'utf8');
  const parts = [
    grabConst(src, 'BODY_AVG_BYTES'),
    grabConst(src, 'BODY_YEAR_SPAN'),
    grab(src, 'listBodyIssues'),
    grab(src, 'pickBodyWindow'),
    grab(src, 'formatBytes'),
    grab(src, 'estimateBodyBytes'),
    grab(src, 'updateBodySearchActions'),
    grab(src, 'articleMatches'),
    grab(src, 'collectMatches'),
    grab(src, 'startBodySearch'),
    grab(src, 'runBodySearch'),
    grab(src, 'stopBodySearch'),
  ];
  if (overrides && overrides.pickBodyWindow) parts[3] = overrides.pickBodyWindow;
  if (overrides && overrides.stopBodySearch) parts[11] = overrides.stopBodySearch;
  parts.push('globalThis.__api = { listBodyIssues, pickBodyWindow, formatBytes, estimateBodyBytes, updateBodySearchActions, collectMatches, startBodySearch, runBodySearch, stopBodySearch };');
  parts.push('globalThis.__avg = BODY_AVG_BYTES;');
  parts.push('globalThis.__span = BODY_YEAR_SPAN;');

  const ctx = {
    console: console,
    Math: Math, Object: Object, Array: Array, String: String, Number: Number, JSON: JSON,
    Boolean: Boolean, Set: Set, Promise: Promise,
    state: env.state,
    document: {
      getElementById: function (id) {
        if (id === 'bodySearchActions') return env.box;
        if (id === 'searchInput') return { value: env.query };
        if (id === 'bodyOnly') return { checked: env.bo };
        if (id === 'resultInfo') return { textContent: '' };
        return null;
      }
    },
    getSearchScope: function () { return env.scope; },
    getMagScope: function () { return env.magScope; },
    getMagState: function () { return env.ms; },
    /* 正文加载用桩：默认立刻返回；测「停止」时换成可控的 pending promise */
    loadIssueData: env.loadIssueData || function () { return Promise.resolve(); },
    renderSearchPage: env.renderSearchPage || function () {},
  };
  vm.createContext(ctx);
  vm.runInContext(parts.join('\n'), ctx, { filename: 'app.js#body-search' });
  ctx.__api.__avg = ctx.__avg;
  ctx.__api.__span = ctx.__span;
  return ctx.__api;
}

/* 窗口里跨了几个不同的年份 */
function distinctYears(win) {
  const s = {};
  win.forEach(function (it) { s[it.y] = true; });
  return Object.keys(s).length;
}

/* 四种形态：开始搜正文 / 继续搜索更早年份 / 正在加载 / 已全部完毕。
   返回违规列表（空数组 = 全部通过）。 */
function fourFormViolations(apiFactory) {
  const violations = [];
  const specs = [
    { cursor: 0, running: false, expect: '开始搜正文' },
    { cursor: 3, running: false, expect: '继续搜索更早年份' },
    { cursor: 3, running: true, expect: '正在加载正文' },
    { cursor: 10, running: false, expect: '已全部搜索完毕' },
  ];
  const htmls = [];
  specs.forEach(function (sp) {
    const env = makeBodyEnv({
      scope: 'all', magScope: 'current', cursor: sp.cursor,
      running: sp.running, done: sp.running ? 3 : 0,
    });
    const api = apiFactory(env);
    api.updateBodySearchActions();
    const h = env.box.innerHTML;
    htmls.push(h);
    if (h.indexOf(sp.expect) < 0) violations.push('形态缺「' + sp.expect + '」');
  });
  for (let i = 0; i < htmls.length; i++) {
    for (let j = i + 1; j < htmls.length; j++) {
      if (htmls[i] === htmls[j]) violations.push('形态 ' + i + ' 与形态 ' + j + ' 文案完全相同');
    }
  }
  return violations;
}

/* 渐进窗口的违规列表：第二个窗口必须严格更早，且不超过 BODY_YEAR_SPAN 年 */
function progressiveViolations(api) {
  const v = [];
  const issues = [];
  for (let y = 2026; y >= 2017; y--) issues.push({ y: y, i: 1, key: String(y) });
  const span = api.__span || 3;
  const first = api.pickBodyWindow(issues, span);
  const rest = issues.slice(first.length);
  const second = api.pickBodyWindow(rest, span);
  if (distinctYears(first) !== span) v.push('首个窗口跨 ' + distinctYears(first) + ' 年，应为 ' + span + ' 年');
  if (distinctYears(second) !== span) v.push('第二个窗口跨 ' + distinctYears(second) + ' 年，应为 ' + span + ' 年');
  if (first.length && second.length) {
    const firstOldest = Math.min.apply(null, first.map(function (it) { return it.y; }));
    const secondNewest = Math.max.apply(null, second.map(function (it) { return it.y; }));
    if (secondNewest >= firstOldest) v.push('第二个窗口没有严格更早（最新 ' + secondNewest + ' ≥ 首个窗口最旧 ' + firstOldest + '）');
  }
  if (first.length + second.length > issues.length) v.push('两个窗口加起来超过期次总数（会重复搜）');
  return v;
}

/* 跑一次「触发 → 停止 → 放行挂起数据」的流程。
   loadIssueData 换成永不自动兑现的 promise，这样「停止」发生在批次加载途中，
   正好检验停止之后过期循环会不会把结果写回界面。 */
function stopFlow(overrides) {
  const pending = [];
  const env = makeBodyEnv({ cursor: 0 });
  env.loadIssueData = function () {
    return new Promise(function (resolve) { pending.push(resolve); });
  };
  const api = loadBodyApi(env, overrides);
  api.startBodySearch();
  const runningHtml = env.box.innerHTML;
  const runningOk = env.state.bodySearchRunning === true
    && runningHtml.indexOf('正在加载正文') >= 0
    && runningHtml.indexOf('停止') >= 0;
  const tokenBefore = env.state.searchToken;
  const cursorBefore = env.state.bodySearchCursor;
  env.state.searchResults = ['sentinel'];
  api.stopBodySearch();
  const stoppedOk = env.state.bodySearchRunning === false
    && env.state.searchToken === tokenBefore + 1
    && env.state.bodySearchCursor === cursorBefore;
  pending.forEach(function (r) { r(); });
  return { env: env, runningOk: runningOk, stoppedOk: stoppedOk };
}

async function main() {
  console.log('='.repeat(72));
  console.log('跨刊检索内核体检');
  console.log('='.repeat(72));

  let api;
  try {
    api = loadApi();
  } catch (e) {
    console.log('❌ ' + e.message);
    if (/找不到函数|找不到常量/.test(e.message)) {
      console.log('   （说明 assets/js/app.js 里还没有这些函数，先实现再跑本脚本）');
    }
    process.exit(1);
  }

  const cases = [];
  function caseRule(rule, ok, detail) {
    cases.push({ rule: rule, ok: ok, detail: detail });
  }

  const index = makeIndex();

  /* ---- R1 空查询 ---- */
  caseRule('R1', api.searchAllTitles(index, '').length === 0
    && api.searchAllTitles(index, '   ').length === 0,
    '空查询 / 纯空格查询返回空数组');

  /* ---- R2 字段齐全 ---- */
  /* 查询词用「新篇」：能同时命中同一刊物里的两篇（求是 2020 年第 2 期与第 1 期），
     R4 的组内顺序断言才有样本可查（只命中一篇的话组内没有相邻对，断言会空转）。 */
  const hits = api.searchAllTitles(index, '新篇');
  const fieldsOk = hits.length === 4
    && hits.every(function (h) {
      return 'm' in h && 'y' in h && 'i' in h && 't' in h && 'u' in h
        && typeof h.m === 'string' && typeof h.y === 'number'
        && typeof h.i === 'number' && typeof h.t === 'string' && typeof h.u === 'string';
    });
  caseRule('R2', fieldsOk, '命中项字段齐全（' + hits.length + ' 条，期望 4 条）');

  /* ---- R3 组间顺序 ---- */
  const groups = api.groupCrossMagResults(hits);
  const magSeq = groups.map(function (g) { return g.mag; });
  const wantSeq = MAG_ORDER.filter(function (m) {
    return magSeq.indexOf(m) >= 0;
  });
  caseRule('R3', JSON.stringify(magSeq) === JSON.stringify(wantSeq),
    '组间顺序为展示顺序 qs→hqwg→djyj（实际 ' + JSON.stringify(magSeq) + '）');

  /* ---- R4 组内顺序 ---- */
  let innerOk = true;
  let innerDetail = '组内均为年降期降';
  groups.forEach(function (g) {
    for (let i = 1; i < g.items.length; i++) {
      const a = g.items[i - 1];
      const b = g.items[i];
      if (a.y < b.y || (a.y === b.y && a.i < b.i)) {
        innerOk = false;
        innerDetail = '组 ' + g.mag + ' 内顺序错：' + JSON.stringify(a) + ' 在 ' + JSON.stringify(b) + ' 之后';
        break;
      }
    }
  });
  caseRule('R4', innerOk, innerDetail);

  /* ---- R5 组计数 ---- */
  const countOk = groups.every(function (g) {
    return g.count === g.items.length;
  });
  caseRule('R5', countOk, '组计数 = 组内条数');

  /* ---- R6 子集性质：跨刊命中 ⊆ 单刊「仅标题」命中 ---- */
  /* 用真实的 data/search_index.json + 三份 meta 跑，这条才有意义 */
  let subsetOk = false;
  let subsetDetail = '未检查';
  if (fs.existsSync(INDEX_JSON)) {
    const realIndex = JSON.parse(fs.readFileSync(INDEX_JSON, 'utf8'));
    const metas = {
      qs: JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'qs', 'meta.json'), 'utf8')),
      hqwg: JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'hqwg', 'meta.json'), 'utf8')),
      djyj: JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'meta.json'), 'utf8')),
    };
    /* 抽样若干真实标题做子集验证 */
    const words = ['中国', '发展', '党', '建设', '思想'];
    let checked = 0;
    let violated = 0;
    words.forEach(function (w) {
      const cross = api.searchAllTitles(realIndex, w);
      if (!cross.length) return;
      checked++;
      const byMag = {};
      cross.forEach(function (h) { (byMag[h.m] = byMag[h.m] || []).push(h); });
      Object.keys(byMag).forEach(function (mag) {
        const meta = metas[mag] || [];
        const single = singleMagHits(api, meta, w);
        const singleUrls = {};
        single.forEach(function (a) { singleUrls[a.u] = true; });
        byMag[mag].forEach(function (h) {
          if (!singleUrls[h.u]) violated++;
        });
      });
    });
    subsetOk = violated === 0;
    subsetDetail = '抽样 ' + checked + ' 个词，跨刊命中越界 ' + violated + ' 条（应为 0）';
  }
  caseRule('R6', subsetOk, '子集性质：' + subsetDetail);

  /* ---- R7 窗口：最新年份起 3 年 ---- */
  const issues = [
    { y: 2026, i: 20, key: '2026-20' },
    { y: 2026, i: 1, key: '2026-1' },
    { y: 2025, i: 1, key: '2025-1' },
    { y: 2024, i: 1, key: '2024-1' },
    { y: 2023, i: 1, key: '2023-1' },
    { y: 2022, i: 1, key: '2022-1' },
  ];
  const win3 = api.pickBodyWindow(issues, 3);
  const win3Ok = win3.length === 4 && win3.every(function (it) { return it.y >= 2024; });
  caseRule('R7', win3Ok, '近 3 年窗口取到 ' + win3.length + ' 期（应为 4 期，2024~2026）');

  /* ---- R8 数据不足 3 年时取全部 ---- */
  const shortIssues = [
    { y: 2026, i: 1, key: '2026-1' },
    { y: 2025, i: 1, key: '2025-1' },
  ];
  const winShort = api.pickBodyWindow(shortIssues, 3);
  caseRule('R8', winShort.length === 2, '数据不足 3 年时取全部（' + winShort.length + ' 期）');

  /* ---- R9 formatBytes ---- */
  const fmtOk = api.formatBytes(0) === '0 B'
    && api.formatBytes(512) === '512 B'
    && api.formatBytes(1536) === '1.5 KB'
    && api.formatBytes(16 * 1024 * 1024) === '16.0 MB';
  caseRule('R9', fmtOk, 'formatBytes 输出格式正确');

  /* ---- 反向自检 R10：刊别写错 → 必须命中 R3 ---- */
  {
    const bad = JSON.parse(JSON.stringify(index));
    bad.rows[0][0] = 'djyj';                 /* 把 qs 的第一条改成 djyj */
    const badHits = api.searchAllTitles(bad, '新篇');
    const badGroups = api.groupCrossMagResults(badHits);
    const badSeq = badGroups.map(function (g) { return g.mag; });
    const badWant = MAG_ORDER.filter(function (m) { return badSeq.indexOf(m) >= 0; });
    const fires = JSON.stringify(badSeq) !== JSON.stringify(badWant);
    caseRule('R10', fires, '反向自检 R10：刊别写错 → R3 报出（实际顺序 ' + JSON.stringify(badSeq) + '）');
  }

  /* ---- 反向自检 R11：组内顺序打乱 → 必须命中 R4 ---- */
  {
    const bad = JSON.parse(JSON.stringify(index));
    const a = bad.rows[0];
    bad.rows[0] = bad.rows[1];
    bad.rows[1] = a;                        /* 2020-2 与 2020-1 对调 */
    const badHits = api.searchAllTitles(bad, '新篇');
    const badGroups = api.groupCrossMagResults(badHits);
    let fired = false;
    badGroups.forEach(function (g) {
      for (let i = 1; i < g.items.length; i++) {
        const x = g.items[i - 1];
        const y = g.items[i];
        if (x.y < y.y || (x.y === y.y && x.i < y.i)) { fired = true; }
      }
    });
    caseRule('R11', fired, '反向自检 R11：组内顺序打乱 → R4 报出');
  }

  /* ---- 反向自检 R12：跨刊命中多出单刊没有的条目 → 必须命中 R6 ---- */
  {
    /* 造一条单刊「仅标题」匹配不到的跨刊命中：标题含关键词，
       但同一篇文章在单刊里作者/板块/标题都不含该词 —— 构造一个"只存在于索引"的假条目 */
    const fakeIndex = {
      v: 'test', cols: ['m', 'y', 'i', 't', 'u'],
      rows: [['qs', 2026, 1, '独有关键词乙', 'http://q/fake']],
    };
    const fakeHits = api.searchAllTitles(fakeIndex, '独有关键词乙');
    const fakeMeta = [{ t: '别的标题', a: '某作者', s: '某板块', y: 2026, i: 1, u: 'http://q/fake', h: 0 }];
    const single = singleMagHits(api, fakeMeta, '独有关键词乙');
    const singleUrls = {};
    single.forEach(function (a) { singleUrls[a.u] = true; });
    const violated = fakeHits.filter(function (h) { return !singleUrls[h.u]; }).length;
    caseRule('R12', violated > 0, '反向自检 R12：越界条目被 R6 抓到（' + violated + ' 条）');
  }

  /* ---- R13 估算字节数：期次数 × 该刊均值，且三刊取值不同 ---- */
  {
    const env = makeBodyEnv({});
    const api = loadBodyApi(env);
    const three = [{ key: 'a' }, { key: 'b' }, { key: 'c' }];
    const q = api.estimateBodyBytes('qs', three);
    const h = api.estimateBodyBytes('hqwg', three);
    const d = api.estimateBodyBytes('djyj', three);
    const ok = q === 3 * api.__avg.qs
      && h === 3 * api.__avg.hqwg
      && d === 3 * api.__avg.djyj
      && q !== h && h !== d && q !== d
      && api.estimateBodyBytes('qs', []) === 0;
    caseRule('R13', ok,
      '估算字节数 = 期次数 × 该刊均值（qs 3 期 = ' + q + ' 字节），三刊取值互不相同');
  }

  /* ---- R14 四种形态互不相同 ---- */
  {
    const violations = fourFormViolations(function (env) { return loadBodyApi(env); });
    caseRule('R14', violations.length === 0,
      '按钮四种形态（开始/继续/加载中/已完成）文案互不相同'
      + (violations.length ? '：' + violations.join('；') : ''));
  }

  /* ---- R15 三刊模式 / 仅标题模式：不给正文按钮 ---- */
  {
    const envAll = makeBodyEnv({ magScope: 'all', scope: 'all' });
    const apiAll = loadBodyApi(envAll);
    apiAll.updateBodySearchActions();
    const envTitle = makeBodyEnv({ magScope: 'current', scope: 'title' });
    const apiTitle = loadBodyApi(envTitle);
    apiTitle.updateBodySearchActions();
    const ok = envAll.box.hidden === true && envAll.box.innerHTML === ''
      && envTitle.box.hidden === true && envTitle.box.innerHTML === '';
    caseRule('R15', ok,
      '三刊模式与「仅标题」模式下正文按钮区隐藏（三刊 hidden=' + envAll.box.hidden
      + '，仅标题 hidden=' + envTitle.box.hidden + '）');
  }

  /* ---- R16 渐进窗口：第二个窗口严格更早且不超过窗口跨度 ---- */
  {
    const env = makeBodyEnv({});
    const api = loadBodyApi(env);
    const violations = progressiveViolations(api);
    caseRule('R16', violations.length === 0,
      '正文窗口由近及远渐进、第二个窗口严格更早且不超过 ' + api.__span + ' 年'
      + (violations.length ? '：' + violations.join('；') : ''));
  }

  /* ---- R17 按钮文案里的期数 / 字节数必须与真实窗口一致 ---- */
  {
    const env = makeBodyEnv({ cursor: 0 });
    const api = loadBodyApi(env);
    api.updateBodySearchActions();
    const html = env.box.innerHTML;
    const issues = api.listBodyIssues(env.ms);
    const win = api.pickBodyWindow(issues, api.__span);
    const est = api.estimateBodyBytes('qs', win);
    const wantNum = '近 ' + api.__span + ' 年 ' + win.length + ' 期';
    const wantSize = '约 ' + api.formatBytes(est);
    const ok = html.indexOf(wantNum) >= 0 && html.indexOf(wantSize) >= 0;
    caseRule('R17', ok,
      '按钮文案与真实窗口一致（期望含「' + wantNum + '」「' + wantSize + '」）');
  }

  /* ---- R18 反向自检：窗口函数无视年份跨度 → R16 必须报出 ---- */
  {
    const bad = 'function pickBodyWindow(issues) { return issues || []; }';
    const env = makeBodyEnv({});
    const api = loadBodyApi(env, { pickBodyWindow: bad });
    const violations = progressiveViolations(api);
    caseRule('R18', violations.length > 0,
      '反向自检 R18：窗口函数坏掉 → R16 报出（' + violations.length + ' 条违规）');
  }

  /* ---- R19 反向自检：按钮渲染永远同一句 → R14 必须报出 ---- */
  {
    const violations = fourFormViolations(function (env) {
      return {
        updateBodySearchActions: function () {
          env.box.innerHTML = '<button>开始搜正文</button>';
          env.box.hidden = false;
        }
      };
    });
    caseRule('R19', violations.length > 0,
      '反向自检 R19：按钮渲染不随状态变化 → R14 报出（' + violations.length + ' 条违规）');
  }

  /* ---- R20 停止：断点保留 + 过期循环不把结果写回界面 ---- */
  {
    const flow = stopFlow(null);
    /* 放行挂起数据后让微任务队列跑完（await 一轮 macrotask 即可冲干净） */
    await new Promise(function (r) { setTimeout(r, 0); });
    const results = flow.env.state.searchResults;
    const notOverwritten = Array.isArray(results) && results.length === 1 && results[0] === 'sentinel';
    caseRule('R20', flow.runningOk && flow.stoppedOk && notOverwritten,
      '停止后：运行中按钮含「正在加载/停止」，停止后令牌作废、断点保留、已命中结果不被改写'
      + '（running=' + flow.runningOk + '，stopped=' + flow.stoppedOk + '，结果未改写=' + notOverwritten + '）');
  }

  /* ---- R21 反向自检：停止不作废令牌 → R20 必须报出 ---- */
  {
    const badStop = 'function stopBodySearch() { state.bodySearchRunning = false; updateBodySearchActions(); }';
    const flow = stopFlow({ stopBodySearch: badStop });
    await new Promise(function (r) { setTimeout(r, 0); });
    const results = flow.env.state.searchResults;
    const overwritten = !(Array.isArray(results) && results.length === 1 && results[0] === 'sentinel');
    caseRule('R21', overwritten,
      '反向自检 R21：停止不作废令牌 → R20 报出（过期循环改写了结果：' + overwritten + '）');
  }

  /* ---- R22 断点续跑：停止后再触发，窗口从断点继续而不是从头 ---- */
  {
    const env = makeBodyEnv({ cursor: 3 });
    const api = loadBodyApi(env);
    api.updateBodySearchActions();
    const html = env.box.innerHTML;
    /* 10 期假数据 2026~2017，断点 3 → 剩余 2023~2017 → 窗口 2021~2023 */
    const ok = html.indexOf('继续搜索更早年份') >= 0
      && html.indexOf('2021–2023 年') >= 0
      && html.indexOf('近 3 年') < 0;
    caseRule('R22', ok,
      '从断点续跑：断点 3 时的窗口是 2021–2023 年（不是重新从近 3 年开始）');
  }
  console.log('');
  let failed = 0;
  cases.forEach(function (c) {
    if (!c.ok) failed++;
    console.log('  ' + (c.ok ? 'OK  ' : 'FAIL') + ' ' + c.rule.padEnd(4) + ' ' + c.detail);
  });
  console.log('');
  console.log('  用例 %d 条，失败 %d 条', cases.length, failed);
  if (failed) {
    console.log('❌ 体检未通过');
    process.exit(1);
  }
  console.log('✅ 体检通过');
}

main();
