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

### 2.4 重建跨刊标题索引

**重建跨刊标题索引**：`python scripts\build_search_index.py`
（先升 `scripts\build_search_index.py` 里的 `INDEX_VERSION`，再运行；
然后 `python scripts\build_search_index.py --check` 确认与 meta 一致）

> `data/search_index.json` 由三份 `meta.json` 派生，是派生产物。
> 改了 `meta.json` 就要重建这一步。本步要在 §2.5 验证数据之前完成
> （否则体检会报「S1 行数不符」），也要在 §2.8 提交之前完成。

### 2.5 验证数据

```bash
# 数据体检：期号覆盖 / 重复条目 / 正文缺失 / 分片与 counts 一致性
python scripts/check_data.py
```

输出示例：

```
[hqwg] 红旗文稿
    文章总数: 2265   唯一URL: 2265   重复条目: 0
    期号范围: 2020年第01期 ~ 2026年第20期   共 164 期
    无全文(h=0): 0 篇
    正文分片: 164 个   整期无正文: 0 期
      2026年第20期: 13 篇

[counts.json] 校验
    红旗文稿: 文章 2265 篇 / 期 164 期  一致

[search_index] 跨刊标题索引
    S1 行数一致：7415 行
    S2 逐行可寻址：全部命中（含标题一致）
    S3 同一刊物内 URL 无重复
    S4 体积 1000280 字节（上限 1572864）
    索引问题数: 0
```

> 期望看到：**最新期号已更新、重复条目为 0、无"正文缺失"告警、counts 与 meta 一致、
> 索引与 meta 一致（`索引问题数: 0`）**。
> 改了 `meta.json` 却没有重建索引时，`check_data.py` 会报 `!! S1 行数不符`
> 并以非 0 退出码退出 —— 这时先回 §2.4 重建索引，不要直接往下走。

> 2026-10-30 起体检脚本多断言两项 **板块名**：兜底值（"目 录"/"评论"，不是真实栏目）
> 与归一表里的旧写法（同一栏目改过名）都必须为 **0 条**。
> 末尾汇总行会打印 `板块名体检: 兜底值 N 条   未归一旧写法 N 条`。

> 正文数据自 2026-10 起按期分片存放在 `data/<mag>/issues/<年>-<期>.json`，
> 体检脚本会逐片核对"meta 标了有正文的文章在对应分片里确实存在"，
> 并报告"孤儿分片"（磁盘上有分片但 meta 里没有该期次）。

若报出"空 URL"或"重复条目"，处理方式见 [§4.4 重复抓取同一期](#44-重复抓取同一期) 与
[§4.6 空 URL 条目](#46-空-url-条目)。

> 改动了 `sw.js`（或任何 `.js`）时，还要跑这几个体检：
>
> ```bash
> python scripts/check_js_comments.py    # 注释层 + SW 求值冒烟
> python scripts/check_sw_navigate.py    # SW 导航处理（行为级）
> python scripts/check_compat.py        # Chrome 69 兼容性
> ```
>
> `check_sw_navigate.py` 是 2026-10-30 新增的：那次"首页入口打不开"的根因就在
> SW 的导航处理上（详见 [§4.9](#49-首页入口打不开空白没有样式)）。

### 2.6 同步 index.html

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

### 2.7 同步缓存破坏三件套

**这是最容易遗漏的关键步骤**。如果不同步，用户会因为 `immutable` 缓存而看不到新内容。

需要同步更新以下 5 处（**五处必须一致**）：

| 位置 | 查找 | 当前示例 |
| --- | --- | --- |
| `index.html` 第 12 行 | `<link rel="stylesheet" href="assets/css/style.css?v=...` | `?v=20261030h` |
| `index.html` 第 13 行 | `<link rel="manifest" href="manifest.webmanifest?v=...` | `?v=20261030h` |
| `index.html` 第 14 行 | `<link rel="apple-touch-icon" href="assets/img/apple-touch-icon.png?v=...` | `?v=20261030h` |
| `index.html` 第 427 行 | `<script src="assets/js/app.js?v=...` | `?v=20261030h` |
| `assets/js/app.js` 第 4 行 | `const DATA_VERSION = ...` | `'20261030h'` |

> `sw.js` 里还有两处 `'20261030h'` 兜底值（第 42、44 行）。正常情况下 SW 从自身 URL 的
> `?v=` 参数取版本（注册时用 `sw.js?v=<DATA_VERSION>`），兜底值只在 SW 被直接访问时才会用到；
> 但为了让"全仓库搜同一个版本号"的自查能一次搜干净，建议一并改。

**封面图版本号是独立的**，不要跟着上面的日期走：

| 文件 | 版本号 |
| --- | --- |
| `assets/img/cover_qs.jpg` | `?v=20260920a` |
| `assets/img/cover_hqwg.jpg` | `?v=20261030a` |
| `assets/img/cover_djyj.jpg` | `?v=20261030a` |

封面图在 `assets/css/style.css` 里引用，**只有换封面图时才改**，且三本各自独立。

**版本号命名规则**：`YYYYMMDDx`，x 是当天的 a/b/c（如果同一天多次更新）。

**为什么是 5 处？**

- HTML 的 `?v=` 决定浏览器是否会重新下载 `style.css`、`manifest` 与 `app.js`
- `app.js` 的 `DATA_VERSION` 决定 `dataUrl()` 给数据 URL 加什么参数，从而决定浏览器是否会重新下载 `data/*.json`
- manifest 的 `?v=` 保证浏览器不会用旧 manifest
- `sw.js` 用同一个版本号注册，版本一变 → 浏览器装新 SW → 新 SW 的 `activate` 清掉旧的外壳与数据缓存
- 五者必须保持一致

**自查**：

```bash
# 全仓库搜旧版本号（把 20261030c 换成上一次的版本号），应当搜不到任何结果
git grep -n "20261030c" -- ':!docs/UPDATE_FLOW.md'
```

### 2.8 提交

```bash
git add -A
git status
```

应该看到新增的文件（在 `data/<mag>/issues/`、`articles/`）和修改的文件（`index.html`、`assets/js/app.js`）。

```bash
git commit -m "更新党建研究2026年第10期"
```

### 2.9 推送

```bash
git push origin main
```

**推送成功后**：Cloudflare Pages 在 1–2 分钟内自动部署。

### 2.10 验证线上

```bash
# 等 1–2 分钟后，用 curl 检查
curl -I https://your-domain.pages.dev/
curl -s https://your-domain.pages.dev/data/meta.json | head -c 200
```

或者直接打开浏览器**强制刷新**（Ctrl+Shift+R / Cmd+Shift+R），进入"关于本站"查看"数据更新"是否变成最新日期。

### 2.11 验证 Service Worker（离线能力）

站点自 2026-10-30 起带 Service Worker（`sw.js`），发版后多了一步验证：

```bash
# 确认 SW 能取到，且响应头是 must-revalidate
curl -I https://your-domain.pages.dev/sw.js
# 期望：Cache-Control: public, max-age=0, must-revalidate
```

浏览器端检查：

1. **DevTools → Application → Service Workers**：状态应为 `activated and is running`
2. **DevTools → Application → Cache Storage**：应看到 `djyj-shell-<版本号>`、`djyj-rt-<版本号>`、`djyj-md` 三个缓存
3. **离线验证**：DevTools → Network 勾选 `Offline`，然后**普通刷新**（不是强制刷新）——
   页面应照常渲染（样式完整、三刊计数正确），已读过的文章正文可继续打开
4. **新版本提示**：改动版本号并部署后，页面底部应弹出"新版本已就绪，点击刷新"

> **注意**：强制刷新（Ctrl+Shift+R）会绕过 Service Worker，看到的是"永远最新"的联网结果，
> 不能用来验证离线能力。要验证离线请用 Network 面板的 Offline 开关，或停掉本地服务器。

**Service Worker 与版本号的关系**：

| 缓存 | 键规则 | 跨版本 |
| --- | --- | --- |
| `djyj-shell-<v>` | index.html 按路径；CSS/JS/manifest/计数/meta/索引按完整 URL（含 `?v=`） | ❌ 随版本清空 |
| `djyj-rt-<v>` | 正文分片按路径；meta/索引按完整 URL | ❌ 随版本清空 |
| `djyj-md` | `articles/**/*.md` 按路径 | ✅ 永久保留（正文不可变） |

正文 md 缓存跨版本保留，所以**每次发版不会重下 85 MB 正文**；而 meta / 索引会随版本清空重下，
保证不会把上一期的目录当成本期。

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

### 4.8 板块名异常：整期板块是"目录"/"评论"，或整期没有板块

**症状**：板块页上出现一张叫"目 录"或"评论"的卡片；或者某一期文章的板块全空。

**原因（2026-10-30 查清）**：

- **"目 录"是抓取脚本的兜底值**，不是求是真栏目。旧版目录页用 `<font color="maroon">目 录</font>`
  标目录页自己的标题，老解析器只认 `<span style="color: #ba372a">`，且比较"目 录"时只按半角空格，
  页面实际有半角 / 全角 U+3000 / nbsp 三种写法 → 全被当成了板块。
- **"评论"是微博分享控件的产物**：老版本把文章页的 `<div class="fs-pinglun"><span class="big">评论</span>`
  当成了栏目。

**处理**（**不用重抓正文** —— 板块名只存在 `meta.json` 的 `s` 字段里，正文分片完全不用动）：

```bash
# 预演：只抓目录页（每期 1 个请求），打印刷回/清空的条数与前后分布，不写盘
python scripts\refresh_sections.py
# 实际写回
python scripts\refresh_sections.py --apply
# 只处理某一本 / 某几期
python scripts\refresh_sections.py --mag qs --issues 2026-15,2026-20
```

脚本**只保留来源站目录页能证实的板块名**，证实不了的一律清空（前端归入"未分栏目"）；
目录页抓不到就整期不动，不用猜测覆盖已有数据。

**同名栏目被改名**（板块页上多出两张相似的卡片）由 `scripts\canonical_sections.py` 处理：

```bash
python scripts\canonical_sections.py            # 写盘
python scripts\canonical_sections.py --check     # 只体检
```

归一表在 `scripts/canonical_sections.py` 的 `ALIASES` 里，每条都附来源站证据；
**没有来源站证据的相似名字不合并**（例如党建研究的"调查报告"与"调研报告"保持原样）。

> **边界**：求是 2019–2025 年 14 期（158 期）的栏目信息**在来源站已彻底下线**
> （实时目录页里 `│` = 0、红色标题 = 0），这批文章只能进"未分栏目"。
> 彻底修正需要外部档案或第三方镜像。

### 4.9 首页入口打不开（空白、没有样式）

**症状**（2026-10-30 用户报障）：首页底部"遴选备考指南""荆楚遴选备考全书"两张卡片，
点进去**打开了新页面，但空白、没有样式**；直接在新标签输 URL 也是一样。

**排查顺序**（先证伪服务端，再查客户端）：

```bash
# 1) 线上字节是否与本地一致 —— 一致就说明不是服务端问题
curl.exe -sS -o 线上.html "https://paper.zhouhao.cn/linxuan-beikao-zhinan/linxuan-beikao-zhinan"
# 本地算 MD5 与线上比对

# 2) 各路径变体的状态码（注意 .html 会 308 到无扩展名路径）
curl.exe -sS -o NUL -w "%{http_code} %{content_type} %{size_download} -> %{redirect_url}" \
  "https://paper.zhouhao.cn/linxuan-beikao-zhinan/linxuan-beikao-zhinan.html"
```

**根因**（在 SW 层）：

1. Cloudflare 的 `html_handling` 把 `.html` **308 重定向**到无扩展名路径；
2. SW 里直接 `fetch(导航请求)`，遇到跳转会按 Fetch 规范被过滤成 **opaque**
   （`status=0、ok=false、redirected=false`）；
3. 旧代码把 `!response.ok` 当成"断网"，回落到缓存的 `index.html`，
   **把首页 HTML 塞到子页面地址上**；
4. 首页的 `assets/` 是相对路径，在子目录下全部 404 → **空白 + 没有样式**；
5. 缓存里查不到首页时返回 `Response.error()` → 浏览器 `net::ERR_FAILED`。

**处理**：已在 `sw.js` 修掉（导航抓取改用 `mode: 'same-origin'`；SW 只接管
`/` 与 `/index.html` 两个外壳路由，其余静态页放行给网络），并新增行为级体检：

```bash
python scripts\check_sw_navigate.py
python scripts\check_sw_navigate.py --self-test
```

> 改 `sw.js` 后**一定要**跑这个体检：它会把线上 sw.js 放进 mock 的 SW 环境，
> 用一个"按规范把重定向响应过滤成 opaque"的假 fetch 实跑导航，
> 断言"首页正常联网""外壳路径拿到干净响应""非外壳路径不被接管""断网仍能回落"。

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
