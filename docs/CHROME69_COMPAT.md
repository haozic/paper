# Chrome 69 兼容性适配

本文件记录"为什么以及如何让网站在 Chrome 69（2018 年发布）下正常工作"。

> **背景**：用户群中部分人使用 2018 年前后的浏览器（如内网机、办公机、老旧平板），需要保证站点能在 Chrome 69 上正常运行。
>
> **当前状态（2026-10-30 复盘后）**：主站 + 两个独立子页均已适配，`scripts/check_compat.py` 体检全绿。

---

## 1. Chrome 69 的限制

Chrome 69 是 2018 年发布的版本（V8 引擎 6.9）。它**不支持**以下现代特性：

| 特性 | Chrome 支持版本 | 影响 |
| --- | --- | --- |
| `oklch()` / `oklab()` 颜色 | 111+ | 颜色失效（默认黑色） |
| `aspect-ratio` | 88+ | 比例盒子坍塌 |
| `:has()` 选择器 | 105+ | 选中态样式失效 |
| `inset` 简写 | 87+ | 定位塌陷成 0 尺寸 |
| `gap`（**flex**） | 84+ | 元素挤在一起 |
| `gap`（grid） | 66+ | ✅ Chrome 69 支持 |
| `100dvh` 单位 | 108+ | 被忽略 |
| `backdrop-filter` | 76+ | 模糊失效（不影响布局） |
| `accent-color` | 93+ | 表单颜色默认 |
| `appearance` 简写 | 84+ | 表单控件外观失效 |
| JS 可选链 `?.` | 80+ | **脚本直接语法错误** |
| JS 空值合并 `??` | 80+ | 同上 |
| JS `replaceAll` | 85+ | 抛错 |
| JS `matchAll` | 73+ | 抛错 |
| JS `Object.fromEntries` | 73+ | 抛错 |
| JS `Array.prototype.at` | 92+ | 抛错 |
| JS `globalThis` | 71+ | 抛错 |
| JS 逻辑赋值 `\|\|=` `&&=` `??=` | 85+ | 抛错 |
| JS 数字分隔符 `1_000_000` | 75+ | 抛错 |

> **最致命的是 `?.`**：可选链会导致整个 `app.js` 解析失败，**网站所有功能瘫痪**。所以这是首要适配目标。
>
> 当前 `assets/js/app.js` 及三个 HTML 页面的内联脚本已全部通过 `acorn --ecma2019` 解析（Chrome 69 的语法上限），无任何超限语法。

---

## 2. 适配策略

### 2.1 CSS 颜色：oklch → hex

**问题**：早期版本有 85 处 `oklch()` 颜色。Chrome 69 完全不识别，颜色会变成默认黑/白。

**方案**：批量转换为 hex 近似值（`scripts/oklch_to_hex.py` 为一次性转换脚本，转换结果已并入 `assets/css/style.css`，脚本未保留在仓库中）。

**踩坑**：`oklch(from var(...) l c h / 0.08)`（相对颜色语法，119+）需要手工替换为固定 `rgba(139, 0, 0, 0.08)`。

### 2.2 比例盒子：aspect-ratio → padding-top

**问题**：2 处 `aspect-ratio: 3 / 4`（杂志封面）。Chrome 69 完全忽略，封面坍塌。

**方案**：用 `@supports not` 包裹 padding-top hack：

```css
.mag-cover {
    width: 100%;
    aspect-ratio: 3 / 4;  /* modern browsers */
    height: auto;
}
@supports not (aspect-ratio: 3 / 4) {
    .mag-cover {
        position: relative;
        height: 0;
        padding-top: 133.3333%;  /* 4/3 */
    }
    .mag-cover-inner {
        position: absolute;
        top: 0; left: 0; right: 0; bottom: 0;
        display: flex !important;
    }
}
```

**踩坑**：

- `padding-top: 75%` 在宽度 100% 的盒子里 = 高度 = 宽度 * 0.75，对应 4:3（不是 3:4）
- 需要 `position: relative` + 子元素 `position: absolute` 覆盖

### 2.3 :has() 选择器 → 类 + JS 同步

**问题**：2 处 `.scope-option:has(input:checked)`（搜索范围选中态）。Chrome 69 整条规则被忽略。

**方案**：增加 `.checked` 镜像类，由 JS 同步：

```css
.scope-option.checked,
.scope-option:has(input:checked) {
    background: var(--mag-color);
    color: white;
}
```

**JS 同步**（`assets/js/app.js` 的 `syncScopeChecked()`，在 `init()` 与 radio change 时各调一次）：

```js
function syncScopeChecked() {
    document.querySelectorAll('.scope-option').forEach(opt => {
        const input = opt.querySelector('input[name="searchScope"]');
        if (input && input.checked) opt.classList.add('checked');
        else opt.classList.remove('checked');
    });
}
```

> ⚠️ 嵌套的 `input` 也要换色：`.scope-option.checked input[type="radio"]:checked` 是独立规则，漏掉会导致 radio 本身颜色不变。

### 2.4 flex gap → margin 兜底

**问题**：`style.css` 里 34 个 flex 容器使用了 `gap`。Chrome 69 忽略 flex 的 gap，元素全部挤在一起。

**方案**：在文件末尾追加 `@supports` 兜底块，用相邻兄弟选择器 `> * + *` 补 margin：

```css
.magazine-grid > * + * { margin-top: 20px; }   /* column */
.nav-tabs > * + * { margin-left: 4px; }        /* row */
```

**关键决策：为什么用 `aspect-ratio` 而不是 `gap` 做旧版浏览器标记**

Chrome 66 起就支持 **grid** 的 gap，所以 `@supports not (gap: 1px)` 在 Chrome 66~83 会误判为"已支持 flex gap"。因此统一用 `aspect-ratio`（Chrome 88+）作为"旧版浏览器"标记，与 §2.2 的写法保持一致。

**关键决策：先 `gap: 0` 归零再补 margin**

兜底块生效于 Chrome 87 及更早。其中 Chrome 84~87 **已经支持** flex gap，若只补 margin 就会与 gap 叠加成双倍间距。所以兜底块里先把这些容器的 `gap` 归零，间距一律交给 margin：

```css
@supports not (aspect-ratio: 3 / 4) {
    .nav-tabs { gap: 0; }                       /* 归零，避免与 margin 叠加 */
    .nav-tabs > * + * { margin-left: 4px; }
}
```

grid 容器**不归零**（`.section-list` 在 ≥768px 是 grid，保留 `gap: 16px`）。

**坑：裸文本是匿名 flex 项**

`> * + *` 只选中元素节点。以下容器里有一个"元素 + 裸文本"的组合，`> * + *` 选不中，得给前置元素补 `margin-right`：

| 容器 | 结构 | 兜底写法 |
| --- | --- | --- |
| `.search-status` | `::before` + 文本 | `.search-status::before { margin-right: 4px }` |
| `.nav-tab` | `svg` + 文本(+徽标) | `.nav-tab .icon { margin-right: 6px }`、`.nav-tab .fav-badge { margin-left: 8px }` |
| `.scope-option` | `input` + 文本 | `.scope-option input[type="radio"] { margin-right: 3px }` |
| `.filter-check` | `input` + 文本 | `.filter-check input[type="checkbox"] { margin-right: 4px }` |
| `.fh-count` | `svg` + 文本 | `.fh-count svg { margin-right: 6px }` |
| `.about-link` | `svg` + 文本 | `.about-link svg { margin-right: 6px }` |
| `.sc-count` | 文本 + `.sc-unit` | `.sc-count .sc-unit { margin-left: 2px }` |

> `.nav-tab .fav-badge` 写 8px 而不是 6px：徽标自带 `margin-left: 2px`，原生路径是 gap 6px + 2px = 8px。

**坑：`flex-wrap: wrap` 容器**

`.filters` 是 `flex-wrap: wrap`。`> * + *` 会让换行后每行第一个元素也带上左边距。它只有 2 个子元素且用 `justify-content: space-between`，视觉差异可忽略。

**子页面同样需要兜底**

`linxuan-beikao-zhinan/linxuan-beikao-zhinan.html` 内联样式里有 4 个 flex 容器带 gap（`.framework-card .steps`、`.hot-badge`、`.magazine-card .mag-header`、`.article-link`），在其 `<style>` 末尾追加了同构的 `@supports not (aspect-ratio: 1 / 1)` 兜底块。

### 2.5 inset 简写 → 长写兜底

**问题**：`inset: 0` 是 Chrome 87+ 的简写。Chrome 69 上整块塌陷为 0 尺寸。

**这次的真实故障**：访问密码门 `.gate` 用了 `inset: 0`，遮罩层塌陷后又被 `body.gate-active { overflow: hidden }` 锁死滚动 → **白屏且滚不动**。

**方案**：同一规则里补长写（`inset` 保留作现代浏览器的覆盖）：

```css
.gate {
    position: fixed;
    top: 0; right: 0; bottom: 0; left: 0;   /* Chrome 69 兜底 */
    inset: 0;                                 /* modern browsers 覆盖 */
    ...
}
```

涉及 `.gate`、`.gate-bg`、`.gate-bg-pattern`、`.gate-emblem::after`，以及子页 `hubei-linxuan-guide` 的 `.sidebar-backdrop`。

### 2.6 JS 可选链 `?.` → ES5

**问题**：`obj?.prop` 在 Chrome 69 直接抛 `SyntaxError`，整个 `app.js` 加载失败。

**方案**：逐个替换为 ES5 等价写法（早期已批量完成，当前代码里已无 `?.`）。

| 原代码 | 替换为 |
| --- | --- |
| `getMagState()?.meta` | `var ms = getMagState(); ms ? ms.meta : []` |
| `ms.articleIndex?.[url]` | `ms.articleIndex ? ms.articleIndex[url] : undefined` |
| `document.getElementById('x')?.classList.remove('s')` | `var el = document.getElementById('x'); if (el) el.classList.remove('s')` |
| `e?.stopPropagation()` | `if (e && e.stopPropagation) e.stopPropagation()` |
| `e.state?.mag` | `(e.state && e.state.mag)` |
| `panel?.classList.contains('show')` | `panel && panel.classList.contains('show')` |

**踩坑**：

- `var` 关键字（不能用 `let`/`const`）— 但实际改写后用 `var` 即可保持兼容
- 替换后必须用 `node --check` 验证语法（现用 `npx acorn --ecma2019`，等价于 Chrome 69 的语法上限）
- 替换前先 grep 列出所有 `\.?\.[a-zA-Z]` 模式

### 2.7 100dvh → vh

**问题**：`100dvh` 是 dynamic viewport height，iOS Safari 在工具栏出现/消失时高度变化更平滑。Chrome 69 看到 `100dvh` 直接忽略（无效值）。

**方案**：保留 `100vh` 在前，`100dvh` 在后：

```css
.home-page {
    min-height: 100vh;     /* Chrome 69 使用 */
    min-height: 100dvh;    /* modern browsers 覆盖 */
}
```

### 2.8 backdrop-filter

**问题**：`backdrop-filter: blur(8px)` Chrome 76+ 才有。69 不支持但**静默忽略**，不影响布局。

**方案**：加 `-webkit-backdrop-filter` 前缀（更老的浏览器支持）。效果在 69 上不存在但可接受。

```css
-webkit-backdrop-filter: blur(8px);
backdrop-filter: blur(8px);
```

### 2.9 accent-color / appearance → 自绘表单控件

**问题**：`accent-color` 需 Chrome 93+，`appearance` 简写需 Chrome 84+。Chrome 69 上 radio/checkbox 是浏览器默认外观（蓝色），与站点的红色主题不一致。

**方案**：统一自绘，**所有浏览器观感一致**（不再依赖 `accent-color`）：

```css
.scope-option input[type="radio"],
.filter-check input[type="checkbox"] {
    -webkit-appearance: none;
    appearance: none;
    /* 边框、圆角、尺寸等 */
}
.scope-option input[type="radio"]:checked {
    background-image: radial-gradient(circle at center, #fff 0, #fff 4px, transparent 4.5px);
}
```

---

## 3. 验证清单

### 3.1 静态体检（推荐）

```bash
# Chrome 69 兼容性体检：特性黑名单 + flex gap 兜底缺失检查
python scripts/check_compat.py

# 顺便打印特性清单与各版本要求
python scripts/check_compat.py --list
```

脚本会扫描 `assets/css/style.css`、`assets/js/*.js`、以及所有 HTML 的内联 `<style>` / `<script>`，有三类检查：

- **A. 特性黑名单**：按"规则块"粒度判断，同规则内有等价旧写法（或文件内有 `@supports` 兜底）时不误报；
- **B. flex gap 兜底**：任何 `display:flex` + `gap` 的容器，必须在同文件的 `@supports` 兜底块里出现，否则报错——**这正是本次回归的根因**；
- **C. JS 语法**：先剥离字符串字面量与注释，避免把 `` `#m=${key}` `` 误判成类私有字段。

**`@supports` 的两种语义（体检脚本已区分）**：

Chrome 69 本身就支持 `@supports`（Chrome 28+），所以条件块在 Chrome 69 上要么整块生效、要么整块忽略：

| 写法 | Chrome 69 上的行为 | 体检脚本的判定 |
| --- | --- | --- |
| `@supports not (aspect-ratio: 3 / 4)` | **整块生效**（Chrome 69 没有 aspect-ratio） | 逐条检查；块内选择器记为"已覆盖兜底" |
| `@supports (content-visibility: auto)` | **整块忽略**（Chrome 69 没有 content-visibility） | 整块跳过，无需兜底 |
| `@supports (display: grid)` | **整块生效**（Chrome 69 有 grid） | 逐条检查 |

判定依据是条件里检测的特性是否在 `FEATURES` 黑名单内。因此新增现代特性时，
只要放进 `@supports (该特性: ...)` 里，Chrome 69 会自动忽略，**不需要写兜底**；
但反过来，把现代特性写在 `@supports not (...)` 兜底块里是错的（那块在 Chrome 69 上生效）。

体检脚本自身的判定逻辑有反向自测，改完解析器请跑：

```bash
python scripts/test_check_compat.py    # 15 条用例，覆盖 @supports / @media / 注释 / 兜底缺失
```

原始 grep 方式（仅作辅助）：

```bash
grep -rn "oklch" assets/css/          # CSS oklch 残留
grep -rn '?\.' assets/js/             # JS 可选链残留
grep -rEn 'gap\s*:' assets/css/       # gap 使用点
```

### 3.2 语法校验

```bash
# JS 按 Chrome 69 的语法上限（ES2019）解析
npx --yes acorn@8 --ecma2019 assets/js/app.js

# CSS 语法校验
npx --yes csstree-validator@3 assets/css/style.css
# 已知误报：env()、text-justify: inter-ideograph（csstree 词表过时，浏览器无害）
```

### 3.3 注释层体检（防"块注释提前闭合"）

**语法校验查不出一类 bug：块注释被提前闭合。**

JS 的块注释不嵌套，注释里一旦出现 `*/` 注释就提前结束，后面的注释文字会被当成代码解析。
这类 bug **语法完全合法**（acorn / node --check / eslint 一律通过），只在**运行期**抛错。

本仓库在 `sw.js` 上真实踩过一次：文件头注释里写了 `data/**/issues/*.json`，
其中的 `*/` 提前闭合了注释 → `issues` 变成未定义标识符 → Service Worker
`script evaluation failed` → 整个离线能力静默失效。

```bash
# 词法扫描：报出块注释内部出现 "/*" 的位置（本项目约定：注释里不写带 "/*" 的路径）
python scripts/check_js_comments.py

# 只跑词法扫描（不跑求值冒烟）
python scripts/check_js_comments.py --no-runtime

# 求值冒烟 + 词法扫描（含反向自检，证明检查确实有鉴别力）
python scripts/check_js_comments.py --self-test
```

求值冒烟会在 mock 的 Service Worker 全局环境里真正求值 `sw.js`，
捕获求值期异常，并检查 `install` / `activate` / `fetch` / `message` 四个监听器都注册了。
没有 node 时会自动跳过这一步并明确说明。

> **反向自检**里有一组对照：把真实事故形态注入 `sw.js` 副本 → 求值必须失败
> （`ReferenceError: issues is not defined`）；正常 `sw.js` → 求值必须通过。
> 没有这组对照，就无法证明这个检查抓得住真问题。

### 3.4 兜底等效性验证（重要）

兜底块在现代浏览器里默认不生效，无法直接看到。验证办法是**翻转标记强制启用**：

```bash
# 把 @supports not (aspect-ratio: ...) 改成 @supports (aspect-ratio: ...)
# → 现代浏览器里兜底块生效 → 与原生渲染逐像素对照
```

判断标准：**翻转前后渲染一致**（唯一差异是人为注入的标记边框）。这一步能证明兜底块是等价实现，而不是"看起来差不多"。

### 3.5 浏览器实际测试

1. 用 Chrome 69（或更早版本）打开站点
2. 重点测试：
   - 首页：封面图是否正常显示
   - 搜索：选中态是否有颜色
   - 板块卡片：是否垂直堆叠有间距
   - 文章页：能否加载并阅读
3. 用 DevTools Console 检查 JS 错误

### 3.6 性能数据

| 浏览器 | 首屏加载 | 搜索响应 |
| --- | --- | --- |
| Chrome 69 | 1.5–2.5 s | 200–500 ms |
| Chrome 100+ | 1.0–1.5 s | < 100 ms |

---

## 4. 历史踩坑

### 4.1 第一次没找到 19 期目录

求是 19 期（发布于 9/30）的目录 URL 不会出现在 `mulu.htm`（只显示最新期）。需要从 2026 年汇总页里找。**解决方法**：在 `find_issue_url_in_year` 中按"第N期"文本上下文匹配最近的 `c.html` 链接。

### 4.2 oklch 替换脚本的精度问题

早期脚本对 `(0.48, 0.17, 27)` 这种四舍五入不到 `(0.48, 0.17, 27.0)` 的值会找不到。需要用 `round(l, 6)` 等做容差匹配。

### 4.3 gap fallback 与 flex-wrap 冲突

对于 `flex-wrap: wrap` 的容器，`> * + *` 会让第一行最后一个元素也加 margin-right（视觉上不平衡）。解决：在 `wrap` 的容器上用 `gap` 优先，fallback 加 `> *` 而非 `> * + *`。

### 4.4 :has() 替换时漏改一处

`scope-option:has(input:checked) input` 不只是改块本身的样式，**嵌套的 input** 也要换色。漏改会导致 radio 本身颜色不变（仅背景变色），看起来突兀。

### 4.5 ⚠️ 兜底块"写了但从未生效"（2026-10-30 回归）

旧版 "Chrome 69 Gap Fallback" 段里，**所有选择器都漏写了前导点**：

```css
/* 错误：magazine-grid 匹配不到任何元素 */
magazine-grid > * + * { margin-top: 20px; }
/* 正确 */
.magazine-grid > * + * { margin-top: 20px; }
```

规则从未匹配过任何元素，等于没有兜底，却因为"文件里有兜底段"给人虚假的安全感。

**教训**：兼容性代码的正确性不能靠肉眼扫读，必须有工具能回答"这条规则到底匹配到东西了吗"。这就是 `scripts/check_compat.py` 的 B 类检查要解决的问题。

### 4.6 ⚠️ 兜底块"生效了但会双倍间距"（Chrome 84~87）

只补 margin 不归零 gap，会让 Chrome 84~87（已支持 flex gap）出现双倍间距。**兜底块必须先 `gap: 0` 归零**。

### 4.7 ⚠️ 注释里的路径让整个 Service Worker 静默失效（2026-10-30）

`sw.js` 文件头注释里写了 `data/**/issues/*.json`：

```js
/* ... (data/**/issues/*.json) ... */
```

JS 的块注释不嵌套，里面的 `*/` **提前闭合了注释**，于是：

1. `issues` 变成一个未定义的标识符 → 求值阶段 `ReferenceError`
2. 后面的 `/*` 又开启了新注释，把 `'use strict'` 也吞了进去
3. Service Worker `script evaluation failed`，**离线能力完全失效，且没有任何语法报错**

**为什么没被拦住**：`npx acorn --ecma2019 sw.js` 退出码 0 —— 因为这段文本被解析成了
合法的（但语义错误的）JS。**语法正确 ≠ 运行正确**，语法校验对这类 bug 完全无能为力。

**怎么发现的**：浏览器 Console 里的 `Service Worker 注册失败：… script evaluation failed`。
这类"注册失败但页面照常工作"的假象很危险 —— 页面上完全看不出异常，
只有真断网时才会发现离线是坏的。

**教训**：

1. **JS 注释里不要写带 `/*` 的路径**（`articles/*.md`、`data/**/issues` 都不行）。
   本仓库把这条定为硬规则，由 `scripts/check_js_comments.py` 强制。
2. **新增 Service Worker / Worker 脚本后，必须做一次"真的把它加载起来"的验证**，
   不能只看语法检查通过。`scripts/check_js_comments.py` 的求值冒烟就是干这个的。
3. **功能必须有独立于 UI 的可见信号**。这次是因为 Console 里恰好有一条注册失败警告
   才被发现；如果连警告都没有，这个 bug 会一路带到线上。

### 4.8 ⚠️ 规则"写对了"但窄视口下等于没写（2026-10-30）

用户反馈"正文阅读页调整页边距的按钮没有反应"。查下来事件绑定、变量写入、
按钮高亮全部正常，根因在 CSS 的表达方式：

```css
.article-page-body {
    max-width: calc(var(--article-w-base) + var(--article-w-delta));  /* 基准 860px */
    box-sizing: border-box;
}
```

`max-width` 只在"元素本来比 max-width 宽"时才起作用。窄视口下元素宽被视口顶住，
于是（视口 799px，基准 860px）：

| 档位 | max-width | 实际元素宽 | 正文宽 |
|---|---|---|---|
| 窄 (-80) | 780px | 780px | 684px |
| 标准 (0) | 860px | 799px（视口顶住） | 703px |
| 宽 (+120) | 980px | **799px（视口顶住）** | **703px（与标准完全相同）** |

"宽"这一档是**死档**（0 变化），"窄"也只差 19px 肉眼基本看不出；
手机上（375px）三档全部 0 变化。这种 bug 不报错、不白屏、没有任何异常信号，
只能靠人眼对比才发现。

**教训**：

1. **凡是"用户能点的开关"，都必须能断言"点了之后一定有可测量的差异"。**
   差异不能只体现在某个中间变量上，必须落到用户能看到的几何量。
2. **响应式设计里，`max-width` 不是"栏宽"，它只是上限。** 真正决定"栏有多宽"
   的往往是"视口"和"留白"，所以要让用户能调的东西，必须调这两个里真正生效的那个。
3. **症状是"点了没反应"时，优先怀疑"表达式在目标场景下退化成恒等"**，
   而不是先怀疑事件绑定。绑定没挂上会有明显报错（按钮高亮也不动），
   而表达式退化是**静默**的。

现在改成双机制：`--article-gutter` 控制左右留白（用户说的"页边距"，三档硬拉开
差异，任何视口宽度下都生效）+ `--article-w-delta` 控制 `max-width`（宽屏上继续
调整整栏宽度）。并新增 `scripts/check_reading_width.py`：它解析 CSS 算出各视口下
三档的实际正文宽度，断言三者互不相同且"窄 < 标准 < 宽"，带反向自检证明它对
"只有 max-width"的旧写法确实会报错。

---

## 5. 推荐做法

### 5.1 用 Can I Use 查询

任何新特性在用之前，先查 [caniuse.com](https://caniuse.com/)。

### 5.2 关键流程

1. **设计阶段**：在 caniuse 上查兼容
2. **写代码阶段**：默认用现代特性，但加 `@supports` 兜底
3. **测试阶段**：跑 `python scripts/check_compat.py` + 兜底等效性验证（§3.4）
4. **改 JS 后**：跑 `python scripts/check_js_comments.py`（§3.3），它会真的把
   Service Worker 脚本加载起来求值一遍
5. **改了阅读设置类的开关后**：跑 `python scripts/check_reading_width.py`（§4.8），
   断言"用户点的开关一定产生可测量的几何差异"
6. **上线阶段**：在 `_headers` 加 `Vary: User-Agent` 不必要，但要监控错误日志

### 5.3 工具

- `caniuse.com`：兼容性查询
- `postcss-preset-env`：自动加前缀
- `core-js`：JS polyfill
- `browserslist`：声明目标浏览器范围
- `scripts/check_compat.py`：本仓库自带的 Chrome 69 体检（零依赖）
- `scripts/check_js_comments.py`：JS 注释层体检 + Service Worker 求值冒烟（零依赖）
- `scripts/check_reading_width.py`：阅读页宽度/页边距三档体检 + 反向自检（零依赖）

### 5.4 未来规划

如果 Chrome 69 用户占比 < 5%，可以移除兼容代码。统计方法：

- Cloudflare Web Analytics
- Google Analytics（如果用的话）
- 简单的 JS 检测 + 上报到 `console.log`
