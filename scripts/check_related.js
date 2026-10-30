#!/usr/bin/env node
/**
 * 相关阅读算法体检
 *
 * 为什么需要这个脚本
 * ------------------
 * 相关阅读的推荐质量很难靠肉眼判断：打开一篇文章，看推荐的几条"像不像"，
 * 主观且不可复现。旧算法只看"同板块 + 在有序列表里离得近"，会把
 * 《求是》"评论"板块里 499 篇评论中毫不相干的几篇推给读者。
 *
 * 本脚本把 assets/js/app.js 里相关阅读用到的实现**原样抽出来**跑，
 * 而不是在这里另写一份实现 —— 否则两边很容易各改各的、悄悄漂移。
 * 纯展示的部分（DOM、HTML 转义、事件绑定）用假实现顶掉，
 * 被验证的打分与排序逻辑则是线上那份代码。
 *
 * 做两件事：
 *
 *   A. 板块名归一化用例：「目 录」「目　录」「目 录」必须合并成一个，
 *      空板块名必须归入「其他」。
 *   B. 对每本杂志的若干篇文章，同时跑**旧算法**和**新算法**，
 *      用同一套标题相似度给两边的结果打分并对比。
 *
 * 质量门槛（断言）：
 *   1. 归一化用例全部通过；
 *   2. 新算法推荐列表的相似度中位数，高于旧算法；
 *   3. 新算法 top1 相似度，不低于旧算法；
 *   4. 新算法 top1 相似度达到可用水平（≥0.15）。
 *
 * 用法：
 *   node scripts/check_related.js            # 体检，有问题返回非 0 退出码
 *   node scripts/check_related.js --show     # 顺便打印每篇文章的推荐明细
 */

'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');
const APP_JS = path.join(ROOT, 'assets', 'js', 'app.js');

const MAGAZINES = [
  { key: 'qs', name: '求是', meta: 'data/qs/meta.json' },
  { key: 'hqwg', name: '红旗文稿', meta: 'data/hqwg/meta.json' },
  { key: 'djyj', name: '党建研究', meta: 'data/meta.json' },
];

/* 从 app.js 里原样抽出指定函数 */
function grab(src, name) {
  const re = new RegExp('(?:^|\\n)function ' + name + '\\([\\s\\S]*?\\n}');
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

/* 假的相关阅读容器：只记录 innerHTML，不做真实渲染 */
function makeEl() {
  return {
    _html: '',
    hidden: true,
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = v; },
    querySelectorAll() { return []; },
  };
}

/* 载入 app.js 中与相关阅读有关的实现（展示层用假实现顶掉） */
function loadApi() {
  const src = fs.readFileSync(APP_JS, 'utf8');
  const code = [
    grabConst(src, 'CN'),
    grabConst(src, 'OTHER_SECTION'),
    grabConst(src, 'NOISE_TITLES'),
    grab(src, 'normalizeSection'),
    grab(src, 'sectionLabel'),
    grab(src, 'titleTokens'),
    grab(src, 'isNoiseTitle'),
    grab(src, 'getTitleIndex'),
    grab(src, 'titleSimilarity'),
    grab(src, 'issueLabel'),
    grab(src, 'renderRelatedArticles'),
    'globalThis.__api = { normalizeSection, sectionLabel, titleTokens, isNoiseTitle, getTitleIndex, titleSimilarity, issueLabel, renderRelatedArticles };',
  ].join('\n');

  const el = makeEl();
  const ctx = {
    console: console,
    Math: Math, Object: Object, Array: Array, String: String, Number: Number, JSON: JSON,
    encodeURIComponent: encodeURIComponent,
    escHtml: function (s) { return String(s == null ? '' : s); },   /* 不转义，方便回读标题 */
    document: { getElementById: function (id) { return id === 'articleRelated' ? el : null; } },
    getMagState: function () { return ctx.__ms; },
  };
  vm.createContext(ctx);
  vm.runInContext(code, ctx, { filename: 'app.js#related' });
  ctx.__el = el;
  return ctx;
}

/* 从 renderRelatedArticles 写出的 HTML 里回读推荐条目 */
function parseRelated(html) {
  const out = [];
  const re = /<span class="ap-related-meta">([^<]*)<\/span><span class="ap-related-name">([^<]*)<\/span>/g;
  let m;
  while ((m = re.exec(html))) out.push({ meta: m[1], title: m[2] });
  return out;
}

/* 按（年, 期, 抓取顺序）排好序 —— 与 app.js 的 getOrderedMeta 一致 */
function buildOrdered(meta) {
  const arr = meta.map(function (a, i) { return { a: a, i: i }; });
  arr.sort(function (x, y) {
    if (x.a.y !== y.a.y) return x.a.y - y.a.y;
    if (x.a.i !== y.a.i) return x.a.i - y.a.i;
    return x.i - y.i;
  });
  return arr;
}

/* ===== 旧算法（保留作对比基线）：同板块 + 距离近，同作者补充 ===== */
function oldRelated(meta, curIdx) {
  const ordered = buildOrdered(meta);
  let pos = -1;
  for (let i = 0; i < ordered.length; i++) {
    if (ordered[i].i === curIdx) { pos = i; break; }
  }
  const cur = meta[curIdx];
  const sameSec = [];
  const sameAuthor = [];
  for (let i = 0; i < ordered.length; i++) {
    const a = ordered[i].a;
    if (a.u === cur.u) continue;
    const d = Math.abs(i - pos);
    if (a.s && cur.s && a.s === cur.s) sameSec.push({ a: a, d: d });
    else if (cur.a && a.a === cur.a) sameAuthor.push({ a: a, d: d });
  }
  sameSec.sort(function (x, y) { return x.d - y.d; });
  sameAuthor.sort(function (x, y) { return x.d - y.d; });
  const picks = sameSec.slice(0, 5);
  for (let i = 0; i < sameAuthor.length && picks.length < 5; i++) {
    if (picks.every(function (p) { return p.a.u !== sameAuthor[i].a.u; })) picks.push(sameAuthor[i]);
  }
  return picks.map(function (p) { return p.a; });
}

/* ===== 新算法：直接调用 app.js 里的 renderRelatedArticles ===== */
function newRelated(ctx, ms, curIdx) {
  const ordered = buildOrdered(ms.meta);
  let pos = -1;
  for (let i = 0; i < ordered.length; i++) {
    if (ordered[i].i === curIdx) { pos = i; break; }
  }
  ctx.__ms = ms;
  ctx.__el._html = '';
  ctx.__api.renderRelatedArticles(ms.meta[curIdx], pos, ordered);
  return parseRelated(ctx.__el._html);
}

function median(arr) {
  if (!arr.length) return 0;
  const s = arr.slice().sort(function (a, b) { return a - b; });
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

/* ===== 主流程 ===== */
function main() {
  const showDetail = process.argv.includes('--show');
  const ctx = loadApi();
  const api = ctx.__api;

  console.log('='.repeat(72));
  console.log('相关阅读算法体检');
  console.log('='.repeat(72));

  /* ---- A. 板块名归一化 ---- */
  console.log('');
  console.log('[A] 板块名归一化');
  const normCases = [
    ['目 录', '未分栏目'],        // 半角空格
    ['目　录', '未分栏目'],       // 全角空格
    ['目 录', '未分栏目'],       // 不换行空格
    ['目 录', '未分栏目'],            // 全角 + 半角
    ['目录', '未分栏目'],            // 抓取脚本的兜底值（来源站没有这个栏目）
    ['', '未分栏目'],
    ['   ', '未分栏目'],
    ['评论', '评论'],
    [null, '未分栏目'],
    [undefined, '未分栏目'],
  ];
  let normBad = 0;
  normCases.forEach(function (c) {
    const got = api.normalizeSection(c[0]);
    const ok = got === c[1];
    if (!ok) normBad++;
    console.log('  %s normalizeSection(%s) = %s（期望 %s）',
      ok ? 'OK  ' : 'FAIL', JSON.stringify(c[0]), JSON.stringify(got), JSON.stringify(c[1]));
  });
  console.log('  「目 录」三种写法合并为同一个板块名：%s',
    api.normalizeSection('目　录') === api.normalizeSection('目 录') ? '是' : '否');
  console.log('  未分栏目的文章不显示板块名（sectionLabel 返回空串）：%s',
    api.sectionLabel('目 录') === '' && api.sectionLabel('') === ''
      && api.sectionLabel('文化中国') === '文化中国' ? '是' : '否');

  /* ---- B. 新旧算法对比 ---- */
  console.log('');
  console.log('[B] 新旧算法推荐质量对比');

  let samples = 0;
  const oldTop1 = [];
  const newTop1 = [];
  const oldMedians = [];
  const newMedians = [];

  MAGAZINES.forEach(function (mag) {
    const metaPath = path.join(ROOT, mag.meta);
    if (!fs.existsSync(metaPath)) {
      console.log('  跳过（缺少 %s）', mag.meta);
      return;
    }
    const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
    const ms = { meta: meta };
    api.getTitleIndex(ms);      // 预热，保证两边的计时口径一致

    /* 抽样：每本取 5 篇有正文的文章 */
    const picks = [];
    const step = Math.max(1, Math.floor(meta.length / 5));
    for (let i = 0; i < meta.length && picks.length < 5; i += step) {
      if (meta[i] && meta[i].h) picks.push(i);
    }
    if (!picks.length) return;

    console.log('');
    console.log('  ── %s（%d 篇）──', mag.name, meta.length);

    picks.forEach(function (curIdx) {
      samples++;
      const cur = meta[curIdx];
      const idx = api.getTitleIndex(ms);

      const oldList = oldRelated(meta, curIdx);
      const newList = newRelated(ctx, ms, curIdx);

      const simOfTitle = t => {
        const i = meta.findIndex(function (a) { return a.t === t; });
        return i >= 0 ? api.titleSimilarity(idx, curIdx, i) : 0;
      };
      const oldS = oldList.map(function (a) { return simOfTitle(a.t); });
      const newS = newList.map(function (x) { return simOfTitle(x.title); });

      oldTop1.push(oldS.length ? oldS[0] : 0);
      newTop1.push(newS.length ? newS[0] : 0);
      oldMedians.push(median(oldS));
      newMedians.push(median(newS));

      console.log('    当前：%s', String(cur.t).slice(0, 34));
      if (showDetail) {
        console.log('      旧：');
        oldList.forEach(function (a, k) {
          console.log('        %d. [%s] %s', k + 1, oldS[k].toFixed(3), String(a.t).slice(0, 34));
        });
        console.log('      新：');
        newList.forEach(function (x, k) {
          console.log('        %d. [%s] %s  <%s>', k + 1, newS[k].toFixed(3), String(x.title).slice(0, 34), x.meta);
        });
      }
    });
  });

  const mOld = median(oldMedians);
  const mNew = median(newMedians);
  const tOld = median(oldTop1);
  const tNew = median(newTop1);

  console.log('');
  console.log('  样本文章数：%d', samples);
  console.log('  top1 相似度中位数：旧 %s → 新 %s', tOld.toFixed(4), tNew.toFixed(4));
  console.log('  推荐列表相似度中位数：旧 %s → 新 %s', mOld.toFixed(4), mNew.toFixed(4));

  const checks = [
    { name: '归一化用例全部通过', ok: normBad === 0 },
    { name: '新算法推荐相似度中位数高于旧算法', ok: mNew > mOld },
    { name: '新算法 top1 相似度不低于旧算法', ok: tNew >= tOld },
    { name: '新算法 top1 相似度达到可用水平（≥0.15）', ok: tNew >= 0.15 },
  ];

  console.log('');
  let failed = 0;
  checks.forEach(function (c) {
    if (!c.ok) failed++;
    console.log('  %s %s', c.ok ? 'OK  ' : 'FAIL', c.name);
  });

  console.log('');
  if (failed) {
    console.log('❌ 体检未通过：%d 项不达标', failed);
    process.exit(1);
  }
  console.log('✅ 体检通过');
}

main();
