# Chrome 69 兼容性适配

本文件记录"为什么以及如何让网站在 Chrome 69（2018 年发布）下正常工作"。

> **背景**：用户群中部分人使用 2018 年前后的浏览器（如内网机、办公机、老旧平板），需要保证站点能在 Chrome 69 上正常运行。

---

## 1. Chrome 69 的限制

Chrome 69 是 2018 年发布的版本（V8 引擎 6.9）。它**不支持**以下现代特性：

| 特性 | Chrome 支持版本 | 影响 |
| --- | --- | --- |
| `oklch()` / `oklab()` 颜色 | 111+ | 颜色失效（默认黑色） |
| `aspect-ratio` | 88+ | 比例盒子坍塌 |
| `:has()` 选择器 | 105+ | 选中态样式失效 |
| `gap` (flex/grid) | 84+ | 元素挤在一起 |
| `100dvh` 单位 | 108+ | 被忽略 |
| `backdrop-filter` | 76+ | 模糊失效（不影响布局） |
| `accent-color` | 93+ | 表单颜色默认 |
| JS 可选链 `?.` | 80+ | **脚本直接语法错误** |
| JS 空值合并 `??` | 80+ | 同上 |
| JS `replaceAll` | 85+ | 抛错 |
| JS `matchAll` | 73+ | 抛错 |
| JS `Object.fromEntries` | 73+ | 抛错 |
| JS `Array.prototype.at` | 92+ | 抛错 |
| JS `globalThis` | 71+ | 抛错 |
| JS 逻辑赋值 `||=` `&&=` `??=` | 85+ | 抛错 |
| JS 数字分隔符 `1_000_000` | 75+ | 抛错 |

> **最致命的是 `?.`**：12 处可选链会导致整个 `app.js` 解析失败，**网站所有功能瘫痪**。所以这是首要适配目标。

---

## 2. 适配策略

### 2.1 CSS 颜色：oklch → hex

**问题**：85 处 `oklch()` 颜色。Chrome 69 完全不识别，颜色会变成默认黑/白。

**方案**：批量转换为 hex 近似值。

**实现**（`scripts/oklch_to_hex.py`）：

```python
# 简化：维护一张常用 L,C,H → hex 的查找表
TABLE = {
    (0.48, 0.17, 27):  "#a41c1c",  # primary
    (0.58, 0.14, 27):  "#bf3535",  # primary-light
    # ... 共 30+ 条
}
# 找不到的走 oklch_to_hex(l, c, h_deg) 计算
```

**踩坑**：`oklch(from var(...) l c h / 0.08)`（相对颜色语法，119+）需要手工替换为固定 `rgba(139, 0, 0, 0.08)`。

### 2.2 比例盒子：aspect-ratio → padding-top

**问题**：2 处 `aspect-ratio: 3 / 4`（杂志封面）。Chrome 69 完全忽略，封面坍塌。

**方案**：用 `@supports not` 包裹 padding-top 75% hack：

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

**JS 同步**（在 `init()` 中或 radio change 事件里）：

```js
document.querySelectorAll('input[name="searchScope"]').forEach(r => {
    r.addEventListener('change', () => {
        document.querySelectorAll('.scope-option').forEach(opt => {
            const radio = opt.querySelector('input');
            opt.classList.toggle('checked', radio && radio.checked);
        });
    });
});
```

### 2.4 flex gap → margin 兜底

**问题**：约 35 处 `gap` 属性（flex 容器的水平/垂直间距）。Chrome 69 忽略，元素挤在一起。

**方案**：用相邻兄弟选择器 `> * + *` 补 margin：

```css
.magazine-grid > * + * { margin-top: 20px; }   /* column */
.nav-tabs > * + * { margin-left: 4px; }        /* row */
```

**实现**（`scripts/gap_fallback.py`）：

- 解析 `style.css` 中所有 `gap` 出现位置
- 根据 flex direction（row/column）决定 margin-left/margin-top
- 在文件末尾追加 31 条 fallback 规则

**踩坑**：

- `> * + *` 只对**前一个**兄弟加 margin，最后一个不需
- 对 `gap: 0` 的容器也要加 `margin: 0`（但写 `0` 等同于不加）
- 桌面/移动不同断点可能要重复添加

### 2.5 JS 可选链 `?.` → ES5

**问题**：12 处 `obj?.prop` 在 Chrome 69 直接抛 `SyntaxError`，整个 `app.js` 加载失败。

**方案**：逐个替换为 ES5 等价写法。

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
- 替换后必须用 `node --check` 验证语法
- 替换前先 grep 列出所有 `\.?\.[a-zA-Z]` 模式

### 2.6 100dvh → vh

**问题**：`100dvh` 是 dynamic viewport height，iOS Safari 在工具栏出现/消失时高度变化更平滑。Chrome 69 看到 `100dvh` 直接忽略（无效值）。

**方案**：保留 `100vh` 在前，`100dvh` 在后：

```css
.home-page {
    min-height: 100vh;     /* Chrome 69 使用 */
    min-height: 100dvh;    /* modern browsers 覆盖 */
}
```

**踩坑**：两个属性名一样但值不同，重复声明覆盖规则适用。

### 2.7 backdrop-filter

**问题**：`backdrop-filter: blur(8px)` Chrome 76+ 才有。69 不支持但**静默忽略**，不影响布局。

**方案**：加 `-webkit-backdrop-filter` 前缀（更老的浏览器支持）。效果在 69 上不存在但可接受。

```css
-webkit-backdrop-filter: blur(8px);
backdrop-filter: blur(8px);
```

### 2.8 accent-color

**问题**：`accent-color` 用于 radio/checkbox 的强调色，Chrome 93+ 支持。69 忽略。

**方案**：保留即可。69 上 radio 仍为浏览器默认蓝色，UI 不破。

---

## 3. 验证清单

每次适配后，用以下方法验证：

### 3.1 静态分析

```bash
# CSS 检查 oklch 残留
grep -r "oklch" assets/css/

# JS 检查 ?. 残留
grep -r '?\.' assets/js/

# gap 残留
grep -E 'gap\s*:' assets/css/
```

### 3.2 浏览器实际测试

1. 用 Chrome 69（或更早版本）打开站点
2. 重点测试：
   - 首页：封面图是否正常显示
   - 搜索：选中态是否有颜色
   - 板块卡片：是否垂直堆叠有间距
   - 文章页：能否加载并阅读
3. 用 DevTools Console 检查 JS 错误

### 3.3 性能数据

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

---

## 5. 推荐做法

### 5.1 用 Can I Use 查询

任何新特性在用之前，先查 [caniuse.com](https://caniuse.com/)。

### 5.2 关键流程

1. **设计阶段**：在 caniuse 上查兼容
2. **写代码阶段**：默认用现代特性，但加 `@supports` 兜底
3. **测试阶段**：用 BrowserStack 或本地多浏览器测试
4. **上线阶段**：在 `_headers` 加 `Vary: User-Agent` 不必要，但要监控错误日志

### 5.3 工具

- `caniuse.com`：兼容性查询
- `postcss-preset-env`：自动加前缀
- `core-js`：JS polyfill
- `browserslist`：声明目标浏览器范围

### 5.4 未来规划

如果 Chrome 69 用户占比 < 5%，可以移除兼容代码。统计方法：

- Cloudflare Web Analytics
- Google Analytics（如果用的话）
- 简单的 JS 检测 + 上报到 `console.log`
