# 系统架构

本文件描述"党内刊物检索系统"的技术架构、模块划分与数据流向，供维护者快速理解全貌。

---

## 1. 总览

整个系统是一个**纯静态单页应用**（SPA-like），由 4 层组成：

```
┌────────────────────────────────────────────────────────┐
│  Cloudflare Pages（CDN + 边缘缓存）                       │
│  自定义头：_headers（data/ 一年缓存、assets/ 必须 revalidate）│
└────────────────────────────────────────────────────────┘
            ↓ HTTPS
┌────────────────────────────────────────────────────────┐
│  index.html  +  assets/css/style.css  +  assets/js/app.js│
│  ── 单页应用入口（首页 / 杂志 / 文章 / 板块 / 目录 / 收藏）  │
│  sw.js  +  manifest.webmanifest  ── PWA 外壳与离线缓存     │
└────────────────────────────────────────────────────────┘
            ↓ fetch (JSON)
┌────────────────────────────────────────────────────────┐
│  data/                                                      │
│  ├─ article_index.json   URL → md 文件路径映射            │
│  ├─ counts.json          各刊文章数 / 期数（首页计数）      │
│  ├─ <mag>/meta.json      全部文章元数据                    │
│  └─ <mag>/issues/<年>-<期>.json  按期分片的全文（懒加载）     │
└────────────────────────────────────────────────────────┘
            ↓ 读 articles/
┌────────────────────────────────────────────────────────┐
│  articles/<mag>/<year>_<issue>_<title>.md                  │
│  原始 Markdown 备份（git 体积大但方便人工查阅）              │
└────────────────────────────────────────────────────────┘
            ↓
┌────────────────────────────────────────────────────────┐
│  scripts/scrape_magazines.py  数据采集入口                 │
│  docs/                          架构 / 流程 / 兼容文档       │
└────────────────────────────────────────────────────────┘
```

---

## 2. 前端模块（`assets/js/app.js`）

代码组织为以下区块（按行号大致划分）：

| 行号 | 区块 | 职责 |
| --- | --- | --- |
| 1–68 | 全局配置 | `DATA_VERSION`、`MAGAZINES`、`state`、`FAV_KEY` |
| 68–100 | 辅助函数 | SVG 渲染、按刊状态 `newMagState` / `getMagState` |
| 100–190 | 首页与杂志应用 | 首页计数（`counts.json`）、进入杂志、动态 sticky 偏移量 |
| 190–270 | 数据加载 | 按刊 `meta.json` 按需加载、初始化杂志 |
| 270–334 | 正文分片加载 | `loadIssueData`（按期分片 + 重试）、`listBodyIssues`、`onMagazineDataReady` |
| 334–370 | 收藏 | `localStorage` 持久化、徽标同步 |
| 370–515 | 搜索与高亮 | 标题/作者/正文搜索、**正文按期增量加载**、关键词高亮、分页 |
| 515–640 | 搜索结果渲染 | 结果卡片、正文命中上下文片段 |
| 640–790 | 文章详情 | 优先加载 md 文件，回退到该期分片 |
| 790–1090 | 阅读设置 | 字号 / 行距 / 页宽 / 缩进 / 纸张底色 / 主题 |
| 1090–1165 | 阅读位置 | 进度记录、"上次读到 N%"提示条、"继续阅读" |
| 1165–1280 | 上下篇与相关阅读 | 按（年,期,抓取顺序）排序的邻居计算与渲染 |
| 1280–1340 | 复制链接 / 搜索聚焦 | `copyArticleLink`、`focusSearch` |
| 1340–1482 | 关于页 / 阅读进度 / Markdown 渲染 | 清洗、标题识别、白名单过滤 |
| 1482–1700 | 板块 / 目录 | 板块卡片、目录树形展开 |
| 1700–1790 | 收藏视图 | 跨杂志查找收藏文章（按需补 meta） |
| 1790–1900 | 路由 / 初始化 | hash 路由解析、键盘快捷键、初始化事件绑定 |

### 关键设计

#### 2.1 状态机（state 对象）

```js
const state = {
    currentMag: null,           // 'qs' | 'hqwg' | 'djyj' | null
    magCache: {},                // {qs: {meta, yearData, ...}, ...}
    favorites: [],              // [url, ...]
    currentMode: 'section',     // 'section' | 'catalog' | 'favorites'
    currentArticleUrl: null,
    fullTextReady: false,
    catalogRendered: false,
    isSearching: false,
    searchResults: [],
    currentPage: 1, pageSize: 20,
    readingFs: 20,
    readingTheme: 'auto',
};
```

- 切换杂志时只重置必要字段（`currentMag` / `favorites` 保留）
- `magCache` 字典按需懒填充，三本杂志互相不干扰

#### 2.2 懒加载策略

```
打开首页 → 加载 counts.json（~200 字节）
    ↓
点击杂志 / 进入收藏页 → 加载该刊 meta.json（~0.4–1.3 MB，按需）
    ↓
触发搜索（仅标题/作者）→ 立即返回结果
    ↓
用户切换到"正文搜索"
    ↓
按期增量加载 issues/<年>-<期>.json（每批 6 期），每批加载完立即刷新结果
    ↓
阅读文章 → 加载 articles/<mag>/*.md，失败则回退到该期分片
```

- counts.json：~200 字节，首页首屏只下这一个
- meta.json：单刊 0.4–1.3 MB，进入该刊时必加载
- issues/<年>-<期>.json：单片中位数 ~200 KB、最大 0.31 MB，正文搜索时按期增量加载
- article_index.json：~1.2 MB，文章详情用，单篇 < 50 KB

#### 2.3 数据版本缓存破坏

```js
// app.js 顶部
const DATA_VERSION = '20261016a';
function dataUrl(p) { return p + '?v=' + DATA_VERSION; }
```

`dataUrl()` 给所有数据 URL 加上 `?v=YYYYMMDDx`。当 `index.html` 与 `app.js` 同时升级这个版本号时，浏览器会重新下载所有 `data/*.json`。

#### 2.4 路由（hash）

`#m=qs&a=123` 进入求是第 123 篇文章；`#about` 打开关于页；`#m=qs&s=板块名` 进入板块页。监听 `popstate` 实现前进/后退。

---

## 3. 数据文件结构

### 3.1 `data/article_index.json`

```json
{
  "qs":   { "<url>": "articles/qs/2026_20_xxx.md", ... },
  "hqwg": { "<url>": "articles/hqwg/2026_19_xxx.md", ... },
  "djyj": { "<url>": "articles/djyj/2026_09_xxx.md", ... }
}
```

**键** = 文章原文 URL（与 `meta.json` 的 `u` 字段一致）。
**值** = 仓库内 Markdown 文件相对路径。

### 3.2 `data/<mag>/meta.json`

```json
[
  {
    "t": "文章标题",
    "a": "作者",
    "s": "板块",
    "y": 2026, "i": 20,
    "u": "https://...",
    "h": 1
  },
  ...
]
```

**数组**（不是字典），按抓取时间顺序追加。

### 3.3 `data/<mag>/issues/<年>-<期>.json`

```json
{
  "<url>": "# 标题\n\n正文段落 1\n\n...",
  "<url>": "..."
}
```

**字典**，键 = URL，值 = Markdown 文本。
按**期**拆分（单片 ~200 KB，最大 0.31 KB 级），文件名 `<年>-<期>.json`、期号不补零。

> 2026-10 之前正文按年存放于 `data/<mag>/years/YYYY.json`（单文件 4–18 MB）。
> `scripts/rebuild_data.py` 已把全部正文重建为分片，并丢弃了 `meta.json` 里
> 找不到对应文章的**不可达条目**（历史跨刊污染 + http/https 协议变体重复）。

### 3.4 `data/counts.json`

```json
{"qs":{"articles":3402,"issues":188},"hqwg":{"articles":2265,"issues":164},"djyj":{"articles":1748,"issues":71}}
```

首页只需要三个数字。为此单独准备了这个 ~200 字节的小文件，
避免为了计数下载合计 1.3 MB 的三份 `meta.json`。
抓取脚本每次跑完会自动刷新，也可用 `python scripts/scrape_magazines.py --counts` 离线重建。

### 3.5 `articles/<mag>/<year>_<issue>_<title>.md`

文件命名规则：`年_期号_标题（≤60字符，去除特殊符号）.md`。
**重名时**追加 `_<index>` 后缀。

---

## 4. CSS 架构（`assets/css/style.css`）

### 4.1 关键设计

- **移动优先**：默认样式对应手机屏（≤600px），用 `@media (min-width: 768px)` 切换到桌面布局
- **CSS 变量**：所有主题色用 `:root` 定义变量（`--primary`、`--bg`、`--text`），切换主题只需改变量
- **Chrome 69 兼容**：底部专门有 `/* Chrome 69 Gap Fallback */` 区块，为 flex 容器的 `gap` 属性提供 `> * + *` margin 兼容写法

### 4.2 主要区块

| 行号 | 区块 | 职责 |
| --- | --- | --- |
| 1–100 | Design Tokens | `:root` 变量 + Dark Mode |
| 100–180 | 布局 | 页面结构、桌面 / 移动切换 |
| 180–320 | 首页 | 杂志卡片、标题、按钮 |
| 320–700 | 杂志应用 | 搜索栏、过滤器、结果列表、收藏 |
| 700–900 | 板块 / 目录 | 板块卡片、目录树 |
| 900–1100 | 文章页 | 进度环、字号、主题切换 |
| 1100–1500 | 关于页 | 简介、链接、版权 |
| 1500–1800 | 桌面响应式 | `@media (min-width: 768px)` / `(min-width: 1024px)` |
| 末尾 | Chrome 69 Fallback | `gap`、`aspect-ratio` 兜底 |

---

## 5. 部署架构

### 5.1 Cloudflare Pages

```
GitHub repo (main branch)
       ↓ push
Cloudflare Pages 自动构建（无构建步骤）
       ↓
CDN 边缘节点（全球 200+ 节点）
       ↓ HTTPS
用户浏览器
```

### 5.2 缓存策略（`_headers`）

```text
/data/*               Cache-Control: public, max-age=31536000, immutable
/assets/*             Cache-Control: public, max-age=0, must-revalidate
/*.html               Cache-Control: public, max-age=0, must-revalidate
/sw.js                Cache-Control: public, max-age=0, must-revalidate
/manifest.webmanifest Cache-Control: public, max-age=0, must-revalidate
```

- `data/` 一年不可变，URL 携带 `?v=YYYYMMDDx` 触发更新
- `assets/` 必须 revalidate，避免用户看到旧版 CSS/JS
- HTML 永不缓存，确保 index.html 立即生效
- `sw.js` 必须 revalidate，否则浏览器拿不到新版 SW，离线缓存会永远停在旧版
- `manifest.webmanifest` 同理，否则桌面安装信息不更新

### 5.3 Service Worker（`sw.js`）

自 2026-10-30 起引入，提供离线阅读能力。Service Worker 自 Chrome 40+ 支持，
Chrome 69 完全可用（Chrome 72 前不认 manifest，只影响"安装到桌面"，不影响离线阅读）。

**版本绑定**：注册时用 `sw.js?v=<DATA_VERSION>`，SW 从自身 URL 的 `?v=` 取版本号。
版本一变 → 浏览器装上新 SW → 新 SW 的 `activate` 清掉旧版本的外壳与数据缓存，
保证不会把上一期的 meta / 索引当成本期数据用。

**三套缓存**：

| 缓存名 | 内容 | 键规则 | 跨版本 |
| --- | --- | --- | --- |
| `djyj-shell-<v>` | index.html、CSS/JS、manifest、图标、封面、counts | index/图片按路径；CSS/JS/manifest/counts 按完整 URL（含 `?v=`） | ❌ 随版本清空 |
| `djyj-rt-<v>` | 各刊 meta、article_index、正文分片 | meta/索引按完整 URL；分片按路径 | ❌ 随版本清空 |
| `djyj-md` | `articles/**/*.md` 正文 | 按路径 | ✅ 永久保留（正文不可变） |

**分流策略**：

- 导航请求（`request.mode === 'navigate'`）：**network-first**，断网回落缓存的 `index.html`
- 其余同源 GET：**cache-first**，运行时写入对应缓存
- 跨域请求不接管

**容量控制**：运行时缓存 `MAX_RT_ENTRIES = 200`、`MAX_MD_ENTRIES = 250`，超出后按插入顺序 FIFO 淘汰。

**内容类型守卫**：Cloudflare Pages 的 SPA 回退会把 404 变成 200 的 `index.html`。
若照单全收，HTML 会被缓存到 `.json` / `.md` 的键上，文章页就会把整页 HTML 当正文渲染。
因此写入缓存前校验 `content-type`：`.json` 必须是 JSON，且不能是 `text/html`。

**更新提示**：页面发现新 SW 装好且已有旧 SW 在控制时，底部弹出"新版本已就绪，点击刷新"。

### 5.4 域名配置

- 默认域：`xxx.pages.dev`
- 自定义域：在 Cloudflare Pages 设置中加 CNAME，自动签发 SSL
- DNS：推荐使用 Cloudflare 托管，自动启用 HTTP/2、HTTP/3、Brotli

---

## 6. 抓取脚本架构（`scripts/scrape_magazines.py`）

### 6.1 模块结构

```
MAGAZINES 配置字典
    ↓
--check 模式
├─ get_latest_issue(mag)         网络检查
├─ get_local_latest_issue(mag)   本地 meta 比较
└─ 输出"本地 vs 官网"对比表

抓取模式
├─ find_catalog_url(mag, year, issue)
├─ find_year_aggregate_url(mag, year)        # 新增
├─ find_issue_url_in_year(mag, year, issue)  # 新增
├─ parse_qs_hqwg_catalog / parse_djyj_catalog
├─ fetch_article_content(url, mag_type)
├─ process_magazine(mag, year, issue)         # 协调：写 meta/issues/index + 刷新 counts
└─ download_cover(mag, year, issue)           # 写 assets/img/

main()  CLI 调度
```

### 6.2 关键模块详解

#### 6.2.1 目录页解析

| 杂志 | 解析函数 | 关键规则 |
| --- | --- | --- |
| 求是 / 红旗文稿 | `parse_qs_hqwg_catalog` | 找 `#detailContent` div，遍历 `<p>`，识别红色加粗的板块标题（`color: #ba372a`），提取 `<a href>` 链接 |
| 党建研究 | `parse_djyj_catalog` | 遍历 `<li>`，识别 `.cur` 板块，提取 `.shtml` 链接 |

#### 6.2.2 元素到 Markdown

`element_to_md(el, base_url)` 递归转换：

- `<p>` → 段落（识别居中/居右样式）
- `<strong>`, `<b>` → `**bold**`
- `<em>`, `<i>` → `*italic*`
- `<img>` → `![alt](src)`
- `<a>` → 保留文本（链接由前端渲染时再处理）
- `<h1>`–`<h6>` → `# Title`
- `<br>` → `\n`

#### 6.2.3 关键辅助函数

- `clean_text(text)`：移除"视频代码""repaste.body.begin"等模板残留
- `sanitize_filename(name)`：去除 `<>:"/\\|?*`、空格，截断 60 字符
- `element_to_md`：递归转换，识别段落对齐

---

## 7. 性能指标

| 指标 | 数值 |
| --- | --- |
| 首次加载（仅首页） | ~2 MB（HTML + meta + CSS + JS） |
| 搜索响应 | < 100 ms（仅标题） |
| 搜索响应（正文） | 1–2 s（首次 + 分片按期增量加载） |
| 文章渲染 | < 200 ms（md 加载 + 渲染） |
| Lighthouse 性能分 | 90+（桌面），80+（移动） |
| 总数据量 | ~150 MB（不含 articles/ 约 8 MB） |

---

## 8. 安全 / 隐私

- 无后端，无用户数据收集
- 收藏功能使用 `localStorage`（用户本地，不上传）
- 静态资源通过 HTTPS 提供
- 无第三方追踪 / 分析脚本
- 搜索行为完全在浏览器端，不发送到任何服务器

---

## 9. 未来规划

- [ ] PWA：service-worker 离线阅读
- [ ] 文章导出 PDF
- [ ] 阅读历史记录
- [ ] 多语言切换（繁/英文）
- [ ] 自动检测新刊的 GitHub Action（每周 cron）
- [ ] 同主题文章聚合（"同一议题的所有文章"）
- [ ] 跨期同主题对比视图
- [ ] 高亮笔记（基于 localStorage）

---

## 10. 变更日志

- 2026-10-30：新增 PWA / 离线阅读（`sw.js`、`manifest.webmanifest`、图标），正文数据改为按期分片
- 2026-10-16：文档体系重构，新增 `docs/` 目录
- 2026-09-27：完成 Chrome 69 兼容性适配
- 2026-09-27：遴选备考指南新增三大专题
- 2026-09：扩展为三刊（《求是》《党建研究》《红旗文稿》）
- 2025：原版党建研究检索系统
