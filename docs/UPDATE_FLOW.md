# 文章更新流程

本文件描述"如何把最新一期的三本党刊抓取并发布到网站"的标准操作流程。

> **适用场景**：每月 1 日 / 15 日左右，新刊发布后的 1–2 天内需要更新。

---

## 1. 频率

| 杂志 | 周期 | 典型发布日期 | 抓取窗口 |
| --- | --- | --- | --- |
| 求是 | 半月刊 | 每月 1 日、15 日 | 发布后 1–2 天内 |
| 红旗文稿 | 半月刊 | 每月 10 日、25 日左右 | 发布后 1–2 天内 |
| 党建研究 | 月刊 | 每月 10 日左右 | 发布后 3–5 天内 |

> 三本杂志的"期号"和实际发布日期**不完全一一对应**（如国庆、春节会顺延），以 `https://www.qstheory.cn/qs/mulu.htm` 上显示的为准。

---

## 2. 完整流程（约 10–15 分钟）

### 2.1 准备

```bash
# 进入项目根目录
cd e:\cursor\xgkt\djyj

# 确认 git 状态干净
git status
# 应该看到：nothing to commit, working tree clean
```

### 2.2 检测更新

```bash
python scripts\scrape_magazines.py --check
```

**输出示例**：

```
============================================================
检查杂志更新
============================================================
  求是: 本地 2026年第20期 | 网站 2026年第20期 | 已最新
  红旗文稿: 本地 2026年第19期 | 网站 2026年第20期 | 有更新
  党建研究: 本地 2026年第9期 | 网站 2026年第10期 | 有更新
```

如果某本杂志显示"有更新"，继续。

### 2.3 抓取新刊

```bash
# 党建研究第 10 期
python scripts\scrape_magazines.py djyj 2026 10
```

**输出示例**：

```
============================================================
开始处理: 党建研究 2026年第10期
============================================================
目录页解析到 32 篇文章
  [1/32] 本期导读...
  [2/32] ...
  ...
  完成: 32篇 (32篇有全文)
  党建研究: 封面图已更新 (123456 bytes)
```

### 2.4 验证数据

```bash
# 数据体检：期号覆盖 / 重复条目 / 正文缺失 / 索引一致性
python scripts/check_data.py
```

输出示例：

```
[hqwg] 红旗文稿
    文章总数: 2265   唯一URL: 2265   重复条目: 0
    期号范围: 2020年第01期 ~ 2026年第20期   共 165 期
    无全文(h=0): 0 篇
      2026年第20期: 13 篇
```

期望看到：**最新期号已更新、重复条目为 0、无"正文缺失"告警**。

若报出"空 URL"或"重复条目"，处理方式见 [§4.4 重复抓取同一期](#44-重复抓取同一期) 与
[§4.6 空 URL 条目](#46-空-url-条目)。

### 2.5 同步 index.html

打开 `index.html`，找到"关于本站 → 数据更新"区块（约 226 行）：

```html
<div class="about-section">
    <h2>数据更新</h2>
    <p>最近一次数据采集更新时间：<strong>2026 年 10 月 30 日</strong></p>
    <p>《党建研究》：2020 年第 12 期 至 2026 年第 10 期</p>
    <p>《求是》：2019 年第 1 期 至 2026 年第 20 期</p>
    <p>《红旗文稿》：2020 年第 1 期 至 2026 年第 20 期</p>
</div>
```

更新三处：

1. 采集日期（用当天日期）
2. 三本杂志的最新期号

### 2.6 同步缓存破坏三件套

**这是最容易遗漏的关键步骤**。如果不同步，用户会因为 `immutable` 缓存而看不到新内容。

需要同步更新以下 3 处：

| 位置 | 查找 | 示例 |
| --- | --- | --- |
| `index.html` 第 12 行 | `<link rel="stylesheet" href="assets/css/style.css?v=...` | `?v=20261030b` |
| `index.html` 第 359 行 | `<script src="assets/js/app.js?v=...` | `?v=20261030b` |
| `assets/js/app.js` 第 4 行 | `const DATA_VERSION = ...` | `'20261030b'` |
| `assets/css/style.css` | `cover_qs/hqwg/djyj.jpg?v=...`（封面更新时） | `?v=20261030b` |

**版本号命名规则**：`YYYYMMDDx`，x 是当天的 a/b/c（如果同一天多次更新）。

**为什么是 3 处？**

- HTML 的 `?v=` 决定浏览器是否会重新下载 `style.css` 和 `app.js`
- `app.js` 的 `DATA_VERSION` 决定 `dataUrl()` 给数据 URL 加什么参数，从而决定浏览器是否会重新下载 `data/*.json`
- 三者必须保持一致

### 2.7 提交

```bash
git add -A
git status
```

应该看到新增的文件（在 `data/`、`articles/`）和修改的文件（`index.html`、`assets/js/app.js`）。

```bash
git commit -m "更新党建研究2026年第10期"
```

### 2.8 推送

```bash
git push origin main
```

**推送成功后**：Cloudflare Pages 在 1–2 分钟内自动部署。

### 2.9 验证线上

```bash
# 等 1–2 分钟后，用 curl 检查
curl -I https://your-domain.pages.dev/
curl -s https://your-domain.pages.dev/data/meta.json | head -c 200
```

或者直接打开浏览器**强制刷新**（Ctrl+Shift+R / Cmd+Shift+R），进入"关于本站"查看"数据更新"是否变成最新日期。

---

## 3. 一次性抓取多本多期

```bash
python scripts\scrape_magazines.py qs 2026 21 hqwg 2026 20 djyj 2026 10
```

依次处理每本。注意：每抓一本间隔约 30–60 秒（取决于文章数）。

---

## 4. 异常处理

### 4.1 抓取失败：ConnectionError / Timeout

**原因**：求是/红旗文稿服务器偶尔 503。

**处理**：

1. 等 5–10 分钟重试
2. 错峰抓取（避开发布日当天）
3. 在 `scrape_magazines.py` 顶部 `HEADERS` 加 `Retry` 适配器

```python
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
session.mount('https://', HTTPAdapter(max_retries=Retry(total=3, backoff_factor=0.5)))
```

### 4.2 抓取到 0 篇文章

**可能原因**：

- 目标期还没出版
- 目录页结构变化
- 反爬

**处理**：

1. 在浏览器中打开目标期目录页
2. 对比 `parse_qs_hqwg_catalog` 或 `parse_djyj_catalog` 的解析规则
3. 必要时修改解析函数

### 4.3 部分文章 `h=0`（无正文）

**原因**：目录页有但正文 404 / 视频页 / 聚合页。

**处理**：无需处理。`h=0` 不影响整体功能，文章详情页会用"无全文"占位。

### 4.4 重复抓取同一期

**问题**：`process_magazine` 是**追加**模式，同一 URL 会重复。

**处理**：直接用体检脚本自带的去重功能（先体检再写回，安全）：

```bash
python scripts/check_data.py --dedup
```

它会对三刊的 `meta.json` 和 `data/article_index.json` 按 URL 去重，并打印 `原数量 -> 新数量`。

> ⚠️ 早期数据里的"重复"多数是**空 URL**（见 §4.6），按 URL 去重会把它们合并成 1 条，
> 而不是真正修复。发现 `唯一URL < 文章总数` 时先看 §4.6。

### 4.5 抓取后 git push 失败

**原因**：远程有新提交，本地落后。

**处理**：

```bash
git pull --rebase origin main
# 解决冲突后
git push origin main
```

### 4.6 空 URL 条目

**症状**：体检报"存在重复 URL N 条"，但逐条看会发现这些条目的 `u` 字段是空字符串。

**原因**：《党建研究》目录页里，"贯彻落实全国组织部长会议精神""全国党建工作座谈会发言摘登"等板块
只列标题和作者，**官网没有对应的单篇文章页面**（纯 `<span>` 文本，无链接）。早期解析器把它们也写进了
`meta.json`，导致 `u` 为空。

**危害**：前端用 `meta.findIndex(a => a.u === url)` 定位文章，空串会**匹配到第一条坏记录**，
结果点任何一条都打开同一篇（错误）文章。

**处理**：

```bash
python scripts/repair_empty_urls.py            # 预览
python scripts/repair_empty_urls.py --apply    # 写回
```

脚本会重新抓取对应期号的目录页，**校验该标题确实出现在页面上**，然后给条目分配
「该期目录页 + 标题片段」作为唯一地址（`h` 仍保持 0，正文页会诚实提示"该文章无全文内容"，
"原文链接"可跳到官网目录页核对）。

### 4.7 党建研究抓到 0 篇文章

**原因**：党建研究的**目录页期号不补零**（`/2026/7/`），而**文章内链补零**（`/2026/07/22/ARTI*.shtml`）。
目录页 URL 拼成 `/2026/07/` 会被 12371 重定向到 `error.html`，表现为"解析到 0 篇"。

**处理**：`find_catalog_url()` 已同时尝试 `/年/期/` 与 `/年/0期/` 两种写法，手工排查时两种都试一下。

---

## 5. 缓存破坏的最佳实践

### 5.1 命名

- `YYYYMMDDx` 格式，x 是同一天的版本（a, b, c...）
- **不要**用 `v1.2.3` 这种语义化版本（用户不理解，团队协调困难）

### 5.2 时机

- 仅在**确实更新**数据时升级版本号
- 修改 CSS/JS 但不改数据时，**也**应该升级（因为 CSS/JS 缓存破坏也是 `?v=`）

### 5.3 测试

升级版本号后，**强制刷新**浏览器（Ctrl+Shift+R）确认能看到新版本。

---

## 6. 自动化建议（未来）

可以把以下脚本加入 Windows 计划任务：

```powershell
# check_djyj.ps1
cd e:\cursor\xgkt\djyj
python scripts\scrape_magazines.py --check
if ($LASTEXITCODE -eq 0) {
    python scripts\scrape_magazines.py djyj 2026 11
    # 同步 index.html 与版本号（需要解析输出）
    git add -A
    git commit -m "自动更新党建研究"
    git push origin main
}
```

但**人工确认是必要的**：脚本无法判断"h=0 是否合理"或"封面图是否需要更新"。

---

## 7. 月度时间线（示例）

```
10 月 1 日   求是 21 期发布
            └→ 人工确认 + 抓取

10 月 10 日  红旗文稿 20 期发布 / 党建研究 10 期发布
            └→ 一次抓两本

10 月 15 日  求是 22 期发布
            └→ 抓取
```

---

## 8. 故障演练

### 8.1 模拟：求是网 503 持续 1 天

**应对**：

- 当天跳过抓取
- 第二天重试
- 用户访问不会受影响（已发布内容仍可访问）

### 8.2 模拟：Cloudflare Pages 部署失败

**应对**：

- 检查 Cloudflare 部署日志
- 回退到上一版本（Cloudflare 提供版本切换）
- 修复后重新推送

### 8.3 模拟：不小心 `git push` 了错误版本

**应对**：

```bash
git revert HEAD
git push origin main
```

Cloudflare 会在 1–2 分钟内回滚到上一个版本。

---

## 9. 文档维护

每次更新流程有调整，请同步更新本文件。重大变化同步更新 `README.md` 和 `scripts/README.md`。
