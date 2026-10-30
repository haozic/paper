# 抓取脚本使用文档

`scripts/scrape_magazines.py` 是本项目的数据采集入口，负责把三本中央级党刊（《求是》《党建研究》《红旗文稿》）从官方网站拉取到本地，**同时更新四类数据**：

- `data/<mag>/meta.json` — 文章元数据
- `data/<mag>/years/<year>.json` — 文章正文（按年拆分）
- `data/article_index.json` — `URL → articles/<mag>/<file>.md` 路径映射
- `assets/img/cover_<mag>.jpg` — 最新一期封面图
- `articles/<mag>/<year>_<issue>_<title>.md` — 原始 Markdown 备份

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

# 修复历史遗留的"空 URL"条目（默认预览，加 --apply 才写回）
python scripts\repair_empty_urls.py
python scripts\repair_empty_urls.py --apply

# Chrome 69 兼容性体检（零依赖，有问题返回非 0 退出码）
python scripts\check_compat.py
python scripts\check_compat.py --list
```

| 脚本 | 作用 | 何时用 |
| --- | --- | --- |
| `check_data.py` | 体检三刊的 meta / years / article_index 一致性 | 每次抓取后；怀疑数据异常时 |
| `repair_empty_urls.py` | 修复 `u` 字段为空的条目 | 体检报出空 URL 时 |
| `check_compat.py` | 体检 Chrome 69 兼容性（特性黑名单 + flex gap 兜底缺失） | 改动 CSS / JS 后；详见 [`docs/CHROME69_COMPAT.md`](../docs/CHROME69_COMPAT.md) |

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
              4. 写入 4 个数据文件
              ├─ data/<mag>/meta.json            (追加)
              ├─ data/<mag>/years/<year>.json    (追加)
              ├─ data/article_index.json         (追加)
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

## 6. years/YYYY.json 字段约定

`data/qs/years/2026.json` 是 `{URL: 正文 Markdown}` 的纯字典：

```json
{
  "https://www.qstheory.cn/20261015/.../c.html": "# 标题\n\n正文段落 1\n\n正文段落 2\n\n..."
}
```

- 键：原文 URL（与 `meta.json` 的 `u` 字段一一对应）
- 值：抓取后清洗的 Markdown 文本

**懒加载逻辑**（前端 `assets/js/app.js`）：用户首次搜索时只下载 `meta.json`（~1.5 MB）。当用户切换到"正文搜索"或点击文章页时，**才下载对应年份的 `years/YYYY.json`**，按需加载。

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
- 文章详情页直接 `fetch(articles/qs/2026_20_xxx.md)`，避免把全量正文塞进 `years/YYYY.json`

> 如果把 `articles/` 从仓库删除，只需要保证 `data/years/YYYY.json` 里仍有正文（站点会自动回退到该数据源渲染文章）。

---

## 8. 关键函数清单

| 函数 | 位置 | 作用 |
| --- | --- | --- |
| `MAGAZINES` | 顶部 | 三本杂志的配置字典（catalog_url / meta_path / years_path / articles_dir / cover_path） |
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

# 2.5 体检数据（期号覆盖 / 重复 / 正文缺失）
python scripts\check_data.py

# 3. 同步 index.html 的"数据更新"区块
#    改 "最近一次数据采集更新时间：2026 年 10 月 30 日"
#    改 《党建研究》：... 至 2026 年第 10 期
#    改 《求是》：... 至 2026 年第 21 期
#    改 《红旗文稿》：... 至 2026 年第 20 期

# 4. 同步缓存破坏三件套
#    index.html: <link ... ?v=YYYYMMDDx> 和 <script ... ?v=YYYYMMDDx>
#    assets/js/app.js: const DATA_VERSION = 'YYYYMMDDx';
#    assets/css/style.css: 封面图 ?v=YYYYMMDDx（封面更新时）

# 5. 提交
git add -A
git commit -m "更新求是2026年第21期、红旗文稿2026年第20期、党建研究2026年第10期"
git push origin main
```

> 缓存破坏三件套缺一不可，否则 Cloudflare 的 `immutable` 缓存会让用户看不到新内容。

---

## 12. 调试小贴士

- `parse_qs_hqwg_catalog` 解析失败时，先 `print(soup.prettify()[:2000])` 看实际 HTML
- 调慢 `time.sleep(1.0)` 后重试可绕开偶发 503
- 抓取失败时，函数返回空列表，不会污染现有数据
- 单元测试可单独 import `scrape_magazines`，对 `clean_text`、`element_to_md` 做回归
