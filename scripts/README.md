# 抓取脚本使用文档

`scripts/scrape_magazines.py` 是本项目的数据采集入口，负责把三本中央级党刊（《求是》《党建研究》《红旗文稿》）从官方网站拉取到本地，**同时更新五类数据**：

- `data/<mag>/meta.json` — 文章元数据
- `data/<mag>/issues/<年>-<期>.json` — 文章正文（**按期分片**，2026-10 起）
- `data/counts.json` — 首页计数（各刊文章数 / 期数，约 200 字节）
- `data/article_index.json` — `URL → articles/<mag>/<file>.md` 路径映射
- `assets/img/cover_<mag>.jpg` — 最新一期封面图
- `articles/<mag>/<year>_<issue>_<title>.md` — 原始 Markdown 备份

> 2026-10 之前正文按年存放在 `data/<mag>/years/<year>.json`（单文件 4~18 MB），
> 现已由 `scripts/rebuild_data.py` 一次性重建为按期分片，旧目录已从仓库删除。

---

## 1. 依赖

- Python 3.8+
- 第三方包：`requests`、`beautifulsoup4`
- 标准库：`os`、`re`、`json`、`time`、`sys`、`warnings`

安装依赖：

```bash
pip install requests beautifulsoup4
```

> 脚本自动屏蔽 SSL 警告（`warnings.filterwarnings('ignore')`），不影响功能。

---

## 2. 命令行速查

```bash
# 进入项目根目录
cd e:\cursor\xgkt\djyj

# 检查各杂志最新一期（不抓取，只输出对比）
python scripts\scrape_magazines.py --check

# 仅更新所有杂志的封面图
python scripts\scrape_magazines.py --covers

# 抓取指定期号（可同时抓多本多期，3 个参数为一组）
python scripts\scrape_magazines.py qs 2026 21
python scripts\scrape_magazines.py hqwg 2026 20
python scripts\scrape_magazines.py djyj 2026 10

# 一次抓多本多期
python scripts\scrape_magazines.py qs 2026 21 hqwg 2026 20 djyj 2026 10

# 不带期号时，自动检测最新期并抓取
python scripts\scrape_magazines.py qs
```

参数顺序固定为：`<杂志> <年> <期> [杂志 年 期]...`

合法 `杂志` 取值：`qs` / `hqwg` / `djyj`。

### 2.1 辅助脚本

```bash
# 数据体检：期号覆盖、重复条目、正文缺失、索引一致性（只读）
python scripts\check_data.py

# 体检 + 就地去重（重复条目按 URL 去重）
python scripts\check_data.py --dedup

# 正文数据重建：years/<年>.json → issues/<年>-<期>.json 分片，并丢弃不可达正文
python scripts\rebuild_data.py            # 预演，只报告不写盘
python scripts\rebuild_data.py --apply    # 实际写盘（会重建 issues/ 与 article_index.json）

# 只重建首页计数（离线，不联网）
python scripts\scrape_magazines.py --counts

# 修复历史遗留的"空 URL"条目（默认预览，加 --apply 才写回）
python scripts\repair_empty_urls.py
python scripts\repair_empty_urls.py --apply

# 刷新板块名（只抓目录页，不动正文；默认预演，加 --apply 才写盘）
python scripts\refresh_sections.py
python scripts\refresh_sections.py --apply
python scripts\refresh_sections.py --mag qs --issues 2026-15,2026-20

# 板块名归一（同一栏目被改过名时合并；默认写盘，--check 只体检）
python scripts\canonical_sections.py
python scripts\canonical_sections.py --check

# Chrome 69 兼容性体检（零依赖，有问题返回非 0 退出码）
python scripts\check_compat.py
python scripts\check_compat.py --list

# 体检脚本自身的判定逻辑反向自测（15 条用例）
python scripts\test_check_compat.py

# JS 注释层体检：防"块注释被提前闭合"+ Service Worker 求值冒烟
python scripts\check_js_comments.py
python scripts\check_js_comments.py --no-runtime   # 只跑词法扫描
python scripts\check_js_comments.py --self-test    # 反向自检（8 条用例）

# Service Worker 导航处理体检：防"首页入口打不开"（行为级，4 条用例）
python scripts\check_sw_navigate.py
python scripts\check_sw_navigate.py --list          # 列出用例
python scripts\check_sw_navigate.py --self-test     # 反向自检（2 条用例）

# 备考全书大作文范例字面体检：结构 / 分论点 / 字数 / 重复 / 英文 / Markdown / 乱码 / 体例
python scripts\check_essays.py
python scripts\check_essays.py --self-test    # 反向自检（1 正对照 + 12 条注入用例）

# 面试指南结构与字面体检：章节 / 目录锚点 / 标题层级 / 英文 / 乱码 / 体例 / 重复 / 事实锚点 / 模拟题折叠
python scripts\check_mianshi.py
python scripts\check_mianshi.py --self-test    # 反向自检（1 正对照 + 13 条注入用例 + 1 条例外用例）

# 目录顺序修正：按官网目录页顺序重排 meta（默认预演，加 --apply 才写盘）
python scripts\fix_catalog_order.py
python scripts\fix_catalog_order.py --apply           # 写回 meta.json + data/catalog_order.json
python scripts\fix_catalog_order.py --check           # 离线体检（对照顺序快照，不联网）
python scripts\fix_catalog_order.py --self-test       # 重排逻辑自检（13 条用例，含反向自检）

# 清洗 meta 里被网页页脚污染的"作者"字段（默认预演，加 --apply 才写盘）
python scripts\clean_meta_authors.py
python scripts\clean_meta_authors.py --apply
python scripts\clean_meta_authors.py --self-test

# 重新生成 PWA 图标（需要 Pillow；仅在改图标设计时才用）
python scripts\make_icons.py
```

| 脚本 | 作用 | 何时用 |
| --- | --- | --- |
| `check_data.py` | 体检三刊的 meta / 正文分片 / counts / article_index 一致性 + 目录顺序（对照官网快照） | 每次抓取后；怀疑数据异常时 |
| `rebuild_data.py` | 把正文重分片为 `issues/<年>-<期>.json`，丢弃不可达正文，瘦身 article_index | 迁移到分片布局时；怀疑正文文件过大时 |
| `repair_empty_urls.py` | 修复 `u` 字段为空的条目 | 体检报出空 URL 时 |
| `refresh_sections.py` | 只抓目录页刷新板块名（不重下正文、不重建分片） | 板块页出现"目录/评论"假板块，或整期无板块时 |
| `canonical_sections.py` | 合并"同一栏目被改过名"产生的多张相似卡片（归一表附来源站证据） | 板块页上出现两张长得很像的卡片时 |
| `check_compat.py` | 体检 Chrome 69 兼容性（特性黑名单 + flex gap 兜底缺失） | 改动 CSS / JS 后；详见 [`docs/CHROME69_COMPAT.md`](../docs/CHROME69_COMPAT.md) |
| `test_check_compat.py` | `check_compat.py` 的反向自测（`@supports` 语义、兜底缺失、注释剥离） | 改动 `check_compat.py` 的解析逻辑后 |
| `check_js_comments.py` | 体检 JS 注释层（块注释提前闭合）+ Service Worker 求值冒烟 | 改动任何 `.js` 后；详见 [`docs/CHROME69_COMPAT.md` §3.3](../docs/CHROME69_COMPAT.md) |
| `check_sw_navigate.py` | 体检 SW 的导航处理（跳转 → opaque 过滤、只接管外壳路由、离线回落） | 改动 `sw.js` 后；首页入口打不开时；详见 [`docs/CHROME69_COMPAT.md` §4.10](../docs/CHROME69_COMPAT.md) |
| `check_essays.py` | 体检《备考全书》第十章第六节八篇大作文范例的字面合规（结构 / 分论点同构 / 字数 / 重复段落 / 英文夹杂 / Markdown 残留 / 乱码 / 体例 / 批注数字自证） | 改动大作文范例后；详见 [§9.9](#99-大作文范例字面体检) |
| `check_mianshi.py` | 体检《湖北省直遴选面试指南》的结构与字面合规（章节 / 目录锚点 / 标题层级 / 英文夹杂 / 乱码 / 体例 / 重复段落 / 关键事实锚点） | 改动面试指南正文后；详见 [§9.10](#910-面试指南结构与字面体检) |
| `make_icons.py` | 生成 PWA 图标（192 / 512 / maskable-512 / apple-touch-icon） | 改图标设计时；需要 Pillow |
| `fix_catalog_order.py` | 按官网目录页顺序重排 meta，并把顺序存成 `data/catalog_order.json` 快照 | 站内目录顺序与官网对不上时；新增期次后刷新快照 |
| `clean_meta_authors.py` | 清洗 meta 里被网页页脚（发布时间 / 扫码提示 / 网站声明 / 评论引导）污染的"作者"字段 | 目录里出现长串乱码作者时 |

---

## 3. 杂志数据源

| 杂志 | 目录页 | 抓取方式 |
| --- | --- | --- |
| **求是** | `https://www.qstheory.cn/qs/mulu.htm` | 目录页只列最新一期；目标期需要从 `2026 年汇总页` 反查 |
| **红旗文稿** | `https://www.qstheory.cn/hqwglist/mulu.htm` | 同上 |
| **党建研究** | `https://djyj.12371.cn/01/` | 直接构造 `https://djyj.12371.cn/<年>/<期>/` |

### URL 规律

| 杂志 | 列表页 URL | 文章 URL 模式 |
| --- | --- | --- |
| 求是 / 红旗文稿 | `/mulu.htm` | `https://www.qstheory.cn/YYYYMMDD/<uuid>/c.html` |
| 党建研究 | `/01/` | `https://djyj.12371.cn/YYYY/NN/d_NNNNNN.shtml` 或 `https://djyj.12371.cn/YYYY/NN/<id>.shtml` |

> **求是/红旗文稿**的发布日期通常为每月 1 日与 15 日。求是发布周期是半月刊，红旗文稿也是半月刊。

### 3.1 党建研究的 URL 规律（易踩坑）

| 位置 | 格式 | 示例 |
| --- | --- | --- |
| **目录页** | `/年/期/`（期号**不补零**） | `https://djyj.12371.cn/2026/7/` |
| **文章页** | `/年/期/日/ARTI*.shtml`（期号**补零**） | `https://djyj.12371.cn/2026/07/22/ARTI1784712525709140.shtml` |

> ⚠️ 目录页不补零、文章内链补零，两者不一致。拼目录页 URL 时若写成 `/2026/07/`，12371 会 302 到
> `www.12371.cn/error.html`，表现为"抓取到 0 篇文章"。`find_catalog_url()` 已同时尝试两种写法。

### 3.2 党建研究的部分板块没有单篇链接

目录页中"贯彻落实全国组织部长会议精神""全国党建工作座谈会发言摘登"等板块，只列出**标题和作者**
（纯 `<span>` 文本），没有指向单篇文章的链接——这些文章在官网确实不存在独立页面。

早期解析器把这类条目也写进了 `meta.json`，导致 `u` 字段为空字符串。后果是前端
`meta.findIndex(a => a.u === url)` 用空串匹配，**点任何一条都会打开第一条坏记录（错文章）**。

修复方式（`scripts/repair_empty_urls.py`）：给这类条目分配「该期目录页 + 标题片段」作为唯一地址，
既保证每条可单独寻址、"原文链接"能跳到官网目录页核对，又保持 `h=0` 诚实标注无全文。

---

## 4. 内部数据流

```
              1. 解析 目录页
              https://www.qstheory.cn/qs/mulu.htm  (求是)
              https://djyj.12371.cn/01/          (党建研究)
                          ↓
            ┌──────────────────────────────┐
            │  find_latest_issue()          │   只看最新一期
            │  find_year_aggregate_url()    │   找"2026年"汇总页
            │  find_issue_url_in_year()      │   汇总页中匹配"第N期"
            └──────────────────────────────┘
                          ↓
              2. 解析 目标期目录
              提取 标题 / 作者 / 板块 / URL
                          ↓
              3. 逐篇抓取正文
              复用 process_magazine() 流程
                          ↓
              4. 写入数据文件
              ├─ data/<mag>/meta.json                    (追加)
              ├─ data/<mag>/issues/<年>-<期>.json         (按期分片，写入本期)
              ├─ data/article_index.json                 (追加)
              ├─ data/counts.json                        (抓完自动刷新)
              └─ articles/<mag>/<year>_<issue>_<title>.md
                          ↓
              5. 下载封面图
              assets/img/cover_<mag>.jpg
```

---

## 5. meta.json 字段约定

每篇文章在 `data/<mag>/meta.json` 里形如：

```json
{
  "t": "文章标题",
  "a": "作者名（多作者用"、"分隔）",
  "s": "板块名（如"本刊评论员""要论""关注"等）",
  "y": 2026,
  "i": 20,
  "u": "https://www.qstheory.cn/20261015/.../c.html",
  "h": 1
}
```

| 字段 | 含义 | 示例 |
| --- | --- | --- |
| `t` | title，标题 | `"以更高标准、更实举措推进全面从严治党"` |
| `a` | author，作者 | `"习近平"` 或 `"本刊编辑部"` 或 `"陈家喜"` |
| `s` | section，板块 | `"要论"`, `"关注"`, `"本刊评论员"` |
| `y` | year，年份 | `2026` |
| `i` | issue，期号 | `20` |
| `u` | url，原文 URL | `https://www.qstheory.cn/.../c.html` |
| `h` | has-full，是否抓到正文 | `1` = 抓到了；`0` = 仅元数据，无正文 |

> `h=0` 的文章主要出现在"目录页有但正文页 404"的边缘情况。网站搜索会列出它们，但点击进入会提示"该文章无全文内容"。

---

## 6. issues/<年>-<期>.json 字段约定

`data/qs/issues/2026-20.json` 是 `{URL: 正文 Markdown}` 的纯字典：

```json
{
  "https://www.qstheory.cn/20261015/.../c.html": "# 标题\n\n正文段落 1\n\n正文段落 2\n\n..."
}
```

- 键：原文 URL（与 `meta.json` 的 `u` 字段一一对应）
- 值：抓取后清洗的 Markdown 文本
- 文件名：`<年>-<期>.json`，期号不补零（如 `2026-20.json`、`2021-1.json`）

**为什么按期分片**：按年拆分时 `data/years/2026.json` 单文件达 18.5 MB，正文搜索必须整年整年地下；
按期分片后单片中位数约 200 KB，最大 0.31 MB，正文搜索可以**按期增量加载**，且能边下边出结果。

**懒加载逻辑**（前端 `assets/js/app.js`）：

| 场景 | 下载内容 | 体量 |
| --- | --- | --- |
| 打开首页 | `data/counts.json` | ~200 字节 |
| 进入某本杂志 / 收藏页 | 该刊 `meta.json` | ~0.4~1.3 MB |
| 切换到"正文搜索" | 对应期号的分片，每批 6 期 | 每批约 1.2 MB |
| 点开单篇文章 | `articles/<mag>/*.md`（`article_index.json` 里的路径），失败则回退到该期分片 | 单篇 md |

分片里**不再保留不可达正文**：键在对应 `meta.json` 里找不到同名文章的条目（历史污染、
http/https 协议变体重复）已在 `rebuild_data.py` 重建时丢弃。

---

## 7. article_index.json 字段约定

`data/article_index.json` 是 `{mag: {url: relpath}}` 的双层字典：

```json
{
  "qs": {
    "https://www.qstheory.cn/.../c.html": "articles/qs/2026_20_以更高标准、更实举措推进全面从严治党.md"
  },
  "hqwg": { ... },
  "djyj": { ... }
}
```

- 用于**单篇加载**的 md 文件路径
- 文章详情页直接 `fetch(articles/qs/2026_20_xxx.md)`，避免把全量正文塞进分片文件
- 2026-10 起已重建：只保留 `meta.json` 里能寻址到的条目（13975 → 7086 条）

> 如果把 `articles/` 从仓库删除，只需要保证 `data/<mag>/issues/<年>-<期>.json` 里仍有正文（站点会自动回退到该数据源渲染文章）。

---

## 8. 关键函数清单

| 函数 | 位置 | 作用 |
| --- | --- | --- |
| `MAGAZINES` | 顶部 | 三本杂志的配置字典（catalog_url / meta_path / issues_path / articles_dir / cover_path） |
| `clean_text(text)` | 工具 | 清洗抓取后残留的"视频代码""repaste.body.begin"等模板字符串 |
| `element_to_md(el, base_url)` | 工具 | 把 BeautifulSoup 元素递归转 Markdown |
| `get_latest_issue(mag_key)` | 检查 | 解析目录页找出最新一期号 |
| `get_local_latest_issue(mag_key)` | 检查 | 从本地 meta.json 找出最新期号 |
| `check_updates()` | 检查 | 输出"本地 vs 官网"对比表 |
| `find_catalog_url(mag_key, year, issue)` | 抓取 | 找到目录页 URL（求是/红旗文稿只返回最新期，党建研究直接拼接） |
| `find_year_aggregate_url(mag_key, year)` | 抓取 | 从 `mulu.htm` 解析"XXXX年"汇总页 |
| `find_issue_url_in_year(mag_key, year, issue)` | 抓取 | 在汇总页中匹配"第N期"找到目标期 URL |
| `parse_qs_hqwg_catalog(url, year, issue)` | 抓取 | 解析求是/红旗文稿目录页，提取文章列表 |
| `parse_djyj_catalog(url, year, issue)` | 抓取 | 解析党建研究目录页，提取文章列表 |
| `fetch_article_content(url, mag_type)` | 抓取 | 抓取单篇文章正文并清洗 |
| `download_cover(mag_key, year, issue)` | 抓取 | 下载最新一期封面图到 `assets/img/` |
| `process_magazine(mag_key, year, issue)` | 抓取 | 单期完整流程：找目录→解析→抓取→写文件 |
| `main()` | 入口 | CLI 调度：解析 argv、分发到对应处理函数 |

---

## 9. 常见问题与踩坑记录

### 9.1 报错：`find_catalog_url` 拿不到目标期

**原因**：求是/红旗文稿的 `mulu.htm` 只展示最新一期（如 2026 年第 20 期）。如果你想抓 19 期，`mulu.htm` 不会给直链。

**自动修复**（脚本已自带）：当 `process_magazine` 检测到目标期号 < 最新期号时，会调用 `find_issue_url_in_year` 从"2026 年汇总页"中查找。

**手动绕过**：如果汇总页也找不到（例如求是 2024 之前的期数），可以：

1. 在浏览器中打开目标期的某一篇已知文章，URL 形如 `https://www.qstheory.cn/YYYYMMDD/<id>/c.html`
2. 把 YYYYMMDD 部分（如 20260915）替换到 `process_magazine` 中
3. 或者直接修改 `find_issue_url_in_year` 的正则

### 9.2 报错：求是/红旗文稿抓取到 0 篇文章

**可能原因**：

- 目标期还没出版 → 用 `--check` 确认官网最新期
- 反爬 → 调大 `time.sleep(0.5)` 到 `1.0`
- 目录页 HTML 结构变化 → 在浏览器中打开目录页，对比 `parse_qs_hqwg_catalog` 中的解析规则

### 9.3 报错：`ConnectionError` / `Timeout`

求是/红旗文稿服务器偶尔会 503。建议：

- 重试 3-5 次
- 加 `requests.adapters.HTTPAdapter` 配 `Retry`
- 错峰抓取（避开每月 1 日、15 日的发布高峰）

### 9.4 党建研究部分文章 `h=0`（无正文）

**原因**：目录页有链接，但点进去是聚合页或视频页，没有正文。

**处理**：`h=0` 不影响整体功能。网站会自动用"该文章无全文内容"占位，避免空白。

### 9.5 标题里带"——"或括号被截断

**自动处理**：`parse_qs_hqwg_catalog` 已识别 `——` 开头作为副标题合并到上一条；`(...)` 等会保留为标题一部分。

### 9.6 想增量更新到现有 meta.json

**当前实现**：`process_magazine` 是**追加**（`meta.append`）而不是覆盖。已存在的 URL 会重复。如要严格去重，可以在 `process_magazine` 末尾加：

```python
seen = set()
meta_uniq = []
for a in meta:
    if a['u'] not in seen:
        seen.add(a['u'])
        meta_uniq.append(a)
meta = meta_uniq
```

### 9.7 板块名是"目 录"/"评论"，或某几期整期没有板块

**2026-10-30 查清的三个根因**（都属于**数据层**，不是前端）：

1. **"目 录"是抓取脚本的兜底值**，不是求是真栏目。旧版目录页用
   `<font color="maroon">目 录</font>` 标目录页自己的标题，解析器只认
   `<span style="color: #ba372a">`；且比较"目 录"时只按半角空格，
   页面实际有半角 / 全角 U+3000 / nbsp 三种写法 → 全被当成了板块。
2. **"评论"是微博分享控件的产物**：老版本把文章页的
   `<div class="fs-pinglun"><span class="big">评论</span>` 当成了栏目。
3. **`parse_qs_hqwg_catalog` 的三个老 bug**（从首次入库就有）：
   - `href.startswith('http')` 过滤掉协议相对 URL（`//www.qstheory.cn/...`）
     → 旧期目录页解析出 **0 篇**；
   - `f'/{year}' in href` 年份过滤 → 2026 年第 1 期（发布于 2025-12-31）
     **整期 0 篇**；
   - "目 录"比较未归一化 → 被当成了板块。

**处理**：

```bash
python scripts\refresh_sections.py            # 预演（只抓目录页）
python scripts\refresh_sections.py --apply    # 写盘
```

板块名只存在 `meta.json` 的 `s` 字段里，**不需要重抓 85 MB 正文、也不需要重建分片**。

**原则**：只保留来源站目录页能证实的板块名，证实不了的一律清空（前端归入"未分栏目"，
且不显示为板块名）；目录页抓不到就整期不动。

**边界**：求是 2019–2025 年 14 期（158 期）的栏目信息**在来源站已彻底下线**
（实时目录页里 `│` = 0、红色标题 = 0），这批文章只能进"未分栏目"。

### 9.8 首页底部的"备考指南/备考全书"打不开（空白、没有样式）

**2026-10-30 用户报障查清的根因**（属于 **Service Worker 层**，不是文件缺失、
也不是部署问题 —— 线上返回的字节与本地文件 MD5 完全一致）：

1. Cloudflare Workers Static Assets 的 `html_handling` 会把 `.html` 路径
   **308 重定向**到无扩展名路径（`/x/x.html` → `/x/x`）。
2. SW 接管导航时，旧代码直接 `fetch(request)`。而在 Service Worker 里 fetch
   一个 mode 为 `navigate` 的请求，**只要该地址发生跳转**，Fetch 规范就会把
   响应过滤成 **opaque**：`status=0、ok=false、redirected=false`
   （浏览器实测诊断输出：`BRANCH=not-ok / response.status=0 / response.redirected=false`）。
3. 旧代码把 `!response.ok` 一律当成"断网"，于是回落到缓存的 `index.html`，
   把**首页 HTML 塞到了子页面地址上**。
4. `index.html` 的 `assets/css`、`assets/js` 都是**相对路径**，在
   `/linxuan-beikao-zhinan/` 目录下全部 404 —— 样式没了、app 没启动、
   body 几乎是空的 → 用户看到的就是**"打开了新页面，但空白、没有样式"**。
5. 缓存里查不到 `index.html` 时 SW 返回 `Response.error()`，
   浏览器直接 `net::ERR_FAILED`（`chrome-error://chromewebdata/`）。

**处理**：

```bash
python scripts\check_sw_navigate.py          # 行为级体检（4 条用例）
python scripts\check_sw_navigate.py --self-test   # 反向自检
```

**两条硬规则**（已写进 `sw.js` 注释）：

- SW 里**不要**用 navigate 模式的请求去 `fetch`。要抓正文就用
  `new Request(url, { mode: 'same-origin' })`，跳转才会被正常跟随。
- SW **只接管应用外壳路由**（`/` 与 `/index.html`）；备考指南这类独立静态页
  直接放行给网络，浏览器自己处理 308 重定向。

**排查这类"线上空白"问题的通用顺序**：先比对线上与本地的字节
（`curl -o 文件` + MD5），字节一致就说明**不是服务端问题**，再往客户端查
（SW / 缓存 / 相对路径 404）。

---

### 9.9 大作文范例字面体检

《荆楚遴选备考全书》第十章第六节「预测热点大作文完整范例（8篇）」是手写内容，
篇幅大、句式重复，最容易出**低级文字差错**——写作过程中真实出现过整段复制、
英文夹杂、乱码、Markdown 标记残留四类问题。它们都不会让页面报错，只会让
读者看到病句。

```bash
python scripts\check_essays.py                 # 体检（9 类规则 E1–E9）
python scripts\check_essays.py --self-test     # 反向自检（1 正对照 + 12 条注入用例）
```

规则一览：

| 编号 | 检查项 | 抓的是哪类事故 |
| --- | --- | --- |
| E1 | 结构完整（八篇齐全，每篇有【审题立意】/【参考范文】/ 亮点批注） | 小节被截断、标签写错 |
| E2 | 每篇恰好三个分论点，且以"X"领起同构 | 分论点漏写、句式不统一 |
| E3 | 每篇正文 ≥ 900 字 | 只有提纲没有成文 |
| E4 | 同一篇内无完全重复的正文段落 | **整段复制**（真实发生过） |
| E5 | 无未授权英文单词 | **英文夹杂**（fancy / eVTOL 等） |
| E6 | 无 `**` / `__` 残留 | **Markdown 标记**（纯 HTML 不渲染，会露出星号） |
| E7 | 无替换字符 / 非法控制字符 / 中英粘连 | **乱码**、中文里粘进英文片段 |
| E8 | 无感叹号、无网络用语 | 口语化、体例不符 |
| E9 | 亮点批注里声明的「嵌入 N 处」必须与所列清单条目数一致 | 自己写了个对不上的数字 |

**反向自检必须自带鉴别力**：脚本会先搭一套结构合规的八篇骨架（正对照，必须零错误），
再逐条注入事故写法，并要求**命中指定的规则编号**。只断言"报错了"是不够的——
那样会因为别的规则先报错而假通过。

> 写完正文后，**渲染成图片逐张目检**，文字抽取和单元测试都不能替代：
> 排版错位、表格溢出、callout 塌陷这类问题只有在渲染结果里才看得见。

---

### 9.10 面试指南结构与字面体检

`hubei-linxuan-mianshi/hubei-linxuan-mianshi.html` 是《湖北省直遴选面试指南》
（8 章 34 节，全文手写）。它的问题域与 §9.9 的范例不同：范例怕的是**重复与体例**，
面试指南怕的是**结构散架与依据被删**——目录锚点悬空、标题层级越级、公告里的关键
数字被后续编辑顺手改掉，页面不会报错，只会悄悄失真。

```bash
python scripts\check_mianshi.py                 # 体检（10 类规则 E1–E10）
python scripts\check_mianshi.py --self-test     # 反向自检（1 正对照 + 13 条注入用例 + 1 条例外用例）
```

规则一览：

| 编号 | 检查项 | 抓的是哪类事故 |
| --- | --- | --- |
| E1 | 结构完整（9 章齐全，每章有章标题与小节；侧边栏 `partNames` 覆盖全部章号） | 章节漏写、侧边栏与正文脱节 |
| E2 | 目录每个 `href="#xxx"` 都能在正文找到同名 id | 目录锚点悬空，点过去没反应 |
| E3 | 标题层级不越级（`h2.chapter-title` 只出现在 chapter 内） | 层级错乱，目录层级跟着乱 |
| E4 | 无 `**` / `__` 残留 | Markdown 标记（纯 HTML 不渲染，会露出星号） |
| E5 | 无未授权英文单词（URL 另行剔除） | 英文夹杂 |
| E6 | 无替换字符 / 非法控制字符 / 中英粘连 | 乱码 |
| E7 | 无感叹号、无网络用语（**第三方热词表按来源原文录入，单独摘出**） | 口语化、体例不符 |
| E8 | 同一章内无完全重复的正文段落 | 整段复制 |
| E9 | 24 项关键考情事实锚点必须仍在文中 | 把公告依据（面试权重 50%、80 分门槛、考场规则八条等）删掉或改错 |
| E10 | 模拟练习八道题齐全：编号连续、每题一个 `details`、默认不带 `open`、折叠标题为"参考答案"、答案正文不少于 150 字 | 答案默认摊开（学员还没答就看见答案）、漏题、答案写成空壳 |

**模拟练习章的折叠答案**：第八章用原生 `details`/`summary`（Chrome 12+ 起支持，
Chrome 69 无碍），不引脚本。参考答案默认收起，点"参考答案"才展开，样式写在页面自身的
`style` 块里（`.practice-answer` / `.practice-answer-body` / `.practice-points`），
不影响站内其他页面。E10 专门盯住"默认收起"这条——带 `open` 属性即判不合格。

**E7 的例外是窄口径、有意为之**：第三章那张热点词表按第三方来源原文录入，其中含
`"网红"打卡点` 一类当年时政流行语。那是**考试热词的引用**，不是本指南的行文用语，
改写会与来源对不上。因此脚本按表头（"面试涉及的主要热点"）定位这一张表，把它从俚语
扫描里摘出；表头一旦被改写，定位随即失效并退回全页扫描——**宁可误报，不可漏报**。
反向自检里配了一条用例专门盯这个边界：俚语写进正文必须报错，写进引用区则不报错。

**反向自检必须自带鉴别力**：注入用例要断言**命中指定的规则编号**，不能只断言
"报错了"——只断言"报错了"会因为别的规则先报错而假通过（§9.9 踩过这个坑）。

---

## 10. 自定义扩展

### 10.1 抓取其他党刊

1. 在 `MAGAZINES` 字典里添加新键（如 `'qiushi'` 或 `'dangjian'`）
2. 配置 `catalog_url`（目录页）和字段路径
3. 在 `parse_*_catalog` 中复制适配版解析函数
4. 更新 `index.html` 中的 `MAGAZINES` 和 `assets/js/app.js` 中的 `MAGAZINES`

### 10.2 抓取历史期号

求是/红旗文稿历史期号需要走"年度汇总页"，参见 §9.1。党建研究直接 `https://djyj.12371.cn/YYYY/N/` 即可
（期号不补零，参见 §3.1）。

### 10.3 加速抓取

- 改 `time.sleep(0.5)` → `0.2`（注意反爬风险）
- 用 `concurrent.futures.ThreadPoolExecutor` 并发抓多篇文章
- 但**不能**并发多个期号，会触发反爬

### 10.4 自动检测新刊（cron 模式）

```bash
# Linux/Mac crontab
0 9 * * * cd /path/to/djyj && python scripts/scrape_magazines.py --check >> logs/check.log 2>&1

# Windows 计划任务
schtasks /create /tn "djyj_check" /tr "python e:\cursor\xgkt\djyj\scripts\scrape_magazines.py --check" /sc daily /st 09:00
```

---

## 11. 完整更新流程（与 README 同步）

```bash
# 1. 检查更新
python scripts\scrape_magazines.py --check

# 2. 抓取新刊
python scripts\scrape_magazines.py qs 2026 21
python scripts\scrape_magazines.py hqwg 2026 20
python scripts\scrape_magazines.py djyj 2026 10

# 2.5 体检数据（期号覆盖 / 重复 / 正文缺失 / 分片与 counts 一致性）
python scripts\check_data.py

# 2.6 首页计数（抓取脚本会自动刷新，手动重建用这条；离线不联网）
python scripts\scrape_magazines.py --counts

# 3. 同步 index.html 的"数据更新"区块
#    改 "最近一次数据采集更新时间：2026 年 10 月 30 日"
#    改 《党建研究》：... 至 2026 年第 10 期
#    改 《求是》：... 至 2026 年第 21 期
#    改 《红旗文稿》：... 至 2026 年第 20 期

# 4. 同步缓存破坏五件套（版本号必须一致）
#    index.html 第 12 行: <link rel="stylesheet" ... ?v=YYYYMMDDx>
#    index.html 第 13 行: <link rel="manifest" ... ?v=YYYYMMDDx>
#    index.html 第 14 行: <link rel="apple-touch-icon" ... ?v=YYYYMMDDx>
#    index.html 第 420 行: <script src="assets/js/app.js?v=YYYYMMDDx">
#    assets/js/app.js 第 4 行: const DATA_VERSION = 'YYYYMMDDx';
#    （sw.js 的注册 URL 用的是 DATA_VERSION，不用另外改）
#    assets/css/style.css: 封面图 ?v=...（封面更新时，三本各自独立）

# 5. 提交
git add -A
git commit -m "更新求是2026年第21期、红旗文稿2026年第20期、党建研究2026年第10期"
git push origin main
```

> 缓存破坏五件套缺一不可，否则 Cloudflare 的 `immutable` 缓存会让用户看不到新内容。
> 详细说明见 [`docs/UPDATE_FLOW.md` §2.6](../docs/UPDATE_FLOW.md)。

---

## 12. 调试小贴士

- `parse_qs_hqwg_catalog` 解析失败时，先 `print(soup.prettify()[:2000])` 看实际 HTML
- 调慢 `time.sleep(1.0)` 后重试可绕开偶发 503
- 抓取失败时，函数返回空列表，不会污染现有数据
- 单元测试可单独 import `scrape_magazines`，对 `clean_text`、`element_to_md` 做回归
