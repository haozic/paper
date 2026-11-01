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

function main() {
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
