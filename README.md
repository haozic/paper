# 党内刊物检索系统

收录《求是》《红旗文稿》《党建研究》三本中央级党刊，**2026 年 10 月** 在本仓库的 `data/` 目录下已累计 **7400+ 篇文章 / 104 MB** 的全文数据，提供**全文搜索、板块分类、目录浏览、文章收藏、自适应阅读**等功能。

> 配套的备考资料请见 [`linxuan-beikao-zhinan/`](./linxuan-beikao-zhinan/linxuan-beikao-zhinan.html) 子页。
>
> 想抓取最新一期？请直接跳到 [`scripts/README.md`](./scripts/README.md)。

---

## 目录

- [项目特点](#项目特点)
- [数据范围](#数据范围)
- [项目结构](#项目结构)
- [更新文章：抓取脚本使用流程](#更新文章抓取脚本使用流程)
- [本地开发](#本地开发)
- [部署到 GitHub + Cloudflare Pages](#部署到-github--cloudflare-pages)
- [浏览器兼容性](#浏览器兼容性)
- [性能与缓存策略](#性能与缓存策略)
- [常见问题](#常见问题)
- [更多文档](#更多文档)

---

## 项目特点

| 功能 | 说明 |
| --- | --- |
| 三刊合一 | 求是 / 党建研究 / 红旗文稿 统一在一个站点浏览、检索 |
| 全文搜索 | 支持标题 / 作者 / 正文 / 组合多范围，含搜索词高亮 |
| 板块 / 目录 | 板块统计 + 按"年→期→板块"展开的目录树 |
| 文章收藏 | 基于 `localStorage`（键 `djyj_favorites`），可导出 JSON |
| 阅读设置 | 字号（16/20/24/28）、白天/夜晚/跟随系统主题 |
| 移动适配 | 移动端底部 tab + 桌面端顶部 tab，自适应响应式 |
| Markdown 渲染 | 自动渲染粗体、标题、链接、图片、对齐，保留版式 |
| 跨刊跳转 | 收藏的文章跨杂志自动切换 |
| Chrome 69 兼容 | 站点对 2018 年的 Chrome 69 仍可正常使用 |

---

## 数据范围

| 杂志 | 时间跨度 | 文章数 | 最新一期 |
| --- | --- | --- | --- |
| 《求是》 | 2019 年第 1 期 — 2026 年第 20 期 | 3400+ | 2026-10-15 |
| 《红旗文稿》 | 2020 年第 1 期 — 2026 年第 20 期 | 2200+ | 2026-10-25 |
| 《党建研究》 | 2020 年第 12 期 — 2026 年第 10 期 | 1700+ | 2026-10-10 |

> 期数与文章数会随定期抓取持续增长，请以 `index.html` 的"关于本站 → 数据更新"区块为准。

---

## 项目结构

```
e:\cursor\xgkt\djyj
├── index.html                      # 入口：首页 + 杂志应用 + 文章阅读
├── README.md                       # 你正在阅读的文件
├── wrangler.jsonc                  # Cloudflare Pages 部署配置
├── _headers                        # 自定义 HTTP 头（缓存策略）
├── .nojekyll                       # 禁用 GitHub Pages 的 Jekyll 处理
├── .gitignore
│
├── assets/
│   ├── css/
│   │   └── style.css               # 移动优先响应式样式（含 Chrome 69 兼容补丁）
│   ├── js/
│   │   └── app.js                  # 核心逻辑（搜索/收藏/懒加载/路由）
│   └── img/                        # 杂志封面图（cover_qs/hqwg/djyj.jpg）
│
├── data/                           # ⭐ 网站运行依赖
│   ├── article_index.json          # URL → articles/.../*.md 路径映射
│   ├── counts.json                 # 首页计数：各刊文章数 / 期数（~200 字节）
│   ├── meta.json                   # 党建研究全部文章元数据（标题/作者/期号/URL）
│   ├── issues/2020-12..2026-10.json# 党建研究按期分片的正文（懒加载）
│   ├── qs/
│   │   ├── meta.json               # 求是全部文章元数据
│   │   └── issues/2019-1..2026-20.json # 求是按期分片的正文
│   └── hqwg/
│       ├── meta.json               # 红旗文稿全部文章元数据
│       └── issues/2020-1..2026-20.json # 红旗文稿按期分片的正文
│
├── articles/                       # 📦 原始 Markdown 备份（git 体积大但方便人工查阅）
│   ├── djyj/                       # 党建研究，命名格式：YYYY_NN_<标题>.md
│   ├── qs/                         # 求是
│   └── hqwg/                       # 红旗文稿
│
├── linxuan-beikao-zhinan/          # 🎓 遴选备考专题（独立 HTML 子页）
│   └── linxuan-beikao-zhinan.html
│
├── scripts/                        # 🛠 抓取与运维脚本
│   ├── scrape_magazines.py         # 三刊抓取主脚本（详见 scripts/README.md）
│   ├── rebuild_data.py             # 正文重分片（years/<年> → issues/<年>-<期>）+ 去污染 + 索引瘦身
│   ├── check_data.py               # 数据体检：期号覆盖 / 重复 / 正文缺失 / 分片与 counts 一致性
│   ├── check_compat.py             # Chrome 69 兼容性体检：特性黑名单 + flex gap 兜底检查
│   ├── repair_empty_urls.py        # 修复历史遗留的空 URL 条目
│   └── README.md                   # 脚本使用、字段、URL 规律、踩坑记录
│
└── docs/                           # 📚 架构、流程、踩坑文档
    ├── ARCHITECTURE.md             # 系统架构、模块划分、数据流
    ├── UPDATE_FLOW.md              # 每月更新文章的标准操作流程
    ├── CHROME69_COMPAT.md          # 浏览器兼容性的处理清单
    └── UX_MODERNIZATION.md         # 阅读体验现代化与舒适度优化建议
```

> **重要**：`data/` 是网站运行的**唯一依赖**。`articles/` 仅作原始备份，网站运行时只通过 `article_index.json` 指向它。如果你只需要把站点跑起来，不关心备份，可以 `git rm -r articles/` 后提交，仓库瞬间瘦身到 8 MB。

---

## 更新文章：抓取脚本使用流程

完整说明、命令行清单、字段含义、URL 规律、踩坑记录见 [`scripts/README.md`](./scripts/README.md)。这里给出**最短流程**：

```bash
# 0. 进入项目根目录
cd e:\cursor\xgkt\djyj

# 1. 查看哪本杂志有新刊
python scripts\scrape_magazines.py --check

# 2. 抓取指定期号（自动定位目录页、自动下载封面）
python scripts\scrape_magazines.py qs 2026 21
python scripts\scrape_magazines.py hqwg 2026 20
python scripts\scrape_magazines.py djyj 2026 10

# 3. 同步 index.html 的"数据更新"区块（修改日期 + 各刊期号范围）
# 4. 把 index.html / assets/css/style.css / assets/js/app.js 中的 ?v=YYYYMMDDx 同步升级
#    同时把 assets/js/app.js 顶部的 DATA_VERSION 常量一并升级

# 5. 提交并推送
git add -A
git commit -m "更新求是2026年第21期、红旗文稿2026年第20期"
git push origin main
```

> **缓存破坏三件套**：`index.html` 的 `?v=`、`app.js` 的 `?v=`、`DATA_VERSION` 常量。这三个值必须同步改动，否则用户会看到旧版（因为 CSS/JS/JSON 都用 `immutable` 缓存）。

---

## 本地开发

```bash
cd e:\cursor\xgkt\djyj
python -m http.server 8765
# 浏览器打开 http://localhost:8765/
```

也可以用任何静态服务器（`npx serve .`、`php -S localhost:8000` 等）。

> **不要直接 `file://` 打开 `index.html`**：浏览器对 `file://` 协议下的 `fetch()` 有限制，跨域读取 JSON 会失败。务必通过 HTTP 服务访问。

---

## 部署到 GitHub + Cloudflare Pages

### 第一步：上传到 GitHub

```bash
cd e:\cursor\xgkt\djyj
git init                       # 如果尚未初始化
git add .
git commit -m "init: 党内刊物检索系统"
git branch -M main
git remote add origin https://github.com/你的用户名/djyj.git
git push -u origin main
```

> **关于 `articles/`**：`articles/` 文件夹有 7000+ 个 Markdown 文件，git 推送较慢。如果不需要保留原始备份（线上站点并不依赖它），可以在 `.gitignore` 中加 `articles/`，`git rm -r --cached articles/` 后再推送。`data/` 仍可保留，因为文章正文也存了 `data/<mag>/issues/<年>-<期>.json` 分片里。

### 第二步：Cloudflare Pages 部署

#### 方式 A（推荐）：连接 GitHub 自动部署

1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com)
2. **Workers & Pages** → **创建应用程序** → **Pages** → **连接到 Git**
3. 选择仓库 `djyj`，配置：
   - **框架预设**：None
   - **构建命令**：留空（纯静态站点）
   - **构建输出目录**：`/`（仓库根）
4. **保存并部署**，等待 1-2 分钟获得 `xxx.pages.dev` 域名

#### 方式 B：Wrangler CLI 手动部署

```bash
npm install -g wrangler
wrangler login
wrangler pages deploy . --project-name=djyj
```

> `wrangler.jsonc` 中已经配置了 `assets.directory = "."`，无需额外参数。

### 第三步：绑定自定义域名（可选）

1. Cloudflare Pages 项目 → **自定义域** → 添加域名
2. 按提示配置 CNAME 记录
3. Cloudflare 自动签发 SSL 证书

---

## 浏览器兼容性

| 浏览器 | 最低支持版本 | 备注 |
| --- | --- | --- |
| Chrome / Edge | 69+（2018 年） | 已通过专门的兼容补丁支持 |
| Firefox | 62+ | |
| Safari | 12+ | |
| iOS Safari | 12+ | 含底部安全区适配 |
| Android Chrome | 90+ | |

**Chrome 69 兼容**采用渐进增强（`@supports` 兜底），现代浏览器走原生路径：
- `oklch()` 颜色 → hex
- `aspect-ratio` → `@supports not (aspect-ratio: …)` 里的 `padding-top` 兼容写法
- `:has()` 选择器 → `.checked` 镜像类 + JS 同步
- flex `gap` → `@supports` 兜底块里的 `> * + *` margin（现代浏览器仍走原生 `gap`）
- `inset` 简写 → `top/right/bottom/left` 长写兜底
- `accent-color` / `appearance` → 全浏览器自绘表单控件
- JS 可选链 `?.` → 改写为 ES5 兼容写法

改动 CSS / JS 后请跑一次体检：

```bash
python scripts/check_compat.py
```

详见 [`docs/CHROME69_COMPAT.md`](./docs/CHROME69_COMPAT.md)。

---

## 性能与缓存策略

### 缓存配置（`_headers`）

| 路径 | 缓存策略 | 原因 |
| --- | --- | --- |
| `/data/*` | `max-age=31536000, immutable` | 数据文件很大，URL 携带 `?v=YYYYMMDDx` 版本号，更新即失效 |
| `/assets/*` | `max-age=0, must-revalidate` | CSS/JS 修改后必须立即生效 |
| `/*.html` | `max-age=0, must-revalidate` | 入口文件，确保更新及时 |

### 关键性能数据

- **总数据量**：约 190 MB（data 目录 104 MB + 文章 md 备份 85 MB）
- **首次访问**：仅下载首页 HTML + meta.json（~1.5 MB）+ CSS/JS（约 100 KB）
- **搜索体验**：先搜标题（立即响应），正文搜索按需加载当年份数据
- **阅读文章**：通过 `article_index.json` 直接定位 md 文件，单文件加载 < 50 KB

### SEO & 性能

- 站点为纯静态 HTML，**无构建步骤**，可直接部署
- 单页应用（SPA-like）通过 History API 实现路由
- 支持 service-worker 离线（未来计划）

---

## 常见问题

#### 1. 浏览器报 `CORS / Mixed Content` 错误

- 用 `http://localhost:8765/` 而不是 `file:///path/to/index.html`
- Cloudflare Pages 默认 HTTPS，不会出现 Mixed Content

#### 2. 修改了数据后看不到新内容

- 检查 `index.html` 和 `app.js` 顶部的 `?v=YYYYMMDDx` 缓存破坏号是否同步更新
- 检查 `app.js` 顶部的 `DATA_VERSION` 常量是否与之一致
- 浏览器**强制刷新**（Ctrl+Shift+R / Cmd+Shift+R）

#### 3. 抓取脚本被反爬拦截

求是/红旗文稿的目录页不限制访问频率，但请在 `scripts/scrape_magazines.py` 的 `time.sleep(0.5)` 处适当调大（如 1.0）。脚本默认每次请求间隔 0.5 秒。

#### 4. `articles/` 目录太大

- 临时排除：在 `.gitignore` 加 `articles/`，执行 `git rm -r --cached articles/`
- 永久排除：从本地磁盘删除 `articles/`，但保留 `data/<mag>/issues/`（线上站点只依赖 data/）

#### 5. 想自定义主题色

所有主题色都是 CSS 变量，位于 `assets/css/style.css` 的 `:root` 选择器。改一行 `--primary: #...` 即可全站生效。

---

## 更多文档

- [`scripts/README.md`](./scripts/README.md) — 抓取脚本详细使用文档
- [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) — 系统架构、模块划分、数据流
- [`docs/UPDATE_FLOW.md`](./docs/UPDATE_FLOW.md) — 每月更新文章的标准操作流程
- [`docs/CHROME69_COMPAT.md`](./docs/CHROME69_COMPAT.md) — 浏览器兼容性的处理清单
- [`docs/UX_MODERNIZATION.md`](./docs/UX_MODERNIZATION.md) — 阅读体验现代化与舒适度优化建议（排版/导航/性能，含优先级与路线图）
- [`linxuan-beikao-zhinan/`](./linxuan-beikao-zhinan/) — 遴选备考专题页面

---

## 协议

本仓库源代码采用 MIT 协议。所收录文章版权归原作者及出版方（《求是》杂志社、《党建研究》杂志社、《红旗文稿》杂志社）所有，仅供个人学习研究使用。
