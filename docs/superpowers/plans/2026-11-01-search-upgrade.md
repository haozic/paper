# 检索能力升级实施计划（跨刊标题检索 + 正文搜索降本）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让站内检索能跨三刊按标题搜索，并把正文搜索从「一次随手搜索换来 43 MB 下载」改成「显式触发 + 由近及远渐进」。

**Architecture:** 新增一份派生的紧凑标题索引 `data/search_index.json`（只含刊物/年份/期号/标题/URL 五列），由 `scripts/build_search_index.py` 从三份 `meta.json` 生成，`scripts/check_data.py` 强制断言二者一致。前端在 `assets/js/app.js` 里新增一组**纯函数**（`searchAllTitles` / `groupCrossMagResults` / `pickBodyWindow` / `formatBytes`），由 `scripts/check_search_upgrade.js` 用 `vm` 沙箱把线上实现原样抽出来跑（沿用 `scripts/check_related.js` 的既有做法）。正文搜索改为「先只出标题结果 → 用户点「开始搜正文」→ 按近 3 年窗口渐进加载 → 可继续搜更早年份 → 可随时停止」。

**Tech Stack:** 纯静态站点，零构建、零 npm 运行时依赖。Python 3.8+ 标准库（数据脚本）、Node（仅开发期体检脚本，沿用既有 `check_related.js` 惯例）、原生 ES2017 级 JS、CSS 变量。

**设计依据:** `docs/superpowers/specs/2026-11-01-search-upgrade-design.md`（决策 D1–D7）。本计划是该文档的实施化，若两者冲突以本计划为准（已在下文「与设计文档的两处修正」列出）。

---

## Global Constraints

以下约束适用于**每一个**任务，不再逐条重复：

1. **保留 Chrome 69（2018 年）**：禁用 `?.`、`??`、`||=`/`&&=`/`??=`、`Object.fromEntries`、`String.prototype.matchAll/replaceAll`、`Promise.allSettled/any`、`Object.hasOwn`、`replaceChildren`、`at(-1)`、`findLast/findLastIndex`、`globalThis`、`structuredClone`、`WeakRef`、`URL.canParse`、`Intl.ListFormat/RelativeTimeFormat/Segmenter`、类私有字段。
2. **CSS 黑名单**：禁用 `inset:` 简写、`accent-color`、`content-visibility`（除非放在 `@supports (content-visibility: auto)` 块内）、`scrollbar-gutter`、`text-wrap`、`text-underline-offset`、`text-decoration-skip-ink`、`line-clamp`、`background-clip: text`、`color-mix()`、`oklch()/oklab()/lab()/lch()`、`min()/max()/clamp()` CSS 函数、`dvh/svh/lvh/dvw/svw` 单位、`backdrop-filter`（必须同时给 `-webkit-backdrop-filter`）、`aspect-ratio`（必须给 `@supports not (aspect-ratio: 3 / 4)` 兜底）、`appearance`（必须同时给 `-webkit-appearance`）、`:has()`（必须由 JS 同步 `.checked` 类兜底）、`:is()`、`:where()`、`:focus-visible`、`::marker`、`@container`、`@layer`。
3. **flex gap 兜底**：任何 `display:flex` / `display:inline-flex` 且带 `gap` 的选择器，必须在 `assets/css/style.css` 末尾的 `@supports not (aspect-ratio: 3 / 4)` 兜底块里出现等价 `margin`（`gap: 0` + `> * + *` 补 margin）。**grid 的 gap 自 Chrome 66 起支持，不需要兜底。**
4. **JS 块注释里禁止出现 `/*`**（会提前闭合注释，其后的文字被当成代码解析，语法合法但求值期炸）。`scripts/check_js_comments.py` 会拦。
5. **缓存破坏五件套**：只要改动 `index.html` / `assets/css/style.css` / `assets/js/app.js` / `sw.js` **任一文件的内容**（不只是数据），必须同步升版本号：
   - `index.html` 四处 `?v=`：`style.css` / `manifest.webmanifest` / `apple-touch-icon` / `app.js`
   - `assets/js/app.js` 的 `DATA_VERSION` 常量
   - `sw.js` 两处兜底版本值（`'20261031b'` 字面量，出现两次）
   共 **7 处**。漏一处 → 回访用户继续命中 SW 运行时缓存里的旧文件。
6. **提交规范**：本仓库用**批次式 commit**（一次提交只做一件事，中文提交信息）。提交信息正文必须**诚实写明验证范围**，并标注「已实现但未独立审查」。不要写「已验证通过」这种没有指明验证方式的说法。
7. **推送命令**（Windows，gh 凭据助手）：
   `git -C E:/cursor/djyj -c credential.helper= -c credential.helper="!gh auth git-credential" push origin main`
8. **Bash 安全策略**：命令一律用绝对路径或 `git -C E:/cursor/djyj`，**不要 `cd`**；可恢复删除必须是**顶层单条纯命令**、一次不超过约 8 个目标、不得与其他命令串在同一条。
9. **Windows 控制台是 GBK**：Python 脚本 print 中文/emoji 前必须 `sys.stdout.reconfigure(encoding='utf-8', errors='replace')`。
10. **体检脚本必须复用线上实现**：断言要跑的是 `assets/js/app.js` / `sw.js` 里的真实代码（用正则抽出后丢进 `vm` 沙箱），不得在体检脚本里另写一份实现。反向自检必须**断言到规则编号一级**（断言「命中的是 R7 这条规则」，不是「报错了」）。
11. **书体例**：文白夹杂、口语化、网络用语、英文夹杂一律避免；纯 HTML 片段用 `<strong>` 不用 `**`；引号统一用 ASCII 直引号 `"` / `'`。
12. **浏览器策略**：**禁止代填密码框**（首页密码门密码 `5255`，localStorage 键 `djyj_gate_ok` / `djyj_gate_ts`，12 小时会话）。验证首页必须用临时副本隐藏遮罩（`#gate{display:none!important}body.gate-active{overflow:auto!important}`），不得用脚本绕过认证。
13. **视觉交付必须目检**：任何界面改动都要**渲染成图片逐张看过**，不能只看单测/构建结果。窄屏（<768px）时 `.nav-tab` 隐藏，须点 `.bn-item[data-mode="catalog"]` 进目录视图。

### 与设计文档的三处修正

设计文档 §4.1、§6.3、§8.1 有三处与代码实际或真实数据不符，本计划按**代码实际 + 真实数据**执行，并在 Task 14 一并更正文档：

| 位置 | 设计文档原文 | 实际 | 本计划做法 |
| --- | --- | --- | --- |
| §4.1 行序 | 「`qs → hqwg → djyj` 升序」 | 字母序应为 `djyj → hqwg → qs`；但显式列出的 `qs → hqwg → djyj` 与站点展示顺序、`scripts/check_data.py` 的 `MAGAZINES` 列表一致 | **以显式列表为准**：固定顺序 `qs → hqwg → djyj`（不是字母序） |
| §6.3 正文期次顺序 | 「`listBodyIssues(ms)` 改为按 (y, i) 降序」 | `assets/js/app.js:316` **本来就是** `list.sort((x, y) => (y.y - x.y) \|\| (y.i - x.i))`，即已是新→旧 | **不改 `listBodyIssues` 的排序**；正文搜索直接复用它，只做窗口截取 |
| §8.1 S3 规则 | 「无重复 \| 索引内 URL 无重复」 | 真实数据：三刊 meta 合计 7415 行、唯一 URL **7413** 个。「网站声明」同时出现在《求是》和《红旗文稿》的目录里（http / https 各一组） | **S3 改为「同一刊物内 URL 无重复」**。跨刊重复是真实数据，全局去重会破坏 S1（行数必须等于 meta 条目数之和） |

---

## 文件清单

### 新建

| 文件 | 职责 | 何时写 |
| --- | --- | --- |
| `scripts/build_search_index.py` | 索引生成器：`--check` 逐字节比对、`--self-test` ≥12 条（含 3 条反向自检）、`--print-avg` 测每期正文均值字节 | Task 1 |
| `data/search_index.json` | 派生产物：跨三刊的紧凑标题索引（7415 行，实测 1,000,280 字节 ≈ 977 KB，低于 1.5 MB 上限） | Task 2 |
| `scripts/check_search_upgrade.js` | 跨刊检索内核体检：把 `app.js` 里的纯函数原样抽出来跑，断言分组顺序、窗口选取、子集性质 + 3 条反向自检 | Task 3 |

### 修改

| 文件 | 改什么 | 任务 |
| --- | --- | --- |
| `scripts/check_data.py` | 新增 S1–S4 四条索引一致性断言 | Task 2 |
| `assets/js/app.js` | 新增 `state.searchIndex` 等 6 个状态字段；新增 `loadSearchIndex` / `searchAllTitles` / `groupCrossMagResults` / `pickBodyWindow` / `formatBytes` / `estimateBodyBytes` / `getMagScope` / `syncMagScopeChecked` / `renderCrossMagResults` / `openGlobalSearch` / `closeGlobalSearch` / `runGlobalSearch`；改 `performSearch`（加 `magScope` 维度）、`renderSearchPage`（跨刊分支）、`finishSearch` | Task 4 / 5 / 6 / 8 / 9 |
| `index.html` | 搜索栏加「本刊 / 三刊」范围开关；结果区加 `#bodySearchActions` 容器；首页头加放大镜按钮；加 `#globalSearch` 全屏浮层 | Task 5 / 6 / 8 |
| `assets/css/style.css` | 新增 `.home-search-btn` / `.mag-scope-wrap` / `.result-group*` / `.gs-*` / `.body-search-actions` / `.btn-ghost` 等样式；末尾 `@supports not (aspect-ratio: 3 / 4)` 兜底块补对应 margin | Task 5 / 6 / 8 / 12 |
| `sw.js` | `DATA_ASSETS` 加 `./data/search_index.json?v=` + VERSION；两处兜底版本值升版 | Task 7 / 10 / 13 |
| `scripts/README.md` | 补 `build_search_index.py` 与 `check_search_upgrade.js` 的用法条目 | Task 2 / 3 |
| `docs/UPDATE_FLOW.md` | 补「数据更新后必须重建索引并升 `INDEX_VERSION`」一步 | Task 2 |
| `docs/superpowers/specs/2026-11-01-search-upgrade-design.md` | 更正 §4.1 / §6.3 两处与代码不符的表述 | Task 14 |
| `linxuan-beikao-zhinan/linxuan-beikao-zhinan.html`<br>`hubei-linxuan-guide/hubei-linxuan-guide.html`<br>`hubei-linxuan-mianshi/hubei-linxuan-mianshi.html` | 各内联一段密码门逻辑；后两者补「返回刊物首页」入口 | Task 11 |

### 版本号时间线

| 批次 | `DATA_VERSION` / `?v=` | 索引自身 `v`（`INDEX_VERSION`） |
| --- | --- | --- |
| 起点 | `20261031b` | —— |
| 批次一末（Task 7） | `20261101a` | `20261101a` |
| 批次二末（Task 10） | `20261101b` | `20261101a`（meta 未变，索引不变） |
| 批次三末（Task 13） | `20261101c` | `20261101a`（meta 未变，索引不变） |

---

## 批次一：索引 + 跨刊标题检索

### Task 1: 索引生成器 `scripts/build_search_index.py`

**Files:**
- Create: `scripts/build_search_index.py`
- Read: `data/qs/meta.json`、`data/hqwg/meta.json`、`data/meta.json`

**Interfaces:**
- Consumes: 三份 `meta.json`，每条形如 `{"t": 标题, "a": 作者, "s": 板块, "y": 年, "i": 期, "u": URL, "h": 有无正文}`。
- Produces:
  - `build_index(metas)` → `dict`，结构 `{"v": str, "cols": ["m","y","i","t","u"], "rows": [[mag, y, i, title, url], ...]}`
  - `dump_index(index)` → `str`，紧凑 JSON 文本（`ensure_ascii=False`，`separators=(',', ':')`）
  - `INDEX_VERSION` 常量 = `'20261101a'`
  - `MAG_ORDER` 常量 = `['qs', 'hqwg', 'djyj']`（**展示顺序**，非字母序）
  - `MAX_INDEX_BYTES = 1_572_864`（1.5 MB）
  - 命令行：`--check`（逐字节比对，不一致退出码 1）、`--self-test`（≥12 条用例）、`--print-avg`（打印各刊每期正文分片实测均值字节）

- [ ] **Step 1: 写生成器骨架**

创建 `scripts/build_search_index.py`：

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
跨刊标题索引生成器。

为什么要这个脚本
----------------
站内检索原先锁死在"当前这一本刊"，想跨刊找一篇文章只能三本各搜一遍。
本脚本从三份 meta.json 生成一份紧凑的全局标题索引 data/search_index.json，
让前端一次请求就能跨三刊按标题匹配。

索引是**派生产物**：三份 meta.json 仍是唯一权威源。
`scripts/check_data.py` 的 S1~S4 规则会强制断言二者一致（**由 Task 2 落地**）。

索引形状
--------
    {
      "v": "20261101a",                  # 索引自身版本，meta 变了就要升
      "cols": ["m", "y", "i", "t", "u"], # 固定列序
      "rows": [                          # 每行 5 列
        ["qs", 2019, 1, "本期导读", "http://..."],
        ...
      ]
    }

行序（前端取到即得"新→旧"，不必在客户端再排）：
    刊物按展示顺序 qs → hqwg → djyj（不是字母序）
    → 年份降序 → 期号降序 → 期内沿用 meta.json 现有顺序（= 官网目录顺序）

用法
----
    python scripts/build_search_index.py             # 生成 data/search_index.json
    python scripts/build_search_index.py --check     # 重新生成并逐字节比对，不一致退出码 1
    python scripts/build_search_index.py --self-test # 跑内置用例（含反向自检）
    python scripts/build_search_index.py --print-avg # 打印各刊每期正文分片实测均值字节
"""

import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, ValueError):      # Python < 3.7 / 非标准流
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)

INDEX_VERSION = '20261101a'
INDEX_PATH = 'data/search_index.json'

# 刊物**展示顺序**：与 app.js 的 MAGAZINES、check_data.py 的 MAGAZINES 一致。
# 不是字母序（字母序会是 djyj → hqwg → qs），前端按这个顺序分组展示。
MAG_ORDER = ['qs', 'hqwg', 'djyj']

# 三刊 meta 路径，顺序同 MAG_ORDER
META_PATHS = [
    ('qs', 'data/qs/meta.json'),
    ('hqwg', 'data/hqwg/meta.json'),
    ('djyj', 'data/meta.json'),
]

MAX_INDEX_BYTES = 1_572_864     # 1.5 MB


def load_json(rel_path):
    full = os.path.join(BASE_DIR, rel_path)
    with open(full, encoding='utf-8') as f:
        return json.load(f)


def build_index(metas):
    """metas: [(mag, meta_list), ...] → 索引 dict。

    行序：刊物展示顺序 → 年降 → 期降 → 期内 meta 原有顺序。
    """
    rows = []
    by_mag = dict(metas)
    for mag in MAG_ORDER:
        meta = by_mag.get(mag) or []
        # 年份降序、期号降序；同一年同一期内部保持 meta 原有顺序（稳定排序）
        indexed = list(enumerate(meta))
        indexed.sort(key=lambda pair: (-pair[1]['y'], -pair[1]['i'], pair[0]))
        for _pos, a in indexed:
            rows.append([mag, a['y'], a['i'], a['t'], a['u']])
    return {'v': INDEX_VERSION, 'cols': ['m', 'y', 'i', 't', 'u'], 'rows': rows}


def dump_index(index):
    return json.dumps(index, ensure_ascii=False, separators=(',', ':'))
```

- [ ] **Step 2: 加生成 / 校验 / 体积守卫的 CLI**

在 `scripts/build_search_index.py` 末尾追加：

```python
def read_disk():
    full = os.path.join(BASE_DIR, INDEX_PATH)
    if not os.path.exists(full):
        return None
    with open(full, 'rb') as f:
        return f.read()


def write_disk(text):
    full = os.path.join(BASE_DIR, INDEX_PATH)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


def load_metas():
    return [(mag, load_json(path)) for mag, path in META_PATHS]


def print_avg():
    """打印各刊每期正文分片的实测均值字节，供 app.js 的 BODY_AVG_BYTES 常量对账。"""
    for mag, meta_path in META_PATHS:
        meta = load_json(meta_path)
        issues_dir = os.path.join(BASE_DIR, os.path.dirname(meta_path), 'issues')
        sizes = []
        seen = set()
        for a in meta:
            if not a.get('h'):
                continue
            key = '%d-%d' % (a['y'], a['i'])
            if key in seen:
                continue
            seen.add(key)
            full = os.path.join(issues_dir, key + '.json')
            if os.path.exists(full):
                sizes.append(os.path.getsize(full))
        if sizes:
            print('%-6s 期数 %3d   总计 %8.1f MB   每期均值 %d 字节'
                  % (mag, len(sizes), sum(sizes) / 1048576.0, sum(sizes) // len(sizes)))


def main():
    if '--self-test' in sys.argv:
        return self_test()
    if '--print-avg' in sys.argv:
        print_avg()
        return 0

    metas = load_metas()
    index = build_index(metas)
    text = dump_index(index)
    size = len(text.encode('utf-8'))

    if size > MAX_INDEX_BYTES:
        print('!! 索引体积 %d 字节，超过上限 %d 字节，拒绝写盘' % (size, MAX_INDEX_BYTES))
        return 1

    if '--check' in sys.argv:
        disk = read_disk()
        if disk is None:
            print('!! 缺少 %s，请先运行 python scripts/build_search_index.py' % INDEX_PATH)
            return 1
        if disk != text.encode('utf-8'):
            print('!! %s 与三份 meta.json 不一致，请重新生成' % INDEX_PATH)
            print('   磁盘 %d 字节 / 应为 %d 字节' % (len(disk), size))
            return 1
        print('OK   %s 与三份 meta.json 一致（%d 字节 / %d 行）'
              % (INDEX_PATH, size, len(index['rows'])))
        return 0

    write_disk(text)
    print('已生成 %s：%d 行，%d 字节（%.1f KB）'
          % (INDEX_PATH, len(index['rows']), size, size / 1024.0))
    return 0
```

- [ ] **Step 3: 先跑一次，确认能生成**

Run: `python -u scripts/build_search_index.py`
Expected: 输出 `已生成 data/search_index.json：7415 行，... 字节`

- [ ] **Step 4: 加 `--self-test`（14 条用例，含 4 条反向自检 + 1 条鉴别力）**

在 `scripts/build_search_index.py` 里 `main()` 之前插入：

```python
# --------------------------------------------------------------- 自检用例
# 规则编号（_check_rules 真正检查的规则，R1~R8）：
#   R1  索引行数 = 三刊 meta 条目数之和
#   R2  索引 cols 固定为 ["m","y","i","t","u"]
#   R3  每行都能在对应刊的 meta 里找到同一条（mag/y/i/u 四元组）
#   R4  同一刊物内 URL 无重复（跨刊允许重复：「网站公告」同时列在《求是》和《红旗文稿》）
#   R5  体积不超过 MAX_INDEX_BYTES
#   R6  行序：刊物展示顺序 qs → hqwg → djyj，且同一刊的行必须连续成块
#   R7  行序：年份降序、期号降序，期内保持 meta 原有顺序
#   R8  dump_index 输出可被 json.loads 还原，且与原对象相等
#
# 用例标签（self_test 里的一条条断言，不是一条规则）：
#   C1  正对照：结构合规的样本 → R1~R8 全部零错误
#   C2  空 meta 不炸，返回空 rows
#   C3  反向自检：同一刊物内 URL 重复 → 必须命中 R4
#   C4  反向自检：漏一行 → 必须命中 R1
#   C5  反向自检：刊别写错 → 必须命中 R6
#   C6  反向自检：顺序被打乱 → 必须命中 R7
#   C7  鉴别力：R1 必须是因为"行数少了"而失败，不是被别的规则顺带带崩

def _sample_metas():
    """构造一份结构完全合规的三刊样本（正对照用）。

    刻意包含一条**跨刊重复的 URL**（hqwg 的那篇与 qs 的那篇指向同一页面，
    与真实数据里「网站公告」同时列在两本刊目录里的情况同构），
    用来锁死「跨刊重复 → R4 零错误」这条语义。
    """
    return [
        ('qs', [
            {'t': '本期导读', 'a': '', 's': '', 'y': 2019, 'i': 1, 'u': 'http://q/1', 'h': 1},
            {'t': '新篇A', 'a': '甲', 's': '评论', 'y': 2020, 'i': 2, 'u': 'http://q/2', 'h': 1},
            {'t': '新篇B', 'a': '乙', 's': '评论', 'y': 2020, 'i': 1, 'u': 'http://q/3', 'h': 1},
        ]),
        ('hqwg', [
            {'t': '红旗篇', 'a': '丙', 's': '理论', 'y': 2021, 'i': 1, 'u': 'http://h/1', 'h': 1},
            {'t': '跨刊公告', 'a': '', 's': '', 'y': 2020, 'i': 1, 'u': 'http://q/2', 'h': 1},
        ]),
        ('djyj', [
            {'t': '党建篇', 'a': '丁', 's': '本刊特稿', 'y': 2022, 'i': 1, 'u': 'http://d/1', 'h': 0},
        ]),
    ]


def _check_rules(index, metas):
    """跑一遍规则，返回 {规则编号: 错误信息列表}。"""
    errs = {}
    def add(rule, msg):
        errs.setdefault(rule, []).append(msg)

    rows = index['rows']
    want_n = sum(len(m) for _k, m in metas)
    if len(rows) != want_n:
        add('R1', '行数 %d，应为 %d' % (len(rows), want_n))
    if index.get('cols') != ['m', 'y', 'i', 't', 'u']:
        add('R2', 'cols 为 %r' % (index.get('cols'),))

    # 建查表：key_sets 用于 R3 的 O(1) 可寻址判断，first_pos 用于 R7 的期内原序比对。
    # first_pos 只记**首次**出现的下标 —— meta 里 (y,i,u) 可能重复，
    # 取最后一个会让同一份数据得出不稳定的结论。
    by_mag = dict(metas)
    key_sets = {}
    first_pos = {}
    for mag, meta in metas:
        ks = set()
        pos = {}
        for k, a in enumerate(meta):
            ks.add((a['y'], a['i'], a['u'], a['t']))
            k3 = (a['y'], a['i'], a['u'])
            if k3 not in pos:
                pos[k3] = k
        key_sets[mag] = ks
        first_pos[mag] = pos

    for row in rows:
        if len(row) != 5:
            add('R3', '行长度 %d：%r' % (len(row), row))
            continue
        mag, y, i, t, u = row
        if (y, i, u, t) not in key_sets.get(mag, set()):
            add('R3', '索引行在 meta 中找不到对应条目：%r' % (row,))

    # R4 同一刊物内 URL 无重复
    # 注意：**跨刊**允许重复 —— 实测三刊 meta 合计 7415 行、唯一 URL 7413 个，
    # 「网站公告」这篇文章同时列在《求是》和《红旗文稿》的目录里（http/https 各一组）。
    # 那是真实数据，不是索引的错；全局去重会破坏 R1（行数必须等于 meta 条目数之和），
    # 还会丢掉《红旗文稿》的目录条目。
    counts = {}
    uniques = {}
    for row in rows:
        if len(row) != 5:
            continue
        counts[row[0]] = counts.get(row[0], 0) + 1
        uniques.setdefault(row[0], set()).add(row[4])
    for mag in sorted(counts):
        d = counts[mag] - len(uniques[mag])
        if d:
            add('R4', '%s 在索引内有 %d 条重复 URL' % (mag, d))

    size = len(dump_index(index).encode('utf-8'))
    if size > MAX_INDEX_BYTES:
        add('R5', '体积 %d 超过上限 %d' % (size, MAX_INDEX_BYTES))

    # R6 刊物顺序：展示顺序 qs → hqwg → djyj，且同一刊的行必须连续成块
    seen_mags = []
    for row in rows:
        if row[0] not in seen_mags:
            seen_mags.append(row[0])
    if seen_mags != [m for m in MAG_ORDER if m in seen_mags]:
        add('R6', '刊物顺序为 %r' % (seen_mags,))
    blocks = []
    for row in rows:
        if not blocks or blocks[-1] != row[0]:
            blocks.append(row[0])
    if blocks != seen_mags:
        add('R6', '同一刊的行未连续成块，实际分块 %r' % (blocks,))

    # R7 年降、期降、期内保持原顺序
    # 「旧→新」才算违规：a 比 b 旧即 (a.y, a.i) < (b.y, b.i)
    for mag in MAG_ORDER:
        sub = [r for r in rows if r[0] == mag]
        for a, b in zip(sub, sub[1:]):
            if (a[1], a[2]) < (b[1], b[2]):
                add('R7', '%s 段内顺序错：%r 之后是 %r' % (mag, a, b))
                break
        pos = first_pos.get(mag) or {}
        for a, b in zip(sub, sub[1:]):
            if a[1] == b[1] and a[2] == b[2]:
                pa = pos.get((a[1], a[2], a[4]))
                pb = pos.get((b[1], b[2], b[4]))
                if pa is not None and pb is not None and pa > pb:
                    add('R7', '%s 期内顺序被打乱：%r 在 %r 之后' % (mag, a, b))
                    break

    return errs


def self_test():
    metas = _sample_metas()
    index = build_index(metas)

    cases = []

    def case(rule, ok, detail):
        cases.append((rule, ok, detail))

    # ---- C1 正对照：结构完全合规的样本应当零错误 ----
    # 样本里刻意含一条跨刊重复的 URL，所以 C1 同时锁死「跨刊重复 → R4 零错误」
    errs = _check_rules(index, metas)
    case('C1', not errs.get('R1'), '正对照：无 R1 错误')
    case('C1', not errs.get('R2'), '正对照：无 R2 错误')
    case('C1', not errs.get('R3'), '正对照：无 R3 错误')
    case('C1', not errs.get('R4'), '正对照：无 R4 错误（含跨刊重复 URL）')
    case('C1', not errs.get('R5'), '正对照：无 R5 错误')
    case('C1', not errs.get('R6'), '正对照：无 R6 错误')
    case('C1', not errs.get('R7'), '正对照：无 R7 错误')
    case('C1', json.loads(dump_index(index)) == index, '正对照：dump/load 往返一致')

    # ---- C2 空 meta 不炸 ----
    case('C2', build_index([])['rows'] == [], '空 meta 返回空 rows')

    # ---- C3 反向自检：同一刊物内 URL 重复必须被 R4 抓到 ----
    bad = build_index(metas)
    bad['rows'].append(list(bad['rows'][0]))
    e = _check_rules(bad, metas)
    case('C3', 'R4' in e, '反向自检：同刊 URL 重复 → 命中 R4（实际命中 %s）' % (sorted(e.keys()),))

    # ---- C4 反向自检：注入「漏一行」必须被 R1 抓到 ----
    bad = build_index(metas)
    bad['rows'] = bad['rows'][:-1]
    e = _check_rules(bad, metas)
    case('C4', 'R1' in e, '反向自检：漏一行 → 命中 R1（实际命中 %s）' % (sorted(e.keys()),))

    # ---- C5 反向自检：刊别写错必须被 R6 抓到 ----
    bad = build_index(metas)
    if bad['rows']:
        bad['rows'][0][0] = 'hqwg' if bad['rows'][0][0] != 'hqwg' else 'djyj'
    e = _check_rules(bad, metas)
    case('C5', 'R6' in e, '反向自检：刊别写错 → 命中 R6（实际命中 %s）' % (sorted(e.keys()),))

    # ---- C6 反向自检：顺序被打乱必须被 R7 抓到 ----
    bad = build_index(metas)
    if len(bad['rows']) >= 2:
        bad['rows'][0], bad['rows'][1] = bad['rows'][1], bad['rows'][0]
    e = _check_rules(bad, metas)
    case('C6', 'R7' in e, '反向自检：顺序打乱 → 命中 R7（实际命中 %s）' % (sorted(e.keys()),))

    # ---- C7 鉴别力：R1 必须真的因为"少了一行"而失败，
    #      而不是被别的规则先报错才"通过" ----
    bad = build_index(metas)
    bad['rows'] = bad['rows'][:-1]
    e = _check_rules(bad, metas)
    case('C7', e.get('R1') and '行数' in e['R1'][0],
         '鉴别力：R1 的报错说的是行数（实际：%s）' % (e.get('R1'),))

    failed = 0
    print('=' * 64)
    print('索引生成器自检')
    print('=' * 64)
    for rule, ok, detail in cases:
        if not ok:
            failed += 1
        print('  %s %-4s %s' % ('OK  ' if ok else 'FAIL', rule, detail))
    print('')
    print('  用例 %d 条，失败 %d 条' % (len(cases), failed))
    if failed:
        print('❌ 自检未通过')
        return 1
    print('✅ 自检通过')
    return 0
```

- [ ] **Step 5: 追加脚本入口（必须在文件末尾）**

把下面这段**追加到文件最末尾**（`main()` 与 `self_test()` 都定义完之后）：

```python
if __name__ == '__main__':
    sys.exit(main())
```

> **为什么必须放最后**：入口块在导入时就会执行 `main()`，
> 而 `main()` 里会调用 `self_test()`。若入口块排在 `self_test` 定义之前，
> 运行时会抛 `NameError: name 'self_test' is not defined`。

- [ ] **Step 6: 跑自检，确认全绿**

Run: `python -u scripts/build_search_index.py --self-test`
Expected: `用例 14 条，失败 0 条` + `✅ 自检通过`

- [ ] **Step 7: 确认 `--check` 在文件不存在时以非 0 退出**

Run: `python -u scripts/build_search_index.py --check; echo "exit=$LASTEXITCODE"`
Expected: `exit=0`（Step 3 已经生成过文件）

- [ ] **Step 8: 提交**

```bash
git -C E:/cursor/djyj add scripts/build_search_index.py
git -C E:/cursor/djyj commit -m "新增跨刊标题索引生成器

从三份 meta.json 生成紧凑的全局标题索引（m/y/i/t/u 五列），
行序按刊物展示顺序 qs→hqwg→djyj、年份降序、期号降序、期内保持官网目录顺序。

--self-test 内置 14 条用例，含 4 条反向自检（同刊 URL 重复/漏一行/刊别写错/顺序打乱），
且反向自检断言到规则编号一级（R4/R1/R6/R7）。

验证范围：--self-test 全绿；已用真实三刊 meta 生成一次索引。
已实现但未独立审查。"
```

---

### Task 2: 生成索引产物 + `check_data.py` 加 S1–S4 四条断言

**Files:**
- Create: `data/search_index.json`（由脚本生成，不手写）
- Modify: `scripts/check_data.py`（新增 `check_search_index()` 与 `MAGAZINES` 之外的断言，接入 `main()`）
- Modify: `scripts/README.md`（补用法条目）
- Modify: `docs/UPDATE_FLOW.md`（补「重建索引」一步）

**Interfaces:**
- Consumes: Task 1 的 `build_search_index.py`；`data/search_index.json`。
- Produces: `scripts/check_data.py` 的 `check_search_index()` → `int`（返回错误条数，0 为通过）。规则编号 S1–S4：
  - **S1** 索引行数 = 三刊 `meta.json` 条目数之和
  - **S2** 逐行可寻址：每行 `(mag, y, i, u)` 能在对应刊 `meta.json` 里找到同一条
  - **S3** **同一刊物内** URL 无重复（跨刊允许重复，见 Step 2 的说明）
  - **S4** 索引体积 ≤ 1.5 MB

- [ ] **Step 1: 生成索引**

Run: `python -u scripts/build_search_index.py`
Expected: `已生成 data/search_index.json：7415 行，... 字节`

- [ ] **Step 2: 在 `scripts/check_data.py` 里加 S1–S4**

在 `scripts/check_data.py` 的 `def main():` **之前**插入：

```python
def check_search_index():
    """跨刊标题索引体检（规则 S1~S4）。

    索引 data/search_index.json 是派生产物，唯一权威源是三份 meta.json。
    这里强制断言二者一致，避免改了 meta 却忘了重建索引。
    """
    print('\n[search_index] 跨刊标题索引')
    path = 'data/search_index.json'
    full = os.path.join(BASE_DIR, path)
    if not os.path.exists(full):
        print(f'    !! 缺少 {path}（跑一次 python scripts/build_search_index.py 生成）')
        return 1

    size = os.path.getsize(full)
    with open(full, encoding='utf-8') as f:
        idx = json.load(f)

    rows = idx.get('rows') or []
    cols = idx.get('cols') or []
    bad = 0

    # S2 逐行可寻址：先建 (mag) -> {(y,i,u)} 的集合
    by_mag = {}
    for key, _name, meta_path, _issues in MAGAZINES:
        meta = load(meta_path) or []
        by_mag[key] = set((a['y'], a['i'], a['u']) for a in meta)

    # S1 行数
    want_rows = sum(len(load(mp) or []) for _k, _n, mp, _i in MAGAZINES)
    if len(rows) != want_rows:
        print(f"    !! S1 行数不符：索引 {len(rows)} 行，三刊 meta 合计 {want_rows} 行")
        bad += 1
    else:
        print(f'    S1 行数一致：{len(rows)} 行')

    # S2 逐行可寻址
    missing = 0
    first_bad = None
    for row in rows:
        if len(row) != 5:
            missing += 1
            if first_bad is None:
                first_bad = row
            continue
        mag, y, i, _t, u = row
        if (y, i, u) not in by_mag.get(mag, set()):
            missing += 1
            if first_bad is None:
                first_bad = row
    if missing:
        print(f'    !! S2 有 {missing} 行在 meta 中找不到对应条目，示例 {first_bad}')
        bad += 1
    else:
        print('    S2 逐行可寻址：全部命中')

    # S3 同一刊物内 URL 无重复
    # 注意：**跨刊**允许重复 —— 实测三刊 meta 合计 7415 行、唯一 URL 7413 个，
    # 差的两条是「网站声明」这篇文章同时出现在《求是》和《红旗文稿》的目录里
    # （http / https 各一组）。那是真实数据，不是索引的错；
    # 全局去重会破坏 S1（行数必须等于三刊 meta 条目数之和），也不能做。
    counts = {}
    uniques = {}
    for r in rows:
        if len(r) != 5:
            continue
        counts[r[0]] = counts.get(r[0], 0) + 1
        uniques.setdefault(r[0], set()).add(r[4])
    dup_total = 0
    for mag in sorted(counts):
        d = counts[mag] - len(uniques[mag])
        if d:
            print(f'    !! S3 {mag} 在索引内有 {d} 条重复 URL')
        dup_total += d
    if dup_total:
        bad += 1
    else:
        print('    S3 同一刊物内 URL 无重复')

    # S4 体积
    limit = 1572864
    if size > limit:
        print(f'    !! S4 体积 {size} 字节，超过上限 {limit} 字节')
        bad += 1
    else:
        print(f'    S4 体积 {size} 字节（上限 {limit}）')

    if cols != ['m', 'y', 'i', 't', 'u']:
        print(f"    !! cols 为 {cols}，应为 ['m', 'y', 'i', 't', 'u']")
        bad += 1

    print('    索引问题数: %d' % bad)
    return bad
```

- [ ] **Step 3: 接入 `main()`**

在 `scripts/check_data.py` 的 `main()` 里，把这一行：

```python
    order_bad = check_catalog_order()
```

改成：

```python
    order_bad = check_catalog_order()
    index_bad = check_search_index()
```

- [ ] **Step 4: 跑体检，确认 S1–S4 全绿**

Run: `python -u scripts/check_data.py`
Expected: 输出 `[search_index] 跨刊标题索引` 段，`S1 行数一致：7415 行`、`S2 逐行可寻址：全部命中`、`S3 同一刊物内 URL 无重复`、`S4 体积 1000280 字节（上限 1572864）`、`索引问题数: 0`

- [ ] **Step 5: 反向验证 S1 真的会失败（不能只看它"通过"）**

临时改坏一行再跑，确认被 S2 抓到，然后恢复：

```bash
python -u -c "import json,io,sys; sys.stdout.reconfigure(encoding='utf-8',errors='replace'); p='E:/cursor/djyj/data/search_index.json'; d=json.load(open(p,encoding='utf-8')); d['rows'][5][4]='http://example.invalid/x'; open(p,'w',encoding='utf-8').write(json.dumps(d,ensure_ascii=False,separators=(',',':')))"
python -u E:/cursor/djyj/scripts/check_data.py
python -u E:/cursor/djyj/scripts/build_search_index.py
python -u E:/cursor/djyj/scripts/check_data.py
```
Expected: 第一遍 `!! S2 有 1 行在 meta 中找不到对应条目`；第二遍（重建后）恢复 `S2 逐行可寻址：全部命中`

- [ ] **Step 6: 补文档**

在 `scripts/README.md` 末尾追加：

```markdown
---

## 跨刊标题索引

站内检索原先锁死在当前这一本刊。现在有一份跨三刊的紧凑标题索引，
让前端一次请求就能跨刊按标题匹配。

```bash
# 生成 data/search_index.json
python scripts\build_search_index.py

# 与三份 meta.json 逐字节比对，不一致退出码 1（提交前跑）
python scripts\build_search_index.py --check

# 内置自检（13 条，含 3 条反向自检）
python scripts\build_search_index.py --self-test

# 打印各刊每期正文分片的实测均值字节，供 app.js 的 BODY_AVG_BYTES 常量对账
python scripts\build_search_index.py --print-avg
```

**索引是派生产物**，三份 `meta.json` 仍是唯一权威源。
`scripts/check_data.py` 的 S1~S4 会强制断言二者一致。

> **更新数据后必须做两步**：
> 1. 升 `scripts/build_search_index.py` 里的 `INDEX_VERSION`（索引文件里的 `v` 字段）；
> 2. 重新运行 `python scripts\build_search_index.py`。
> 忘了升版本号的话，`--check` 会因为字节不一致而报错，索引也会被误认为"没变"。
```

在 `docs/UPDATE_FLOW.md` 的数据更新流程步骤列表末尾追加一条：

```markdown
9. **重建跨刊标题索引**：`python scripts\build_search_index.py`
   （先升 `scripts/build_search_index.py` 里的 `INDEX_VERSION`，再运行；
   然后 `python scripts\build_search_index.py --check` 确认与 meta 一致）
```

- [ ] **Step 7: 提交**

```bash
git -C E:/cursor/djyj add data/search_index.json scripts/check_data.py scripts/README.md docs/UPDATE_FLOW.md
git -C E:/cursor/djyj commit -m "生成跨刊标题索引并加入数据一致性断言

data/search_index.json：7415 行，只含刊物/年份/期号/标题/URL 五列，
体积远低于 1.5 MB 上限。

check_data.py 新增 S1~S4：行数一致、逐行可寻址、URL 无重复、体积上限。
索引是派生产物，meta.json 仍是唯一权威源。

验证范围：check_data.py 全绿；已用改坏一行再重建的方式验证 S2 确实会失败。
已实现但未独立审查。"
```

---

### Task 3: 跨刊检索内核体检脚本 `scripts/check_search_upgrade.js`（与 Task 4 合并为一次提交）

**Files:**
- Create: `scripts/check_search_upgrade.js`
- Read: `assets/js/app.js`（本任务**只读**，实现放到 Task 4）

> **本任务不单独提交。** 脚本写完时 `app.js` 里还没有它要验证的函数，
> 跑起来必然是红的（Step 2 就是要看到它红）。单独提交一个跑不过的体检脚本，
> 会让仓库里长期留着一个失败的脚本，也会让「每次提交都是绿的」这条约定失效。
> **脚本与 Task 4 的实现一起提交**（见 Task 4 的 Step 8）。
> TDD 顺序不变：先写脚本 → 看到它失败 → 实现 → 再看到它通过。

**Interfaces:**
- Consumes: `assets/js/app.js` 里的纯函数 `searchAllTitles(index, query)`、`groupCrossMagResults(results)`、`pickBodyWindow(issues, yearSpan)`、`formatBytes(n)`、`articleMatches(a, query, scope, ms)`，以及常量 `MAGAZINES`。
- Produces: 命令行 `node scripts/check_search_upgrade.js`，非 0 退出码表示不达标。规则编号：
  - **R1** 空查询返回空数组
  - **R2** 命中项字段齐全（`m/y/i/t/u`）
  - **R3** 组间顺序 = 刊物展示顺序 `qs → hqwg → djyj`
  - **R4** 组内顺序 = 年份降序、期号降序
  - **R5** 组计数 = 该组实际条数
  - **R6** 跨刊命中 ⊆ 单刊「仅标题」命中（子集性质）
  - **R7** `pickBodyWindow` 取最新年份起 3 年
  - **R8** `pickBodyWindow` 在数据不足 3 年时取全部
  - **R9** `formatBytes` 输出格式正确
  - **R10** 反向自检：刊别写错 → 命中 R3
  - **R11** 反向自检：组内顺序打乱 → 命中 R4
  - **R12** 反向自检：跨刊命中多出单刊没有的条目 → 命中 R6

- [ ] **Step 1: 写体检脚本**

创建 `scripts/check_search_upgrade.js`：

```javascript
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
```

- [ ] **Step 2: 跑一次，确认它**因为函数还没实现**而失败**

Run: `node scripts/check_search_upgrade.js`
Expected: `❌ 在 assets/js/app.js 里找不到函数：searchAllTitles` + `（说明 assets/js/app.js 里还没有这些函数，先实现再跑本脚本）`，退出码非 0。

> 这一步是**故意**的失败：脚本依赖 Task 4 的实现，现在就该红。

- [ ] **Step 3: 不提交，交给 Task 4 一起提交**

脚本此刻是红的（Step 2 就是要看到它红）。**不要在这里提交** —— 单独提交一个跑不过的
体检脚本，会让仓库里长期留着一个失败的脚本。提交动作放在 Task 4 的 Step 8，
那时脚本与 `app.js` 的实现一起进库，两者的 commit 是绿的。

---

### Task 4: `assets/js/app.js` 跨刊检索内核（与 Task 3 合并提交）

**Files:**
- Modify: `assets/js/app.js`（`state` 对象约 42–64 行；`getSearchScope()` 附近 371–386 行）

**Interfaces:**
- Consumes: `data/search_index.json`（经 `dataUrl()` 取，带版本参数）。
- Produces:
  - `state.searchIndex` — `null` 或 `{v, cols, rows}`
  - `state.searchIndexStatus` — `'idle' | 'loading' | 'ready' | 'error'`
  - `loadSearchIndex()` → `Promise<boolean>`：成功返回 `true`；失败返回 `false` 并把状态置 `'error'`
  - `searchAllTitles(index, query)` → `Array<{m,y,i,t,u}>`：对 `rows` 的第 3 列做小写 `includes` 匹配，**保持索引原有行序**
  - `groupCrossMagResults(results)` → `Array<{mag, name, count, items}>`：按刊物切段，段名取 `MAGAZINES[mag].name`
  - `pickBodyWindow(issues, yearSpan)` → `Array<{y,i,key}>`：从**已按 (y,i) 降序**的期次表里取最新年份起 `yearSpan` 年
  - `formatBytes(n)` → `string`
  - `getMagScope()` → `'current' | 'all'`
  - `syncMagScopeChecked()` → `undefined`：同步 `.checked` 类（Chrome 69 没有 `:has()`）
  - `MAGAZINE_ORDER` 常量 = `['qs', 'hqwg', 'djyj']`（展示顺序）

- [ ] **Step 1: 在 `state` 里加 2 个字段（`searchIndex` / `searchIndexStatus`）**

把 `assets/js/app.js` 的 `state` 对象里这一段：

```javascript
    isSearching: false,
    searchResults: [],
    searchToken: 0,         // 递增令牌：查询词变化时让旧的正文搜索立即作废
    lastQuery: '',         // 最近一次已提交的搜索词
```

改成：

```javascript
    isSearching: false,
    searchResults: [],
    searchToken: 0,         // 递增令牌：查询词变化时让旧的正文搜索立即作废
    lastQuery: '',         // 最近一次已提交的搜索词
    searchIndex: null,     // 跨刊标题索引（懒加载，data/search_index.json）
    searchIndexStatus: 'idle',   // idle / loading / ready / error
```

- [ ] **Step 2: 加刊物展示顺序常量**

在 `assets/js/app.js` 的 `MAGAZINES` 常量之后（`const CN = ...` 之前）插入：

```javascript
/* 刊物展示顺序：跨刊检索结果按这个顺序分组。
   与 scripts/build_search_index.py 的 MAG_ORDER、scripts/check_data.py 的 MAGAZINES 一致。 */
const MAGAZINE_ORDER = ['qs', 'hqwg', 'djyj'];
```

- [ ] **Step 3: 加纯函数（放在「===== 搜索 =====」段落里，`getSearchScope()` 之前）**

在 `assets/js/app.js` 的 `/* ===== 搜索 ===== */` 注释行之后、`function getSearchScope()` 之前插入：

```javascript
/* 载入跨刊标题索引。
   失败时不抛错、不影响本刊搜索：状态置 'error'，调用方负责提示与降级。 */
async function loadSearchIndex() {
    if (state.searchIndexStatus === 'ready' && state.searchIndex) return true;
    if (state.searchIndexStatus === 'loading') return false;
    state.searchIndexStatus = 'loading';
    try {
        const resp = await fetch(dataUrl('data/search_index.json'));
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const idx = await resp.json();
        if (!idx || !Array.isArray(idx.rows) || !Array.isArray(idx.cols)) {
            throw new Error('索引结构不正确');
        }
        if (idx.cols.join(',') !== 'm,y,i,t,u') {
            throw new Error('索引列序不正确：' + idx.cols.join(','));
        }
        state.searchIndex = idx;
        state.searchIndexStatus = 'ready';
        return true;
    } catch (e) {
        console.warn('跨刊标题索引加载失败：', e);
        state.searchIndex = null;
        state.searchIndexStatus = 'error';
        return false;
    }
}

/* 跨刊标题检索：只匹配标题（不含作者与板块）。
   返回顺序即索引行序：刊物展示顺序 → 年降 → 期降 → 期内官网目录顺序。

   **不要按 URL 去重**：真实数据里「网站公告」这篇文章同时列在《求是》和
   《红旗文稿》的目录里（http/https 各一组），按 URL 去重会把《红旗文稿》
   那两条目录条目吞掉。每行都是一条独立的目录条目，条目身份是整行。 */
function searchAllTitles(index, query) {
    const out = [];
    if (!index || !index.rows) return out;
    const q = String(query || '').trim().toLowerCase();
    if (!q) return out;
    for (const row of index.rows) {
        if (!row || row.length < 4) continue;
        if (String(row[3]).toLowerCase().indexOf(q) >= 0) {
            out.push({ m: row[0], y: row[1], i: row[2], t: row[3], u: row[4] });
        }
    }
    return out;
}

/* 把跨刊命中切成组：{mag, name, count, items} */
function groupCrossMagResults(results) {
    const groups = [];
    let cur = null;
    for (const r of results) {
        if (!cur || cur.mag !== r.m) {
            const conf = MAGAZINES[r.m];
            cur = { mag: r.m, name: conf ? conf.name : r.m, count: 0, items: [] };
            groups.push(cur);
        }
        cur.count++;
        cur.items.push(r);
    }
    return groups;
}

/* 正文搜索窗口：从已按 (y,i) 降序的期次表里取最新年份起的 yearSpan 年。
   基准是期次表里最大的年份（不读浏览器时间，避免用户机器日期算错）。 */
function pickBodyWindow(issues, yearSpan) {
    if (!issues || !issues.length) return [];
    const span = yearSpan || 1;
    const maxYear = issues[0].y;
    const minYear = maxYear - span + 1;
    return issues.filter(it => it.y >= minYear);
}

/* 字节数转可读文本 */
function formatBytes(n) {
    const num = Number(n) || 0;
    if (num < 1024) return num + ' B';
    if (num < 1024 * 1024) return (num / 1024).toFixed(1) + ' KB';
    return (num / 1024 / 1024).toFixed(1) + ' MB';
}

/* 检索范围：本刊 / 三刊 */
function getMagScope() {
    const checked = document.querySelector('input[name="magScope"]:checked');
    return checked ? checked.value : 'current';
}

/* 同步「本刊 / 三刊」开关的选中态。
   Chrome 69 不支持 CSS :has()，用 .checked 类兜底（与 syncScopeChecked 同一套路）。 */
function syncMagScopeChecked() {
    document.querySelectorAll('.mag-scope-option').forEach(opt => {
        const input = opt.querySelector('input[name="magScope"]');
        if (input && input.checked) opt.classList.add('checked');
        else opt.classList.remove('checked');
    });
}
```

- [ ] **Step 4: 跑体检，确认转绿**

Run: `node scripts/check_search_upgrade.js`
Expected: `用例 12 条，失败 0 条` + `✅ 体检通过`

- [ ] **Step 5: 用 acorn 确认语法与 ES2019 兼容**

Run: `npx --yes acorn@8 --ecma2019 assets/js/app.js`
Expected: 无输出、退出码 0

- [ ] **Step 6: 跑兼容性体检**

Run: `python -u scripts/check_compat.py`
Expected: `✅ 未发现 Chrome 69 不兼容的用法`

- [ ] **Step 7: 跑 JS 注释体检**

Run: `python -u scripts/check_js_comments.py`
Expected: 全绿（`scripts/check_js_comments.py` 会同时做 SW 求值冒烟）

- [ ] **Step 8: 提交（与 Task 3 的体检脚本一起）**

```bash
git -C E:/cursor/djyj add assets/js/app.js scripts/check_search_upgrade.js
git -C E:/cursor/djyj commit -m "app.js 新增跨刊检索内核（纯函数 + 索引懒加载）并附体检脚本

新增 loadSearchIndex / searchAllTitles / groupCrossMagResults /
pickBodyWindow / formatBytes / getMagScope / syncMagScopeChecked，
以及 state.searchIndex 与 state.searchIndexStatus。

跨刊只匹配标题（不含作者与板块），返回顺序即索引行序。

同时新增 scripts/check_search_upgrade.js：把上面这些函数从 app.js 里
原样抽出来跑，断言分组顺序、子集性质、正文窗口选取，
并带 3 条反向自检（R10/R11/R12）。脚本与实现一起提交，仓库里不留红脚本。

验证范围：node scripts/check_search_upgrade.js 12 条用例全绿；
acorn --ecma2019 通过；check_compat.py 与 check_js_comments.py 零失败。
已实现但未独立审查。"
```

---

### Task 5: 范围开关 + 跨刊结果分组渲染

**Files:**
- Modify: `index.html`（搜索栏 `filters` 块，222–237 行）
- Modify: `assets/css/style.css`（新增样式 + 末尾 `@supports not (aspect-ratio: 3 / 4)` 兜底块）
- Modify: `assets/js/app.js`（`performSearch` 加 `magScope` 维度；新增 `renderCrossMagResults`）

**Interfaces:**
- Consumes: Task 4 的 `loadSearchIndex` / `searchAllTitles` / `groupCrossMagResults` / `getMagScope` / `syncMagScopeChecked`。
- Produces:
  - `crossMagCardsHtml(groups, query, showFav)` → `string`：跨刊结果卡片 HTML。杂志内结果区传 `showFav=true`（带收藏按钮），主页浮层传 `false`。**Task 6 的浮层必须复用这个函数，不要另写一份模板。**
  - `renderCrossMagResults()` → `undefined`：把 `state.searchResults`（跨刊命中）按组渲染进 `#searchResults`，并在 `#resultInfo` 写命中数与范围说明。
  - DOM：`input[name="magScope"]` 两个单选（`value="current"` 默认选中、`value="all"`）；`.filters` 上加 `.filters--all` 表示三刊模式。

- [ ] **Step 1: `index.html` 加范围开关**

把 `index.html` 的这一段：

```html
    <div class="filters" id="filters">
        <div class="scope-group">
            <label class="scope-option"><input type="radio" name="searchScope" value="all" checked> 标题+正文</label>
            <label class="scope-option"><input type="radio" name="searchScope" value="title"> 仅标题</label>
            <label class="scope-option"><input type="radio" name="searchScope" value="body"> 仅正文</label>
        </div>
        <label class="filter-check"><input type="checkbox" id="bodyOnly"> 仅有全文</label>
    </div>
```

改成：

```html
    <div class="filters" id="filters">
        <div class="scope-group mag-scope-group">
            <label class="scope-option mag-scope-option"><input type="radio" name="magScope" value="current" checked> 本刊</label>
            <label class="scope-option mag-scope-option"><input type="radio" name="magScope" value="all"> 三刊</label>
        </div>
        <div class="scope-group scope-group--content" id="scopeContentGroup">
            <label class="scope-option"><input type="radio" name="searchScope" value="all" checked> 标题+正文</label>
            <label class="scope-option"><input type="radio" name="searchScope" value="title"> 仅标题</label>
            <label class="scope-option"><input type="radio" name="searchScope" value="body"> 仅正文</label>
        </div>
        <label class="filter-check filter-check--content" id="bodyOnlyWrap"><input type="checkbox" id="bodyOnly"> 仅有全文</label>
    </div>
```

- [ ] **Step 2: `assets/css/style.css` 加样式**

在 `assets/css/style.css` 的 `/* ===== Search Bar ===== */` 段落末尾（`.filter-check` 规则之后）追加：

```css
/* ===== 检索范围：本刊 / 三刊 ===== */
.mag-scope-group {
    flex-shrink: 0;
}
/* 三刊模式下隐藏与正文相关的控件（跨刊只搜标题） */
.filters--all .scope-group--content,
.filters--all .filter-check--content {
    display: none;
}

/* ===== 跨刊结果的分组标题 ===== */
.result-group {
    display: flex;
    flex-direction: column;
    gap: 10px;
}
.result-group-head {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 12px 2px 4px;
    margin-bottom: 2px;
    border-bottom: 1px solid var(--border);
}
.result-group-name {
    font-size: 14px;
    font-weight: 600;
    color: var(--primary);
}
.result-group-count {
    font-size: 12px;
    color: var(--text-3);
}
.result-group-cont {
    font-size: 12px;
    color: var(--text-3);
}
```

- [ ] **Step 3: `assets/css/style.css` 补 flex gap 兜底**

在 `assets/css/style.css` 末尾的 `@supports not (aspect-ratio: 3 / 4) { ... }` 兜底块里，
「---- 纵向排列：后续元素补上边距 ----」那一段之后插入：

```css
    /* ---- 跨刊结果分组 ---- */
    .result-group { gap: 0; }
    .result-group > * + * { margin-top: 10px; }
    .result-group-head { gap: 0; }
    .result-group-head > * + * { margin-left: 8px; }
```

- [ ] **Step 4: `assets/js/app.js` 加跨刊渲染函数**

在 `assets/js/app.js` 的 `function renderSearchPage() {` **之前**插入：

```javascript
/* 跨刊结果卡片 HTML —— 杂志内结果区与主页搜索浮层**共用这一份**，
   免得两处模板各改各的、悄悄漂移。
   showFav=true 时带收藏按钮（杂志内结果区需要），主页浮层不带。 */
function crossMagCardsHtml(groups, query, showFav) {
    let html = '';
    groups.forEach(function (g) {
        html += '<div class="result-group">';
        html += '<div class="result-group-head"><span class="result-group-name">' + escHtml(g.name) + '</span>'
            + '<span class="result-group-count">' + g.count + ' 篇</span></div>';
        g.items.forEach(function (a) {
            const ci = a.i <= 24 ? CN[a.i - 1] : a.i;
            const encUrl = encodeURIComponent(a.u);
            const titleHtml = query ? highlightText(a.t, query) : escHtml(a.t);
            let favBtn = '';
            if (showFav) {
                const isFav = isFavorite(a.u);
                favBtn = '<button class="rc-fav-btn ' + (isFav ? 'active' : '')
                    + '" onclick="event.stopPropagation(); toggleFavFromCard(this, \'' + encUrl + '\')">'
                    + svgStar(isFav) + '</button>';
            }
            html += '<div class="result-card" onclick="showArticle(\'' + encUrl + '\')">'
                + favBtn
                + '<div class="rc-title">' + titleHtml + '</div>'
                + '<div class="rc-meta"><span class="rc-tag">' + a.y + '年第' + ci + '期</span></div>'
                + '</div>';
        });
        html += '</div>';
    });
    return html;
}

/* 跨刊检索结果：按刊物分组平铺，组内沿用索引行序（新 → 旧）。
   沿用既有 .results-list / .result-card / .rc-* 样式，不引入新的视觉语言。 */
function renderCrossMagResults() {
    const container = document.getElementById('searchResults');
    const pagination = document.getElementById('pagination');
    const infoEl = document.getElementById('resultInfo');
    const results = state.searchResults;
    const query = document.getElementById('searchInput').value.trim().toLowerCase();

    if (!results.length) {
        container.innerHTML = '<div class="loading"><div>三刊标题中没有匹配的文章</div></div>';
        pagination.innerHTML = '';
        infoEl.textContent = query ? '共 0 篇（关键词："' + query + '" ｜ 范围：三刊标题）' : '';
        return;
    }

    const groups = groupCrossMagResults(results);
    container.innerHTML = crossMagCardsHtml(groups, query, true);

    const total = results.length;
    infoEl.textContent = '共 ' + total + ' 篇（关键词："' + query + '" ｜ 范围：三刊标题 · 只匹配标题）';
    pagination.innerHTML = '<span class="page-info">共 ' + total + ' 条</span>';
}
```

- [ ] **Step 5: `assets/js/app.js` 改 `performSearch` 加 `magScope` 维度**

把 `assets/js/app.js` 的 `performSearch()` 里这一段：

```javascript
    const scope = getSearchScope();
    const bo = document.getElementById('bodyOnly').checked;

    // 标题搜索：立即执行
    let results;
    if (scope === 'title') {
        results = collectMatches(ms, query, scope, bo);
    } else {
```

改成：

```javascript
    const scope = getSearchScope();
    const bo = document.getElementById('bodyOnly').checked;
    const magScope = getMagScope();

    // 三刊模式：只做标题检索，走全局索引
    if (magScope === 'all') {
        const infoEl = document.getElementById('resultInfo');
        const bsBox = document.getElementById('bodySearchActions');
        if (bsBox) { bsBox.innerHTML = ''; bsBox.hidden = true; }
        if (state.searchIndexStatus === 'error') {
            infoEl.textContent = '索引不可用，仅可搜本刊';
            document.getElementById('searchResults').innerHTML =
                '<div class="loading"><div>跨刊索引不可用，请切回「本刊」检索</div></div>';
            document.getElementById('pagination').innerHTML = '';
            return;
        }
        infoEl.textContent = '正在加载跨刊标题索引...';
        document.getElementById('searchResults').innerHTML =
            '<div class="loading"><div class="spinner"></div><div>加载跨刊标题索引中...</div></div>';
        const tok = state.searchToken;
        loadSearchIndex().then(function (ok) {
            // 等待索引期间用户可能又改了关键词 / 换了范围，别把过期结果写回界面
            if (state.searchToken !== tok) return;
            if (!ok) {
                infoEl.textContent = '索引不可用，仅可搜本刊';
                document.getElementById('searchResults').innerHTML =
                    '<div class="loading"><div>跨刊索引不可用，请切回「本刊」检索</div></div>';
                document.getElementById('pagination').innerHTML = '';
                return;
            }
            state.searchResults = searchAllTitles(state.searchIndex, query);
            state.currentPage = 1;
            renderCrossMagResults();
        });
        return;
    }

    // 标题搜索：立即执行
    let results;
    if (scope === 'title') {
        results = collectMatches(ms, query, scope, bo);
    } else {
```

- [ ] **Step 6: `assets/js/app.js` 绑定范围开关事件**

在 `assets/js/app.js` 的 `init()` 里，把这一段：

```javascript
    document.querySelectorAll('input[name="searchScope"]').forEach(r => {
        r.addEventListener('change', () => {
            syncScopeChecked();
            if (searchInput.value.trim()) performSearch();
        });
    });
    // Chrome 69 不支持 :has()，用 .checked 类同步搜索范围选中态
    syncScopeChecked();
```

改成：

```javascript
    document.querySelectorAll('input[name="searchScope"]').forEach(r => {
        r.addEventListener('change', () => {
            syncScopeChecked();
            if (searchInput.value.trim()) performSearch();
        });
    });
    // Chrome 69 不支持 :has()，用 .checked 类同步搜索范围选中态
    syncScopeChecked();

    // 检索范围：本刊 / 三刊
    document.querySelectorAll('input[name="magScope"]').forEach(r => {
        r.addEventListener('change', () => {
            syncMagScopeChecked();
            const filters = document.getElementById('filters');
            if (filters) filters.classList.toggle('filters--all', getMagScope() === 'all');
            if (searchInput.value.trim()) performSearch();
        });
    });
    syncMagScopeChecked();
```

- [ ] **Step 7: 跑全部体检**

```bash
node scripts/check_search_upgrade.js
npx --yes acorn@8 --ecma2019 assets/js/app.js
python -u scripts/check_compat.py
python -u scripts/check_js_comments.py
python -u scripts/check_data.py
```
Expected: 全部零失败

- [ ] **Step 8: 提交**

```bash
git -C E:/cursor/djyj add index.html assets/css/style.css assets/js/app.js
git -C E:/cursor/djyj commit -m "杂志内新增「本刊 / 三刊」范围开关与跨刊分组结果

三刊模式只匹配标题，结果按刊物分组平铺，组内沿用索引行序（新→旧）。
沿用既有 .results-list / .result-card / .rc-* 样式，未引入新的视觉语言。
单刊路径（magScope=current）逐行保持不变。

验证范围：node scripts/check_search_upgrade.js 12 条全绿；acorn --ecma2019 通过；
check_compat.py / check_js_comments.py / check_data.py 零失败。
界面部分待浏览器目检（Task 7）。
已实现但未独立审查。"
```

---

### Task 6: 主页全屏搜索浮层

**Files:**
- Modify: `index.html`（首页头 108–114 行；`</body>` 前加浮层）
- Modify: `assets/css/style.css`
- Modify: `assets/js/app.js`

**Interfaces:**
- Consumes: Task 4 的 `loadSearchIndex` / `searchAllTitles` / `groupCrossMagResults`；Task 5 的 `crossMagCardsHtml(groups, query, showFav)`。
- Produces:
  - `openGlobalSearch()` → `undefined`：显示 `#globalSearch` 浮层、聚焦输入框
  - `closeGlobalSearch()` → `undefined`：隐藏浮层
  - `runGlobalSearch()` → `undefined`：按当前输入做跨刊标题检索并渲染（复用 `crossMagCardsHtml`，**不要另写一份卡片模板**）
  - DOM：`#globalSearch` / `#globalSearchInput` / `#globalSearchResults` / `#globalSearchCount` / `#homeSearchBtn`

- [ ] **Step 1: `index.html` 首页头加放大镜按钮**

把 `index.html` 的这一行：

```html
            <button class="home-about-btn" onclick="showAboutPage()" title="关于本站"><svg class="icon"><use href="#i-info"/></svg></button>
```

改成：

```html
            <button class="home-search-btn" onclick="openGlobalSearch()" title="搜索三刊标题"><svg class="icon"><use href="#i-search"/></svg></button>
            <button class="home-about-btn" onclick="showAboutPage()" title="关于本站"><svg class="icon"><use href="#i-info"/></svg></button>
```

- [ ] **Step 2: `index.html` 加浮层 DOM**

在 `index.html` 的 `</body>` 之前（`</body>` 上方、`</html>` 之前）插入：

```html
<!-- ===== 主页：三刊标题搜索浮层 ===== -->
<div id="globalSearch" class="global-search" hidden>
    <div class="gs-panel">
        <div class="gs-head">
            <div class="search-box gs-box">
                <svg class="icon search-icon"><use href="#i-search"/></svg>
                <input type="text" id="globalSearchInput" placeholder="在三刊标题中搜索..." autocomplete="off">
                <button class="gs-close" onclick="closeGlobalSearch()" title="关闭"><svg class="icon"><use href="#i-close"/></svg></button>
            </div>
            <p class="gs-hint">只搜索三刊文章标题（不含作者与板块） · 按 Esc 关闭</p>
        </div>
        <div class="gs-count" id="globalSearchCount"></div>
        <div id="globalSearchResults" class="results-list"></div>
    </div>
</div>
```

- [ ] **Step 3: `assets/css/style.css` 加浮层样式**

在 `assets/css/style.css` 的 `/* ===== 跨刊结果的分组标题 ===== */` 段之后追加：

```css
/* ===== 主页：三刊搜索浮层 ===== */
.home-search-btn {
    position: absolute;
    top: 4px;
    right: 42px;
    background: rgba(255,255,255,0.6);
    border: 1px solid var(--border);
    color: var(--text-2);
    width: 34px;
    height: 34px;
    border-radius: 50%;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s var(--ease);
    -webkit-backdrop-filter: blur(8px);
    backdrop-filter: blur(8px);
}
.home-search-btn .icon { width: 17px; height: 17px; }
.home-search-btn:hover {
    background: var(--card);
    border-color: var(--primary-light);
    color: var(--primary);
}
.global-search {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: var(--bg);
    overflow-y: auto;
    z-index: 300;
    -webkit-overflow-scrolling: touch;
}
.global-search[hidden] { display: none; }
.gs-panel {
    max-width: 720px;
    margin: 0 auto;
    padding: calc(16px + env(safe-area-inset-top, 0px)) 16px 40px;
}
.gs-head {
    position: sticky;
    top: 0;
    background: var(--bg);
    padding-bottom: 10px;
    z-index: 2;
}
.gs-box {
    background: var(--card);
    border: 1px solid var(--border-2);
    border-radius: var(--radius);
    padding: 4px 6px 4px 2px;
}
.gs-box #globalSearchInput {
    border: none;
    background: transparent;
    padding-left: 38px;
}
.gs-box #globalSearchInput:focus {
    background: transparent;
}
.gs-close {
    background: none;
    border: none;
    color: var(--text-3);
    cursor: pointer;
    width: 30px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}
.gs-close .icon { width: 16px; height: 16px; }
.gs-hint {
    font-size: 12px;
    color: var(--text-3);
    margin: 8px 2px 0;
}
.gs-count {
    font-size: 13px;
    color: var(--text-2);
    margin: 12px 2px 8px;
}
.gs-count:empty { display: none; }
```

- [ ] **Step 4: `assets/css/style.css` 补兜底与桌面尺寸**

在 `@supports not (aspect-ratio: 3 / 4)` 兜底块的「---- 跨刊结果分组 ----」那段之后插入：

```css
    .gs-box { gap: 0; }
    .gs-box > * + * { margin-left: 8px; }
```

在 `assets/css/style.css` 的桌面断点（`@media (min-width: 768px)` 段，`.home-about-btn` 规则附近）追加：

```css
    .home-search-btn { width: 38px; height: 38px; top: 8px; right: 50px; }
    .home-search-btn .icon { width: 19px; height: 19px; }
```

- [ ] **Step 5: `assets/js/app.js` 加浮层逻辑**

在 `assets/js/app.js` 的 `function renderCrossMagResults() {` 之后插入：

```javascript
/* 主页浮层：全屏三刊标题搜索 */
function openGlobalSearch() {
    const box = document.getElementById('globalSearch');
    if (!box) return;
    box.hidden = false;
    document.body.classList.add('global-search-active');
    const input = document.getElementById('globalSearchInput');
    if (input) {
        input.focus();
        input.select();
    }
    runGlobalSearch();
}

function closeGlobalSearch() {
    const box = document.getElementById('globalSearch');
    if (!box) return;
    box.hidden = true;
    document.body.classList.remove('global-search-active');
}

async function runGlobalSearch() {
    const input = document.getElementById('globalSearchInput');
    const list = document.getElementById('globalSearchResults');
    const count = document.getElementById('globalSearchCount');
    if (!input || !list) return;
    const query = input.value.trim();
    if (!query) {
        list.innerHTML = '';
        count.textContent = '';
        return;
    }
    count.textContent = '正在加载跨刊标题索引...';
    const ok = await loadSearchIndex();
    if (!ok) {
        count.textContent = '索引不可用，请稍后再试或回到杂志内搜索';
        list.innerHTML = '';
        return;
    }
    const results = searchAllTitles(state.searchIndex, query);
    state.globalSearchResults = results;
    if (!results.length) {
        count.textContent = '共 0 篇（关键词："' + query + '" ｜ 只匹配标题）';
        list.innerHTML = '<div class="loading"><div>三刊标题中没有匹配的文章</div></div>';
        return;
    }
    const groups = groupCrossMagResults(results);
    list.innerHTML = crossMagCardsHtml(groups, query, false);
    count.textContent = '共 ' + results.length + ' 篇（关键词："' + query + '" ｜ 只匹配标题）';
}
```

- [ ] **Step 6: `assets/js/app.js` 绑定浮层事件**

在 `assets/js/app.js` 的 `init()` 里，把这一行：

```javascript
    // "继续阅读"按钮
```

改成：

```javascript
    // 主页三刊搜索浮层
    const gsInput = document.getElementById('globalSearchInput');
    if (gsInput) {
        let gsTimer = null;
        gsInput.addEventListener('input', function () {
            if (gsTimer) clearTimeout(gsTimer);
            gsTimer = setTimeout(runGlobalSearch, 150);
        });
        gsInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                if (gsTimer) clearTimeout(gsTimer);
                runGlobalSearch();
            } else if (e.key === 'Escape') {
                closeGlobalSearch();
            }
        });
    }

    // "继续阅读"按钮
```

- [ ] **Step 7: 跑全部体检**

```bash
node scripts/check_search_upgrade.js
npx --yes acorn@8 --ecma2019 assets/js/app.js
python -u scripts/check_compat.py
python -u scripts/check_js_comments.py
```
Expected: 全部零失败

- [ ] **Step 8: 提交**

```bash
git -C E:/cursor/djyj add index.html assets/css/style.css assets/js/app.js
git -C E:/cursor/djyj commit -m "主页新增全屏三刊标题搜索浮层

首页标题栏「关于本站」旁加放大镜按钮，打开全屏搜索浮层，
默认三刊 + 只匹配标题。浮层复用既有 .search-box / .results-list / .result-card 类，
不引入新的视觉语言；三刊封面卡片的版面保持不动。

验证范围：node scripts/check_search_upgrade.js 12 条全绿；acorn --ecma2019 通过；
check_compat.py / check_js_comments.py 零失败。
界面部分待浏览器目检（Task 7）。
已实现但未独立审查。"
```

---

### Task 7: SW 缓存索引 + 缓存破坏五件套 + 浏览器目检（批次一收尾）

**Files:**
- Modify: `sw.js`（`DATA_ASSETS` 数组 71–76 行；两处兜底版本值 42、44 行）
- Modify: `index.html`（四处 `?v=`）
- Modify: `assets/js/app.js`（`DATA_VERSION`）

**Interfaces:**
- Consumes: Task 2 的 `data/search_index.json`。
- Produces: 版本号 `20261101a`；`sw.js` 的 `DATA_ASSETS` 含 `./data/search_index.json?v=20261101a`。

- [ ] **Step 1: `sw.js` 把索引加进预缓存清单**

把 `sw.js` 的这一段：

```javascript
var DATA_ASSETS = [
    './data/article_index.json?v=' + VERSION,
    './data/meta.json?v=' + VERSION,
    './data/qs/meta.json?v=' + VERSION,
    './data/hqwg/meta.json?v=' + VERSION
];
```

改成：

```javascript
var DATA_ASSETS = [
    './data/article_index.json?v=' + VERSION,
    './data/meta.json?v=' + VERSION,
    './data/qs/meta.json?v=' + VERSION,
    './data/hqwg/meta.json?v=' + VERSION,
    './data/search_index.json?v=' + VERSION
];
```

- [ ] **Step 2: `sw.js` 两处兜底版本值升版**

把 `sw.js` 里这两行：

```javascript
        return m ? decodeURIComponent(m[1]) : '20261031b';
    } catch (e) {
        return '20261031b';
```

改成：

```javascript
        return m ? decodeURIComponent(m[1]) : '20261101a';
    } catch (e) {
        return '20261101a';
```

- [ ] **Step 3: `index.html` 四处 `?v=` 升版**

把 `index.html` 里这四处：

```html
    <link rel="stylesheet" href="assets/css/style.css?v=20261031b">
    <link rel="manifest" href="manifest.webmanifest?v=20261031b">
    <link rel="apple-touch-icon" href="assets/img/apple-touch-icon.png?v=20261031b">
```

以及：

```html
<script src="assets/js/app.js?v=20261031b"></script>
```

里的 `20261031b` 全部替换成 `20261101a`。

- [ ] **Step 4: `assets/js/app.js` 的 `DATA_VERSION` 升版**

把 `assets/js/app.js` 的这一行：

```javascript
const DATA_VERSION = (typeof window !== 'undefined' && window.__DATA_VERSION__) || '20261031b';
```

改成：

```javascript
const DATA_VERSION = (typeof window !== 'undefined' && window.__DATA_VERSION__) || '20261101a';
```

- [ ] **Step 5: 核对五件套共 7 处都升了**

Run:
```bash
git -C E:/cursor/djyj grep -n "20261031b" -- index.html assets/js/app.js sw.js
```
Expected: **无输出**（全部升完）。若还有输出，说明漏了一处。

- [ ] **Step 6: 跑全部体检**

```bash
node scripts/check_search_upgrade.js
npx --yes acorn@8 --ecma2019 assets/js/app.js
npx --yes acorn@8 --ecma2019 sw.js
python -u scripts/check_compat.py
python -u scripts/check_js_comments.py
python -u scripts/check_data.py
python -u scripts/check_sw_navigate.py
python -u scripts/check_reading_width.py
```
Expected: 全部零失败

- [ ] **Step 7: 起本地服务**

Run: `python -m http.server 8769 --directory E:/cursor/djyj --bind 127.0.0.1`
（后台运行；**换端口**是为了避开旧 origin 的 SW 缓存）

- [ ] **Step 8: 造一个隐藏密码门的临时副本**

```bash
python -u -c "import io,sys; sys.stdout.reconfigure(encoding='utf-8',errors='replace'); s=open('E:/cursor/djyj/index.html',encoding='utf-8').read(); s=s.replace('</head>','<style>#gate{display:none!important}body.gate-active{overflow:auto!important}</style></head>'); open('E:/cursor/djyj/_tmp_search_index.html','w',encoding='utf-8').write(s)"
```
（这是**目检用临时副本**，不进 git，Task 14 收尾时删掉。**不是**绕过认证的实现——真站的密码门保持原样。）

- [ ] **Step 9: 浏览器目检（跨刊检索）**

用浏览器打开 `http://127.0.0.1:8769/_tmp_search_index.html?x=1`，逐条核对：

1. 首页标题栏出现**两个**圆形按钮（放大镜 + 关于），放大镜在「关于」左边，二者不重叠；
2. 点放大镜 → 全屏搜索浮层打开，顶部有输入框，提示行写着「只搜索三刊文章标题（不含作者与板块）」；
3. 输入「中国」→ 结果按刊物分组，每组有组头「求是 N 篇」等，**组内期号由新到旧**；
4. **截图**这三处（首页按钮、浮层分组结果）；
5. 关闭浮层 → 回到首页，三刊封面卡片版面未变；
6. Console **0 错误 0 警告**，Network **0 失败 / 4xx / 5xx**。

- [ ] **Step 10: 浏览器目检（杂志内三刊开关）**

1. 点「求是」封面卡进入杂志，等 meta 加载完；
2. 搜索框输入「中国」→ 默认「本刊」模式，只出本刊结果（**与改动前一致**：仍是标题+作者+板块匹配）；
3. 切到「三刊」→ 结果变成分组视图，组头出现，「标题+正文 / 仅标题 / 仅正文」与「仅有全文」两个控件**消失**；
4. **对照检查**：三刊结果里出现的每一项，都必须能在本刊同词结果里找到（子集性质）；
5. 切回「本刊」→ 控件恢复，单刊结果样式与排序与改动前一致；
6. **截图**本刊结果与三刊分组结果各一张。

- [ ] **Step 11: 浏览器目检（索引缺失降级）**

```bash
mv E:/cursor/djyj/data/search_index.json E:/cursor/djyj/data/_search_index.json.bak
```
（用 `mv` 临时改名，不用删除命令）

1. 刷新页面 → 切到「三刊」→ 提示「索引不可用，仅可搜本刊」；
2. 切回「本刊」→ 搜索正常，文章页能打开；
3. 改回文件名：
```bash
mv E:/cursor/djyj/data/_search_index.json.bak E:/cursor/djyj/data/search_index.json
```

- [ ] **Step 12: 窄屏目检**

把浏览器视口调到窄屏（<768px），重复 Step 9–10，重点看：搜索区是否挤压、浮层在窄屏是否可输入可滚动、分组标题是否换行错乱。**截图**。

- [ ] **Step 13: 离线目检（索引进 SW 缓存后断网仍能跨刊搜标题）**

1. 先在**联网**状态下打开首页放大镜浮层，搜一次「中国」——这一次会把
   `data/search_index.json?v=20261101a` 拉进 SW 缓存；
2. 打开 DevTools 的 Network 面板，切到 **Offline**（离线）勾选；
3. 刷新页面 → 首页应能正常打开（外壳已缓存）→ 点放大镜 → 搜「中国」→
   **结果仍然分组正常出现**（索引来自 SW 缓存，不是网络）；
4. 切回 Online。

> **注意**：SW 只在首次访问后接管；离线前必须先联网访问过一次让 SW 安装完成。
> 若离线刷新后首页都打不开，说明外壳没缓存好，先排查 SW 而不是索引。

- [ ] **Step 14: 提交**

```bash
git -C E:/cursor/djyj add sw.js index.html assets/js/app.js
git -C E:/cursor/djyj commit -m "跨刊标题索引纳入 SW 预缓存，缓存破坏版本升至 20261101a

sw.js 的 DATA_ASSETS 增加 data/search_index.json（带版本号），
断网后仍可跨刊搜标题。

五件套 7 处同步升版：index.html 四处 ?v=、app.js 的 DATA_VERSION、
sw.js 两处兜底值。

验证范围：check_search_upgrade / check_compat / check_js_comments /
check_data / check_sw_navigate / check_reading_width 全部零失败；
浏览器实测跨刊分组、组内新→旧、单刊行为未变、索引缺失降级正常，
桌面与窄屏各截图目检，Console 0 错误。
已实现但未独立审查。"
```

- [ ] **Step 15: 推送**

```bash
git -C E:/cursor/djyj -c credential.helper= -c credential.helper="!gh auth git-credential" push origin main
```

---

## 批次二：正文搜索降本

### Task 8: 默认仅标题 + 「开始搜正文」显式触发

**Files:**
- Modify: `index.html`（搜索栏 scope 单选的默认选中项；`#searchView` 里加 `#bodySearchActions`）
- Modify: `assets/css/style.css`
- Modify: `assets/js/app.js`（`finishSearch` / 新增 `updateBodySearchActions` / `BODY_AVG_BYTES`）

**Interfaces:**
- Consumes: Task 4 的 `pickBodyWindow` / `formatBytes` / `getMagScope`。
- Produces:
  - `BODY_AVG_BYTES` 常量 = `{ qs: 236000, hqwg: 172000, djyj: 194000 }`（每期正文分片实测均值字节）
  - `estimateBodyBytes(mag, issues)` → `number`
  - `updateBodySearchActions()` → `undefined`：渲染「开始搜正文 / 继续搜索更早年份 / 停止」按钮区
  - `state.bodySearchKey` — `string`：`query|scope|bo` 指纹，用于判断是否续跑
  - `state.bodySearchCursor` — `number`：已搜过的期次数量（断点）
  - `state.bodySearchTotal` — `number`：该刊有正文的期次总数
  - `state.bodySearchRunning` — `boolean`
  - `state.bodySearchDone` — `number`：本轮已处理期次
  - DOM：`#bodySearchActions`

- [ ] **Step 1: `index.html` 把默认范围改成「仅标题」**

把 `index.html` 的这一行：

```html
            <label class="scope-option"><input type="radio" name="searchScope" value="all" checked> 标题+正文</label>
```

改成：

```html
            <label class="scope-option"><input type="radio" name="searchScope" value="all"> 标题+正文</label>
```

并把下一行：

```html
            <label class="scope-option"><input type="radio" name="searchScope" value="title"> 仅标题</label>
```

改成：

```html
            <label class="scope-option"><input type="radio" name="searchScope" value="title" checked> 仅标题</label>
```

- [ ] **Step 2: `index.html` 加按钮容器**

把 `index.html` 的这一段：

```html
    <div class="view" id="searchView">
        <div class="result-info" id="resultInfo"></div>
        <div id="searchResults" class="results-list"></div>
        <div id="pagination" class="pagination"></div>
    </div>
```

改成：

```html
    <div class="view" id="searchView">
        <div class="result-info" id="resultInfo"></div>
        <div class="body-search-actions" id="bodySearchActions" hidden></div>
        <div id="searchResults" class="results-list"></div>
        <div id="pagination" class="pagination"></div>
    </div>
```

- [ ] **Step 3: `assets/css/style.css` 加按钮样式**

在 `assets/css/style.css` 的 `/* ===== 主页：三刊搜索浮层 ===== */` 段之后追加：

```css
/* ===== 正文搜索：显式触发按钮 ===== */
.body-search-actions {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin: 10px 0 14px;
}
.body-search-actions[hidden] { display: none; }
.btn-ghost {
    padding: 8px 16px;
    border: 1px solid var(--border-2);
    border-radius: var(--radius);
    background: var(--card);
    color: var(--text);
    font-size: 13px;
    cursor: pointer;
    transition: all 0.15s var(--ease);
}
.btn-ghost:hover {
    border-color: var(--mag-color, var(--primary));
    color: var(--mag-color, var(--primary));
}
.btn-ghost:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}
.btn-ghost--warn {
    color: var(--primary);
    border-color: var(--primary-light);
}
.bs-progress {
    font-size: 13px;
    color: var(--text-2);
}
.bs-hint,
.bs-done {
    font-size: 12px;
    color: var(--text-3);
}
```

- [ ] **Step 4: `assets/css/style.css` 补兜底**

在 `@supports not (aspect-ratio: 3 / 4)` 兜底块里，「---- 跨刊结果分组 ----」那段之后插入：

```css
    .body-search-actions { gap: 0; }
    .body-search-actions > * + * { margin-left: 10px; }
```

- [ ] **Step 5: `assets/js/app.js` 加状态字段与常量**

把 `assets/js/app.js` 的 `state` 里这一行：

```javascript
    searchIndexStatus: 'idle',   // idle / loading / ready / error
```

改成：

```javascript
    searchIndexStatus: 'idle',   // idle / loading / ready / error
    bodySearchKey: '',      // 当前正文搜索的（词|范围|仅全文）指纹，用于判断是否续跑
    bodySearchCursor: 0,    // 已搜过的期次数量（断点，停止后再次触发从此处续）
    bodySearchTotal: 0,     // 该刊有正文的期次总数
    bodySearchRunning: false,
    bodySearchDone: 0,      // 本轮已处理的期次数（进度显示用）
```

在 `assets/js/app.js` 的 `const MAGAZINE_ORDER = [...]` 之后插入：

```javascript
/* 每期正文分片的实测均值（字节），用于在下载前告知用户预计流量。
   由 python scripts/build_search_index.py --print-avg 实测得出
   （qs 188 期 43.3 MB / hqwg 164 期 27.5 MB / djyj 70 期 13.2 MB）。
   数据更新后重跑该命令并更新这里。 */
const BODY_AVG_BYTES = { qs: 241619, hqwg: 176044, djyj: 198248 };
```

- [ ] **Step 6: `assets/js/app.js` 加估算与按钮渲染函数**

在 `assets/js/app.js` 的 `function finishSearch(results, query, scope, input) {` **之前**插入：

```javascript
/* 正文搜索的预计下载量：期次数 × 该刊每期均值 */
function estimateBodyBytes(mag, issues) {
    const avg = BODY_AVG_BYTES[mag] || 0;
    return (issues ? issues.length : 0) * avg;
}

/* 正文搜索按钮区：默认不下载，必须用户点「开始搜正文」才跑。 */
function updateBodySearchActions() {
    const box = document.getElementById('bodySearchActions');
    if (!box) return;
    const scope = getSearchScope();
    const magScope = getMagScope();
    if (magScope === 'all' || (scope !== 'all' && scope !== 'body')) {
        box.innerHTML = '';
        box.hidden = true;
        return;
    }
    const ms = getMagState();
    if (!ms) {
        box.innerHTML = '';
        box.hidden = true;
        return;
    }
    const issues = listBodyIssues(ms);
    state.bodySearchTotal = issues.length;
    box.hidden = false;

    if (state.bodySearchRunning) {
        box.innerHTML =
            '<span class="bs-progress">正在加载正文...（' + state.bodySearchDone + '/' + state.bodySearchTotal + ' 期）</span>'
            + '<button class="btn-ghost btn-ghost--warn" onclick="stopBodySearch()">停止</button>';
        return;
    }

    const cursor = Math.min(state.bodySearchCursor || 0, issues.length);
    if (cursor >= issues.length) {
        box.innerHTML = '<span class="bs-done">本刊正文已全部搜索完毕</span>';
        return;
    }

    const rest = issues.slice(cursor);
    const win = pickBodyWindow(rest, 3);
    const est = estimateBodyBytes(state.currentMag, win);
    const label = cursor === 0
        ? '开始搜正文（近 3 年 ' + win.length + ' 期 · 约 ' + formatBytes(est) + '）'
        : '继续搜索更早年份（' + win[0].y + '–' + win[win.length - 1].y + ' 年 · 约 ' + formatBytes(est) + '）';

    const query = (document.getElementById('searchInput').value || '').trim();
    box.innerHTML = '<button class="btn-ghost" id="bodySearchBtn" onclick="startBodySearch()"'
        + (query ? '' : ' disabled') + '>' + label + '</button>'
        + (query ? '' : '<span class="bs-hint">请先输入关键词</span>');
}
```

- [ ] **Step 7: `assets/js/app.js` 改 `finishSearch` 调用按钮渲染**

把 `assets/js/app.js` 的 `finishSearch()` 里这一行：

```javascript
    if (scope !== 'title' && !state.fullTextReady) infoText += ' · 全文搜索加载中，当前仅搜索标题/作者';
    document.getElementById('resultInfo').textContent = infoText;

    renderSearchPage();
```

改成：

```javascript
    if (scope !== 'title' && !state.fullTextReady) infoText += ' · 正文未加载，点下方按钮再搜正文';
    document.getElementById('resultInfo').textContent = infoText;

    renderSearchPage();
    updateBodySearchActions();
```

- [ ] **Step 8: `assets/js/app.js` 在 `performSearch` 里重置正文搜索断点**

把 `assets/js/app.js` 的 `performSearch()` 里这一行：

```javascript
    // 使上一次尚未结束的正文搜索失效
    state.searchToken++;
```

改成：

```javascript
    // 使上一次尚未结束的正文搜索失效
    state.searchToken++;

    // 正文搜索断点：查询词 / 范围 / 仅有全文 任一变化就从头开始，
    // 否则保留断点（停止后再次触发要能续跑）
    const scope0 = getSearchScope();
    const bo0 = document.getElementById('bodyOnly').checked;
    const bodyKey = query + '|' + scope0 + '|' + (bo0 ? '1' : '0');
    if (bodyKey !== state.bodySearchKey) {
        state.bodySearchKey = bodyKey;
        state.bodySearchCursor = 0;
        state.bodySearchRunning = false;
    }
    // 三刊模式下要把正文按钮区收起来（跨刊只搜标题）
    updateBodySearchActions();
```

- [ ] **Step 9: 跑全部体检**

```bash
node scripts/check_search_upgrade.js
npx --yes acorn@8 --ecma2019 assets/js/app.js
python -u scripts/check_compat.py
python -u scripts/check_js_comments.py
```
Expected: 全部零失败

- [ ] **Step 10: 提交**

```bash
git -C E:/cursor/djyj add index.html assets/css/style.css assets/js/app.js
git -C E:/cursor/djyj commit -m "正文搜索改为显式触发：默认仅标题 + 开始搜正文按钮

选「标题+正文」或「仅正文」时不再自动下载正文，改为出现
「开始搜正文（近 3 年 N 期 · 约 X MB）」按钮，点击才跑。
按钮上的下载量按各刊每期正文分片实测均值估算。

验证范围：node scripts/check_search_upgrade.js 12 条全绿；acorn --ecma2019 通过；
check_compat.py / check_js_comments.py 零失败。
按钮实际行为待 Task 10 浏览器目检。
已实现但未独立审查。"
```

---

### Task 9: 近 3 年窗口 + 由近及远渐进 + 继续/停止

**Files:**
- Modify: `assets/js/app.js`（替换 `performBodySearch` 为 `startBodySearch` / `runBodySearch` / `stopBodySearch`；`performSearch` 里去掉自动触发）

**Interfaces:**
- Consumes: Task 8 的 `updateBodySearchActions` / `estimateBodyBytes`；Task 4 的 `pickBodyWindow`。
- Produces:
  - `startBodySearch()` → `undefined`：取窗口、置 `state.bodySearchRunning = true`、调 `runBodySearch`
  - `runBodySearch(query, scope, bo, token, win, startAt)` → `Promise<void>`
  - `stopBodySearch()` → `undefined`：作废当前批次循环，保留已命中结果与断点
  - `BODY_YEAR_SPAN` 常量 = `3`

- [ ] **Step 1: `assets/js/app.js` 加 `BODY_YEAR_SPAN` 常量**

在 `assets/js/app.js` 的 `const BODY_AVG_BYTES = ...` 之后插入：

```javascript
/* 正文搜索窗口：最新年份起几年（基准是该刊数据里的最新年份，不是浏览器时间） */
const BODY_YEAR_SPAN = 3;
```

- [ ] **Step 2: `assets/js/app.js` 把 `performSearch` 里的自动触发改掉**

把 `assets/js/app.js` 的 `performSearch()` 里这一段：

```javascript
    // 标题搜索：立即执行
    let results;
    if (scope === 'title') {
        results = collectMatches(ms, query, scope, bo);
    } else {
        // 正文相关范围：先给出当前已加载正文能命中的结果，再按期增量补全
        results = collectMatches(ms, query, scope, bo);
        if (!ms.fullTextReady) {
            performBodySearch(query, results, scope, bo, state.searchToken);
            return;
        }
    }

    finishSearch(results, query, scope, input);
```

改成：

```javascript
    // 标题搜索：立即执行
    let results;
    if (scope === 'title') {
        results = collectMatches(ms, query, scope, bo);
    } else {
        // 正文相关范围：**不自动下载**。先把已加载正文能命中的结果给出来，
        // 正文部分等用户点「开始搜正文」再跑（见 startBodySearch）。
        results = collectMatches(ms, query, scope, bo);
    }

    finishSearch(results, query, scope, input);
```

- [ ] **Step 3: `assets/js/app.js` 用新实现替换 `performBodySearch`**

把 `assets/js/app.js` 里整个 `async function performBodySearch(...) { ... }`（从 `/* 正文搜索：按"期"增量加载...` 注释开始到该函数的结束大括号）替换为：

```javascript
/* 正文搜索：点「开始搜正文」后才跑。
   先跑该刊数据最新年份起的 BODY_YEAR_SPAN 年，跑完可继续搜更早年份；
   任何时候都能「停止」，停止后保留已命中结果与断点，再次触发从断点续。 */
function startBodySearch() {
    if (state.bodySearchRunning) return;
    const ms = getMagState();
    if (!ms) return;
    const input = document.getElementById('searchInput');
    const query = (input.value || '').trim().toLowerCase();
    if (!query) return;
    const scope = getSearchScope();
    const bo = document.getElementById('bodyOnly').checked;

    const key = query + '|' + scope + '|' + (bo ? '1' : '0');
    if (key !== state.bodySearchKey) {
        state.bodySearchKey = key;
        state.bodySearchCursor = 0;
    }

    const issues = listBodyIssues(ms);
    state.bodySearchTotal = issues.length;
    const cursor = Math.min(state.bodySearchCursor || 0, issues.length);
    const rest = issues.slice(cursor);
    if (!rest.length) {
        updateBodySearchActions();
        return;
    }
    const win = pickBodyWindow(rest, BODY_YEAR_SPAN);
    state.bodySearchRunning = true;
    state.bodySearchDone = cursor;
    updateBodySearchActions();
    runBodySearch(query, scope, bo, state.searchToken, win, cursor);
}

/* 跑一个窗口的期次：每批 6 期并发加载，每批完成即刷新结果。 */
async function runBodySearch(query, scope, bo, token, win, startAt) {
    const ms = getMagState();
    if (!ms) {
        state.bodySearchRunning = false;
        updateBodySearchActions();
        return;
    }
    const input = document.getElementById('searchInput');
    const infoEl = document.getElementById('resultInfo');
    const qDisplay = (input.value || '').trim();
    const scopeLabel = scope === 'all' ? '标题+正文' : '仅正文';
    const BATCH = 6;          // 每批并发的期次数
    let done = startAt;

    for (let k = 0; k < win.length; k += BATCH) {
        if (state.searchToken !== token) {
            state.bodySearchRunning = false;
            updateBodySearchActions();
            return;
        }
        const batch = win.slice(k, k + BATCH);
        await Promise.all(batch.map(it => loadIssueData(it.y, it.i)));
        // 等这一批的工夫里，用户可能已经改了关键词 / 换了范围 / 切了视图。
        // 慢网下这一等可达数秒，不重新校验就会把过期结果写回界面。
        if (state.searchToken !== token) {
            state.bodySearchRunning = false;
            updateBodySearchActions();
            return;
        }
        done += batch.length;
        state.bodySearchDone = done;
        state.bodySearchCursor = done;

        // 每批加载完立刻用最新的正文重新匹配并刷新结果
        const results = collectMatches(ms, query, scope, bo);
        state.searchResults = results;
        state.currentPage = 1;
        infoEl.textContent = '共 ' + results.length + ' 篇（关键词："' + qDisplay + '" ｜ 范围：' + scopeLabel + '）'
            + ' · 本刊 · 正文已加载 ' + done + '/' + state.bodySearchTotal + ' 期';
        renderSearchPage();
        updateBodySearchActions();
    }

    state.bodySearchRunning = false;
    if (state.bodySearchCursor >= state.bodySearchTotal) {
        ms.fullTextReady = true;
        state.fullTextReady = true;
    }
    updateBodySearchActions();
}

/* 停止正文搜索：作废当前批次循环，保留已命中结果与断点。 */
function stopBodySearch() {
    if (!state.bodySearchRunning) return;
    state.searchToken++;              // 让正在跑的循环立刻作废
    state.bodySearchRunning = false;
    updateBodySearchActions();
}
```

- [ ] **Step 4: 跑全部体检**

```bash
node scripts/check_search_upgrade.js
npx --yes acorn@8 --ecma2019 assets/js/app.js
python -u scripts/check_compat.py
python -u scripts/check_js_comments.py
```
Expected: 全部零失败

- [ ] **Step 5: 确认没有残留的 `performBodySearch` 引用**

Run: `git -C E:/cursor/djyj grep -n "performBodySearch" -- assets/js/app.js`
Expected: **无输出**（旧函数已整体替换，不留半成品）

- [ ] **Step 6: 提交**

```bash
git -C E:/cursor/djyj add assets/js/app.js
git -C E:/cursor/djyj commit -m "正文搜索改为由近及远渐进：近 3 年窗口 + 继续/停止

startBodySearch 按该刊数据最新年份起 3 年取窗口（基准不读浏览器时间），
每批 6 期并发加载、每批完成即刷新结果；窗口跑完出现「继续搜索更早年份」，
点击后从断点继续更早的期次。加载中可「停止」，停止后保留已命中结果与断点，
再次触发从断点续。

原 performBodySearch 整体替换，不留旧实现。

验证范围：node scripts/check_search_upgrade.js 12 条全绿；acorn --ecma2019 通过；
check_compat.py / check_js_comments.py 零失败；已确认无 performBodySearch 残留。
实际行为待 Task 10 浏览器目检。
已实现但未独立审查。"
```

---

### Task 10: 五件套升版 + 浏览器目检（批次二收尾）

**Files:**
- Modify: `sw.js`（两处兜底值）、`index.html`（四处 `?v=`）、`assets/js/app.js`（`DATA_VERSION`）

- [ ] **Step 1: `sw.js` 两处兜底版本值升到 `20261101b`**

把 `sw.js` 里的 `'20261101a'`（出现两次，都在 `VERSION` 的 IIFE 里）替换成 `'20261101b'`。

- [ ] **Step 2: `index.html` 四处 `?v=` 升到 `20261101b`**

把 `index.html` 里 `20261101a` 的 4 处替换成 `20261101b`。

- [ ] **Step 3: `assets/js/app.js` 的 `DATA_VERSION` 升到 `20261101b`**

把 `assets/js/app.js` 的 `DATA_VERSION` 兜底值 `'20261101a'` 换成 `'20261101b'`。

- [ ] **Step 4: 核对 7 处都升了**

Run: `git -C E:/cursor/djyj grep -n "20261101a" -- index.html assets/js/app.js sw.js`
Expected: **无输出**

- [ ] **Step 5: 跑全部体检**

```bash
node scripts/check_search_upgrade.js
npx --yes acorn@8 --ecma2019 assets/js/app.js
npx --yes acorn@8 --ecma2019 sw.js
python -u scripts/check_compat.py
python -u scripts/check_js_comments.py
python -u scripts/check_data.py
python -u scripts/check_sw_navigate.py
python -u scripts/check_reading_width.py
python -u scripts/check_mianshi.py
python -u scripts/check_essays.py
```
Expected: 全部零失败

- [ ] **Step 6: 浏览器目检（正文搜索显式触发）**

用 `http://127.0.0.1:8769/_tmp_search_index.html?x=2`（**换端口或改查询串**避免旧 SW 缓存）：

1. 进入「求是」→ 搜索框输入「中国」；
2. **默认范围应是「仅标题」**（选中态在「仅标题」上），结果条不含「正在加载」字样；
3. 切到「标题+正文」→ **Network 面板不应出现任何 `data/qs/issues/*.json` 请求**（不自动下载），按钮区出现「开始搜正文（近 3 年 68 期 · 约 16.0 MB）」；
4. **截图**这一屏；
5. 点「开始搜正文」→ 进度条推进（「正在加载正文...（12/188 期）」），结果条出现「正文已加载 68/188 期」；
6. 窗口跑完 → 按钮变成「继续搜索更早年份（2019–2023 年 · 约 X MB）」；
7. 点「继续搜索更早年份」→ 进度继续推进；
8. 点「停止」→ 进度停住，**已命中的结果仍在**，按钮回到「继续搜索更早年份」；
9. 再点「继续搜索更早年份」→ 从断点续（进度不回退到 0）；
10. 全部跑完 → 按钮区显示「本刊正文已全部搜索完毕」；
11. Console **0 错误 0 警告**。

- [ ] **Step 7: 窄屏目检**

窄屏重复 Step 6 的 1–4 步，重点看按钮是否换行错乱、按钮文字是否被截断。**截图**。

- [ ] **Step 8: 提交**

```bash
git -C E:/cursor/djyj add sw.js index.html assets/js/app.js
git -C E:/cursor/djyj commit -m "正文搜索降本上线，缓存破坏版本升至 20261101b

五件套 7 处同步升版：index.html 四处 ?v=、app.js 的 DATA_VERSION、
sw.js 两处兜底值。

验证范围：check_search_upgrade / check_compat / check_js_comments /
check_data / check_sw_navigate / check_reading_width / check_mianshi /
check_essays 全部零失败；浏览器实测「选标题+正文不自动下载、
点开始搜正文才跑、近 3 年窗口、继续搜索更早年份、停止后保留结果并从断点续」，
桌面与窄屏各截图目检，Console 0 错误。
已实现但未独立审查。"
```

- [ ] **Step 9: 推送**

```bash
git -C E:/cursor/djyj -c credential.helper= -c credential.helper="!gh auth git-credential" push origin main
```

---

## 批次三：附带小改

### Task 11: 三个专题页接入密码门 + 「返回刊物首页」入口

**Files:**
- Modify: `linxuan-beikao-zhinan/linxuan-beikao-zhinan.html`
- Modify: `hubei-linxuan-guide/hubei-linxuan-guide.html`
- Modify: `hubei-linxuan-mianshi/hubei-linxuan-mianshi.html`

**Interfaces:**
- Consumes: `assets/js/app.js` 里密码门的既有约定（`localStorage` 键 `djyj_gate_ok` / `djyj_gate_ts`，12 小时会话）。
- Produces: 三页各自具备与主页一致的密码门；后两页具备「返回刊物首页」链接。

- [ ] **Step 1: 先量一下三页的现状**

```bash
git -C E:/cursor/djyj grep -n "djyj_gate_ok" -- linxuan-beikao-zhinan hubei-linxuan-guide hubei-linxuan-mianshi
git -C E:/cursor/djyj grep -n "返回刊物首页" -- linxuan-beikao-zhinan hubei-linxuan-guide hubei-linxuan-mianshi
```
Expected: 两条命令都**无输出**（三页都没有门；只有 `linxuan-beikao-zhinan` 有「返回刊物首页」，另两页没有）。

- [ ] **Step 2: 确定门逻辑的约定（不新增代码，只对齐既有约定）**

三个专题页是**自包含静态 HTML**，不引用 `assets/js/app.js`，所以必须各自内联一段门逻辑。
为避免三页各写一套、日后互相漂移，先把约定写清楚，再在 Step 3 里**原样**贴进三页：

| 约定 | 值 | 出处 |
| --- | --- | --- |
| 已通过标记 | `localStorage['djyj_gate_ok'] === '1'` | `assets/js/app.js` 密码门 IIFE |
| 会话起始时间 | `localStorage['djyj_gate_ts'] = String(Date.now())` | 同上 |
| 有效期 | 12 小时（`12 * 60 * 60 * 1000` 毫秒） | 同上 |
| 密码 | `5255` | 同上 |
| DOM id | `gate` / `gateForm` / `gateInput` / `gateToggle` / `gateHint` | `index.html` 密码门 |

> **本步不改任何文件** —— 三页的代码在 Step 3–4 一次性写入，Step 6 再用检查命令确认三页一致。

- [ ] **Step 3: 给三页加门 DOM**

把下面这段 HTML **原样**插进三个专题页的 `</body>` 之前：

```html
<!-- ===== 访问密码门（与主站一致） ===== -->
<div id="gate" class="gate" role="dialog" aria-modal="true" aria-labelledby="gateTitle">
    <div class="gate-card">
        <h1 id="gateTitle" class="gate-title">党内刊物检索系统</h1>
        <p class="gate-subtitle">请输入访问密码以继续</p>
        <form id="gateForm" class="gate-form" autocomplete="off" novalidate>
            <div class="gate-input-wrap" id="gateInputWrap">
                <input type="password" id="gateInput" class="gate-input" inputmode="numeric" maxlength="20" placeholder="访问密码" aria-label="访问密码">
                <button type="button" id="gateToggle" class="gate-toggle" aria-label="显示密码" title="显示密码">显示</button>
            </div>
            <button type="submit" class="gate-submit">进入系统</button>
            <p id="gateHint" class="gate-hint" role="status" aria-live="polite"></p>
        </form>
        <p class="gate-footer">本系统为非公开内容，仅限内部学习研究使用</p>
    </div>
</div>
<script>
(function () {
    'use strict';
    var STORAGE_KEY = 'djyj_gate_ok';
    var STORAGE_TS = 'djyj_gate_ts';
    var PASSWORD = '5255';
    var TTL_MS = 12 * 60 * 60 * 1000;

    function isAuthed() {
        try {
            if (localStorage.getItem(STORAGE_KEY) !== '1') return false;
            var ts = parseInt(localStorage.getItem(STORAGE_TS) || '0', 10);
            if (!ts) return false;
            return (Date.now() - ts) < TTL_MS;
        } catch (e) { return false; }
    }
    function setAuthed() {
        try {
            localStorage.setItem(STORAGE_KEY, '1');
            localStorage.setItem(STORAGE_TS, String(Date.now()));
        } catch (e) {}
    }
    function showGate() {
        var gate = document.getElementById('gate');
        if (gate) gate.classList.remove('gate--hidden');
        document.body.classList.add('gate-active');
        setTimeout(function () {
            var input = document.getElementById('gateInput');
            if (input) input.focus();
        }, 200);
    }
    function hideGate() {
        var gate = document.getElementById('gate');
        if (gate) gate.classList.add('gate--hidden');
        document.body.classList.remove('gate-active');
    }
    function bind() {
        var form = document.getElementById('gateForm');
        var input = document.getElementById('gateInput');
        var toggle = document.getElementById('gateToggle');
        if (!form || !input) return;
        if (toggle) {
            toggle.addEventListener('click', function () {
                input.type = input.type === 'password' ? 'text' : 'password';
                input.focus();
            });
        }
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            if (input.value === PASSWORD) {
                setAuthed();
                hideGate();
            } else {
                input.classList.add('gate-input--err');
                var hint = document.getElementById('gateHint');
                if (hint) {
                    hint.textContent = '密码错误，请重试';
                    hint.className = 'gate-hint gate-hint--err';
                }
                input.select();
            }
        });
    }
    if (isAuthed()) {
        hideGate();
    } else {
        bind();
        showGate();
    }
})();
</script>
```

- [ ] **Step 4: 给三页补门样式**

在三个专题页各自的 `<style>` 块末尾追加（**各页的配色变量名可能不同，`var(--x)` 取不到时用回退值**）：

```css
/* ===== 访问密码门（与主站一致） ===== */
#gate {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.55);
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
}
#gate.gate--hidden { display: none; }
body.gate-active { overflow: hidden; }
.gate-card {
    background: var(--card, #fff);
    border-radius: 12px;
    padding: 28px 24px;
    max-width: 360px;
    width: 100%;
    text-align: center;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.28);
}
.gate-title { font-size: 20px; margin: 0 0 6px; }
.gate-subtitle { font-size: 13px; margin: 0 0 18px; color: var(--text-3, #666); }
.gate-form { display: flex; flex-direction: column; gap: 10px; }
.gate-input-wrap { display: flex; align-items: center; gap: 6px; }
.gate-input {
    flex: 1;
    padding: 10px 12px;
    border: 1px solid var(--border-2, #ccc);
    border-radius: 8px;
    font-size: 15px;
    -webkit-appearance: none;
    appearance: none;
}
.gate-input--err { border-color: #c0392b; }
.gate-toggle {
    padding: 9px 10px;
    border: 1px solid var(--border-2, #ccc);
    border-radius: 8px;
    background: transparent;
    color: var(--text-2, #444);
    cursor: pointer;
    font-size: 12px;
}
.gate-submit {
    padding: 10px 16px;
    border: none;
    border-radius: 8px;
    background: var(--primary, #8b0000);
    color: #fff;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
}
.gate-hint { font-size: 12px; min-height: 16px; margin: 0; color: #c0392b; }
.gate-hint--ok { color: #2e7d32; }
.gate-footer { font-size: 11px; color: var(--text-3, #888); margin: 16px 0 0; }
```

> **flex gap 注意**：`.gate-form` 与 `.gate-input-wrap` 用了 `gap`，而这三个专题页的 CSS 文件**没有** `@supports not (aspect-ratio: 3 / 4)` 兜底块 → `scripts/check_compat.py` 会报「CSS 兜底缺失」。
> **改法**：把这两处的 `gap` 去掉，改用 `margin`：
> ```css
> .gate-form { display: flex; flex-direction: column; }
> .gate-form > * + * { margin-top: 10px; }
> .gate-input-wrap { display: flex; align-items: center; }
> .gate-input-wrap > * + * { margin-left: 6px; }
> ```

- [ ] **Step 5: 给 `hubei-linxuan-guide` 与 `hubei-linxuan-mianshi` 补「返回刊物首页」**

在这两页的 `<body>` 靠前位置（页面主容器之前）插入：

```html
<p class="back-home-link"><a href="../index.html">← 返回刊物首页</a></p>
```

并在各页 `<style>` 块末尾追加：

```css
.back-home-link {
    margin: 14px 18px 0;
    font-size: 13px;
}
.back-home-link a { color: var(--primary, #991b1b); text-decoration: none; }
```

> 注意：`hubei-linxuan-guide` 与 `hubei-linxuan-mianshi` 的主色变量是 `--accent: #991b1b`，主站是 `--primary: #8b0000`。上面用了 `var(--primary, #991b1b)` 的回退写法，两种情况都能取到颜色。

- [ ] **Step 6: 确认三页的门逻辑一致（防止日后三页各改各的）**

```bash
python -u -c "import io,sys; sys.stdout.reconfigure(encoding='utf-8',errors='replace'); \
pages=['E:/cursor/djyj/linxuan-beikao-zhinan/linxuan-beikao-zhinan.html', \
'E:/cursor/djyj/hubei-linxuan-guide/hubei-linxuan-guide.html', \
'E:/cursor/djyj/hubei-linxuan-mianshi/hubei-linxuan-mianshi.html']; \
need=['djyj_gate_ok','djyj_gate_ts','5255','12 * 60 * 60 * 1000']; \
bad=0; \
[print(('OK  ' if all(n in open(p,encoding='utf-8').read() for n in need) else 'FAIL'), p.split('/')[-2]) for p in pages]"
```
Expected: 三行都是 `OK  `

- [ ] **Step 7: 跑兼容性体检**

Run: `python -u scripts/check_compat.py`
Expected: `✅ 未发现 Chrome 69 不兼容的用法`（若报「CSS 兜底缺失」，说明 Step 4 的 `gap` 没改干净）

- [ ] **Step 8: 跑 JS 注释体检**

Run: `python -u scripts/check_js_comments.py`
Expected: 全绿（三页的内联脚本里**不能出现 `/*`**，注释一律用 `//`）

- [ ] **Step 9: 浏览器目检**

用 `http://127.0.0.1:8769/hubei-linxuan-guide/hubei-linxuan-guide.html?x=1` 等三个地址各打开一次：

1. 三个页面都出现密码门遮罩，页面正文被挡住；
2. **不要代填密码**：确认「门挡住了内容」即可。密码正确性由主页那道门验证过，这里只验「门生效」；
3. 另两页顶部能看到「← 返回刊物首页」，点它能回到 `../index.html`；
4. Console **0 错误**。

- [ ] **Step 10: 提交**

```bash
git -C E:/cursor/djyj add linxuan-beikao-zhinan/linxuan-beikao-zhinan.html hubei-linxuan-guide/hubei-linxuan-guide.html hubei-linxuan-mianshi/hubei-linxuan-mianshi.html
git -C E:/cursor/djyj commit -m "三个专题页接入访问密码门，另两页补返回刊物首页入口

专题页是自包含静态 HTML、不引用 app.js，因此各自内联一段与主页一致的门逻辑
（djyj_gate_ok / djyj_gate_ts，12 小时会话，密码 5255）。
此前专题页可绕过密码门直接读到全文。

荆楚遴选备考全书 / 湖北省直遴选面试指南 两页补「← 返回刊物首页」入口。

验证范围：check_compat.py 与 check_js_comments.py 零失败；
三页门逻辑一致性检查通过；浏览器实测三页均被密码门遮住、返回入口可点，
Console 0 错误。
已实现但未独立审查。"
```

---

### Task 12: 主站 `@media print` + 目录期次去重复年份 + 设置面板滚动收起

**Files:**
- Modify: `assets/css/style.css`（新增 `@media print` 块）
- Modify: `assets/js/app.js`（`renderCatalog` 里期次标题；`initReadingSettingsListeners` 里滚动收起）

**Interfaces:**
- Consumes: 无新增接口。
- Produces: 打印时隐藏导航/侧栏/浮层、只留正文；目录期次行不再重复写年份；阅读设置面板滚动时自动收起。

- [ ] **Step 1: `assets/css/style.css` 加 `@media print`**

在 `assets/css/style.css` 末尾追加：

```css
/* ===== 打印 ===== */
@media print {
    .app-sidebar,
    .nav-tabs,
    .bottom-nav,
    .search-bar,
    .offline-bar,
    .update-toast,
    .back-to-top,
    .article-page-header,
    .article-settings-panel,
    .ap-continue,
    .home-page,
    .global-search,
    .pagination,
    .filters {
        display: none !important;
    }
    .app-main {
        margin: 0 !important;
        padding: 0 !important;
    }
    .article-page-body {
        max-width: none !important;
        padding: 0 !important;
        font-size: 12pt !important;
        color: #000 !important;
        background: #fff !important;
    }
    .article-page {
        position: static !important;
    }
    .ap-related,
    .article-page-footer {
        display: block !important;
    }
    a[href]::after {
        content: "";
    }
}
```

> **注意**：`.global-search` 与 `.filters` 在 `@media print` 里被隐藏 —— `@media print` 是媒体查询，不受 `check_compat.py` 的特性黑名单限制。

- [ ] **Step 2: `assets/js/app.js` 目录期次行去掉重复年份**

把 `assets/js/app.js` 里 `renderCatalog` 中这一行：

```html
                    <span class="ir-title">${year}年第${cin}期</span>
```

改成：

```html
                    <span class="ir-title">第${cin}期</span>
```

> 年份已经在上一层的 `.yb-header`（`${year}年`）里写过了，期次行再写一遍是重复。

- [ ] **Step 3: `assets/js/app.js` 阅读设置面板滚动自动收起**

在 `assets/js/app.js` 的 `initReadingSettingsListeners()` 函数**末尾**追加：

```javascript
    // 滚动时自动收起设置面板：面板是 position:fixed 的浮层，
    // 不收起会一直挡住正文（此前实测滚动时仍悬浮遮挡）。
    let scrollHideTimer = null;
    window.addEventListener('scroll', function () {
        const panel = document.getElementById('articleSettingsPanel');
        if (!panel || !panel.classList.contains('show')) return;
        if (scrollHideTimer) clearTimeout(scrollHideTimer);
        scrollHideTimer = setTimeout(function () {
            panel.classList.remove('show');
            const btn = document.getElementById('articleSettingsBtn');
            if (btn) btn.classList.remove('active');
        }, 250);
    }, { passive: true });
```

> `{ passive: true }` 是 Chrome 49+，Chrome 69 支持。`check_compat.py` 不查这个。

- [ ] **Step 4: 跑全部体检**

```bash
npx --yes acorn@8 --ecma2019 assets/js/app.js
python -u scripts/check_compat.py
python -u scripts/check_js_comments.py
python -u scripts/check_reading_width.py
```
Expected: 全部零失败

- [ ] **Step 5: 浏览器目检**

1. 目录视图：年份组下每期只写「第 N 期」，不再重复年份；**截图**；
2. 阅读页：打开「阅读设置」→ 向下滚动 → 面板自动收起；**截图**；
3. 打印预览（浏览器 `Ctrl+P`）：只剩正文，没有侧栏/搜索框/浮动按钮；**截图**。

- [ ] **Step 6: 提交**

```bash
git -C E:/cursor/djyj add assets/css/style.css assets/js/app.js
git -C E:/cursor/djyj commit -m "附带小改：主站加打印样式、目录期次去重复年份、设置面板滚动收起

主站此前没有 @media print（三个专题页里倒有两个有），打印出来会带上
侧栏、搜索框、浮动按钮和首页元素。

目录期次行不再重复写年份（年份已在年份组标题上）。
阅读设置面板在页面滚动时自动收起，避免悬浮遮挡正文。

验证范围：acorn --ecma2019 通过；check_compat.py / check_js_comments.py /
check_reading_width.py 零失败；浏览器实测目录、滚动收起、打印预览三项并截图。
已实现但未独立审查。"
```

---

### Task 13: 五件套升版 + 全量回归（批次三收尾）

**Files:**
- Modify: `sw.js`（两处兜底值）、`index.html`（四处 `?v=`）、`assets/js/app.js`（`DATA_VERSION`）

- [ ] **Step 1: 升版本到 `20261101c`**

`sw.js` 两处兜底值、`index.html` 四处 `?v=`、`assets/js/app.js` 的 `DATA_VERSION` 全部从 `20261101b` 换成 `20261101c`。

- [ ] **Step 2: 核对 7 处都升了**

Run: `git -C E:/cursor/djyj grep -n "20261101b" -- index.html assets/js/app.js sw.js`
Expected: **无输出**

- [ ] **Step 3: 全量体检**

```bash
node scripts/check_search_upgrade.js
npx --yes acorn@8 --ecma2019 assets/js/app.js
npx --yes acorn@8 --ecma2019 sw.js
python -u scripts/check_compat.py
python -u scripts/check_js_comments.py
python -u scripts/check_data.py
python -u scripts/check_sw_navigate.py
python -u scripts/check_reading_width.py
python -u scripts/check_mianshi.py
python -u scripts/check_essays.py
python -u scripts/fix_catalog_order.py --check
python -u scripts/fix_catalog_order.py --self-test
python -u scripts/clean_meta_authors.py --self-test
python -u scripts/build_search_index.py --check
python -u scripts/build_search_index.py --self-test
```
Expected: 全部零失败；`build_search_index.py --check` 输出 `OK   data/search_index.json 与三份 meta.json 一致`

- [ ] **Step 4: 全量浏览器目检（桌面 + 窄屏）**

按 Task 7 Step 9–12 与 Task 10 Step 6–7 的清单全部重跑一遍，重点确认批次二、三的改动**没有回退批次一的行为**：

1. 首页放大镜浮层可用；
2. 杂志内「本刊 / 三刊」开关可用，三刊结果分组、组内新→旧；
3. 单刊结果与批次一之前完全一致；
4. 正文搜索默认不下载、点按钮才跑、近 3 年窗口、继续/停止；
5. 目录期次不重复年份；
6. 设置面板滚动收起；
7. 打印预览只剩正文；
8. Console 0 错误 0 警告，Network 0 失败。

- [ ] **Step 5: 提交**

```bash
git -C E:/cursor/djyj add sw.js index.html assets/js/app.js
git -C E:/cursor/djyj commit -m "批次三收尾：缓存破坏版本升至 20261101c

五件套 7 处同步升版：index.html 四处 ?v=、app.js 的 DATA_VERSION、
sw.js 两处兜底值。

验证范围：全量体检脚本全部零失败（含 build_search_index --check /
--self-test、fix_catalog_order --check/--self-test、clean_meta_authors
--self-test）；桌面与窄屏全量浏览器目检，Console 0 错误。
已实现但未独立审查。"
```

- [ ] **Step 6: 推送**

```bash
git -C E:/cursor/djyj -c credential.helper= -c credential.helper="!gh auth git-credential" push origin main
```

---

### Task 14: 收尾清理 + 更正设计文档

**Files:**
- Modify: `docs/superpowers/specs/2026-11-01-search-upgrade-design.md`（更正 §4.1、§6.3）
- Delete: `E:/cursor/djyj/_tmp_search_index.html`（目检用临时副本）

- [ ] **Step 1: 更正设计文档 §4.1 的行序表述**

把设计文档 §4.1 表格里的这一行：

```
| 行序 | `qs → hqwg → djyj` 升序 → `y` 降序 → `i` 降序 → 期内沿用 `meta.json` 现有顺序（= 官网目录顺序）。按降序排是为了让前端取到即得「新 → 旧」，不必在客户端再排 |
```

改成：

```
| 行序 | 固定展示顺序 `qs → hqwg → djyj`（**不是字母序**；字母序会是 djyj → hqwg → qs）→ `y` 降序 → `i` 降序 → 期内沿用 `meta.json` 现有顺序（= 官网目录顺序）。按降序排是为了让前端取到即得「新 → 旧」，不必在客户端再排 |
```

- [ ] **Step 2: 更正设计文档 §6.3 的期次顺序表述**

把设计文档 §6.3 代码块里的这一行：

```
  → listBodyIssues(ms) 改为按 (y, i) 降序
```

改成：

```
  → listBodyIssues(ms) 已是按 (y, i) 降序（app.js 里原本就是新→旧，本轮不改）
```

并把紧随其后的：

```
`maxYear` 取该刊 `meta.json` 中最大的 `y`（不读浏览器时间，D6）。
```

改成：

```
`maxYear` 取该刊 `meta.json` 中最大的 `y`（不读浏览器时间，D6）。
本轮实际实现用的是 `pickBodyWindow(issues, 3)`：窗口基准取期次表里最大的年份，
期次表本身已按 (y, i) 降序排列。
```

- [ ] **Step 3: 更正设计文档 §8.1 的 S3 规则表述**

把设计文档 §8.1 表格里的这一行：

```
| 无重复 | 索引内 URL 无重复 |
```

改成：

```
| 无重复 | **同一刊物内** URL 无重复（跨刊允许重复：「网站声明」同时出现在《求是》和《红旗文稿》的目录里，实测三刊 7415 行、唯一 URL 7413 个） |
```

- [ ] **Step 4: 删掉目检用的临时副本**

Run（**顶层单条纯命令，不与其他命令串接**）：
```bash
rm -- "E:/cursor/djyj/_tmp_search_index.html"
```
Expected: 输出 `mavis-trash: moved to trash`

- [ ] **Step 5: 停掉本地静态服务**

停掉 8769 端口的 `python -m http.server`（若 8768 那个还在跑，一并停掉）。

- [ ] **Step 6: 确认工作区干净**

Run: `git -C E:/cursor/djyj status --short`
Expected: 只有 `docs/superpowers/specs/2026-11-01-search-upgrade-design.md` 被修改（待提交）

- [ ] **Step 7: 提交并推送**

```bash
git -C E:/cursor/djyj add docs/superpowers/specs/2026-11-01-search-upgrade-design.md
git -C E:/cursor/djyj commit -m "更正设计文档三处与代码实际/真实数据不符的表述

§4.1 行序：明确是固定展示顺序 qs→hqwg→djyj，不是字母序。
§6.3 期次顺序：listBodyIssues 本来就是 (y,i) 降序，实际实现改用
pickBodyWindow(issues, 3) 取窗口。
§8.1 S3 规则：改为「同一刊物内 URL 无重复」。实测三刊 7415 行、唯一 URL
7413 个，「网站声明」同时出现在求是与红旗文稿的目录里，是真实数据。

已实现但未独立审查。"
```

```bash
git -C E:/cursor/djyj -c credential.helper= -c credential.helper="!gh auth git-credential" push origin main
```

---

## 最终验收清单

全部做完后逐条核对（对应设计文档 §12 的 DoD）：

| # | 验收项 | 怎么验 | 落在哪个任务 |
| --- | --- | --- | --- |
| 1 | 主页放大镜与杂志内「三刊」开关都能跨刊标题检索，结果分组正确、期号新→旧 | 浏览器目检 | Task 7 / 10 / 13 |
| 2 | 单刊检索行为与改动前一致 | 浏览器对照截图 | Task 5 / 7 |
| 3 | 正文搜索默认不下载，点「开始搜正文」后才跑，默认窗口为该刊最新年份起 3 年 | 浏览器 + Network 面板 | Task 10 / 13 |
| 4 | 「继续搜索更早年份」与「停止」均可用，停止后结果与进度保留 | 浏览器目检 | Task 9 / 10 |
| 5 | 索引缺失时跨刊降级提示正常，本刊功能无异常 | 临时改名索引文件后目检 | Task 7 |
| 6 | `build_search_index.py --self-test` ≥12 条含 3 条反向自检全通过 | 命令行 | Task 1 / 13 |
| 7 | `check_data.py` 新增 S1–S4 四条断言全通过 | 命令行 | Task 2 / 13 |
| 8 | `check_compat.py` / `check_js_comments.py` / `check_sw_navigate.py` / `check_reading_width.py` 全部零失败 | 命令行 | 每个批次的收尾任务 |
| 9 | 桌面与窄屏各一轮截图目检，Console 0 错误 | 浏览器 | Task 7 / 10 / 13 |
| 10 | 三批各自独立提交，提交信息诚实标注验证范围与「已实现但未独立审查」 | `git log` | 全部提交 |

### 线上验证（推送后）

```bash
python -u -c "import urllib.request,sys; sys.stdout.reconfigure(encoding='utf-8',errors='replace'); \
req=urllib.request.Request('https://paper.zhouhao.cn/data/search_index.json', headers={'User-Agent':'Mozilla/5.0'}); \
r=urllib.request.urlopen(req); b=r.read(); print(r.status, len(b), b[:40])"
```
Expected: `200 1000280 b'{"v":"20261101a","cols":["m","y","i","t","u"],"rows":[["qs"`

> **字节数 1000280 是本计划编写时用真实三刊 meta 实测出来的**（7415 行 / 976.8 KB）。
> 数据更新后索引会变，这个数字要跟着变 —— 判据是**量级**（约 1 MB，且明显大于 index.html 的 28472 字节），
> 不是这个具体值。

> **判据提醒**：Cloudflare Pages 的 SPA 回退会把**任何不存在的路径**都返回 200 + index.html。
> 所以验证线上文件是否真的存在，必须**比对字节数**（索引应约 1 MB，index.html 是 28472 字节）
> 并看**响应体开头**（索引以 `{"v":"` 开头，index.html 以 `<!DOCTYPE html>` 开头）。只看 200 会误判。

```bash
python -u -c "import urllib.request,sys; sys.stdout.reconfigure(encoding='utf-8',errors='replace'); \
req=urllib.request.Request('https://paper.zhouhao.cn/index.html', headers={'User-Agent':'Mozilla/5.0'}); \
print(urllib.request.urlopen(req).read().decode('utf-8').count('20261101c'), '处版本号')"
```
Expected: `4 处版本号`（index.html 的四处 `?v=`）

---

## 计划自检记录

### 一、文字层自检

**1. spec 覆盖**：设计文档 §12 的 10 条 DoD 逐条对应到任务（见上表）；§9 的三批划分逐条对应到 Task 1–13；§8.1 的体检要求对应到 Task 1（`--self-test`）、Task 2（S1–S4）、Task 3（`check_search_upgrade.js`）；§8.2 的 9 条浏览器目检项对应到 Task 7 Step 9–13、Task 10 Step 6–7、Task 13 Step 4；§8.3 的离线测试对应到 Task 7 Step 13。

**2. 占位扫描**：全文无 TBD / TODO / 「类似 Task N」/ 「补充错误处理」/ 无代码的「写测试」步骤。每处代码改动都给了可直接粘贴的完整代码块。

**3. 类型与函数名一致性**：`searchAllTitles(index, query)`、`groupCrossMagResults(results)`、`pickBodyWindow(issues, yearSpan)`、`formatBytes(n)`、`estimateBodyBytes(mag, issues)`、`loadSearchIndex()`、`getMagScope()`、`syncMagScopeChecked()`、`renderCrossMagResults()`、`updateBodySearchActions()`、`startBodySearch()`、`runBodySearch(query, scope, bo, token, win, startAt)`、`stopBodySearch()` 在各任务中的定义与调用签名一致；`MAGAZINE_ORDER` / `BODY_AVG_BYTES` / `BODY_YEAR_SPAN` / `INDEX_VERSION` / `MAG_ORDER` 各只定义一次。

### 二、代码层自检（把计划里的代码真的拼出来跑）

计划正文里的每段代码都被抽出来，组装成完整的 `index.html` / `style.css` / `app.js` / `check_data.py` / `build_search_index.py` / `check_search_upgrade.js`，
在临时目录里用**仓库自带的体检脚本**实跑。跑出来的问题已全部回填到本计划：

| # | 自检发现的问题 | 处理 |
| --- | --- | --- |
| 1 | `build_search_index.py` **缺 `__main__` 入口**，直接跑什么都不输出 | 补 Step 5，并写明「入口必须放文件末尾」（`main`/`self_test` 都在其后定义） |
| 2 | 索引生成器的 **R7 排序比较方向写反**（`(y,-i)` 元组比较），导致**正对照自己就报错** | 改为 `(a.y, a.i) < (b.y, b.i)`（旧→新才算违规） |
| 3 | `check_search_upgrade.js` 在 vm 沙箱里用 `ctx.__api` 取不到（`ctx` 不在沙箱作用域内） | 改用 `globalThis.__api`（与 `check_related.js` 同一套路；因是字符串字面量，不触发 `check_compat.py` 的 `globalThis` 黑名单） |
| 4 | Node 脚本的 R4（组内顺序）**没有样本可查** —— 查询词只命中每刊一篇，组内没有相邻对 | 查询词改用「新篇」，能同时命中求是的两篇，R4 才有意义；R10/R11 同步改 |
| 5 | Node 的 `console.log('%-4s')` 不支持 printf 补位，字面输出 `%-4s` | 改用 `c.rule.padEnd(4)` |
| 6 | **S3「索引内 URL 无重复」在真实数据上不成立** —— 三刊 7415 行、唯一 URL 7413 个，「网站声明」同时出现在《求是》和《红旗文稿》目录里 | S3 改为「同一刊物内 URL 无重复」；全局去重会破坏 S1（行数必须等于 meta 条目数之和）。**生成器里的 R4 规则同病**，一并改成同一刊物口径，并补一条 R4 反向自检（Task 1 实施时独立复核真实数据发现） |
| 7 | 跨刊分支的 `loadSearchIndex().then(...)` 缺令牌校验，等索引期间改了关键词会把过期结果写回界面 | 加 `tok` 校验，与正文搜索用同一个 `state.searchToken` 机制 |
| 8 | 三刊模式下正文按钮区不会被收起（`finishSearch` 在跨刊分支不执行） | 跨刊分支显式清空并隐藏 `#bodySearchActions`；`performSearch` 里补 `updateBodySearchActions()` |
| 9 | 计划新增的 CSS 里有三处 `display:flex` + `gap` 容器（`.result-group` / `.result-group-head` / `.body-search-actions`），Chrome 69 会丢间距 | 三个都补了 `@supports not (aspect-ratio: 3 / 4)` 兜底条目，`check_compat.py` 实跑已确认零失败 |

**实跑结果（全部零失败）：**

```
build_search_index.py --self-test      14 条用例全绿（含 4 条反向自检，断言到规则编号一级）
build_search_index.py --check          OK  7415 行 / 1000280 字节
check_search_upgrade.js                12 条用例全绿（含 3 条反向自检）
check_data.py（含 S1~S4）              索引问题数: 0
check_compat.py                        ✅ 未发现 Chrome 69 不兼容的用法
check_js_comments.py                   ✅ 未发现"块注释内出现 /*" + SW 求值冒烟通过
acorn --ecma2019 assets/js/app.js      0 错
```

**反向验证**：把索引第 6 行的 URL 改坏 → `check_data.py` 的 S2 报出「有 1 行在 meta 中找不到对应条目」→ 重建索引后恢复「逐行可寻址：全部命中」。
说明 S2 确实有鉴别力，不是恒绿摆设。

**已知与设计文档的偏离**（已在「与设计文档的三处修正」表列出，并在 Task 14 更正文档）：行序的「升序」措辞、期次顺序的冗余改动、S3 的范围。

