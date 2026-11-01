# 交接记录

## 当前任务

党内刊物静态阅读网站通过 GitHub `main` 与 Cloudflare Pages 部署。本轮用户要求全站只使用系统字体、改善访问速度，并删除阅读页“目录”内的“网站首页/杂志首页”两个按钮。用户此前要求直接做完并同步 GitHub。

## 本轮已完成

- 删除主站的 Google Fonts 请求，将主站和三个专题页的实际排版都改为系统字体；两个专题页原有的 `@font-face` 本地 TTF 请求也已移除。
- 删除阅读页“目录”面板里的两个回首页按钮，以及对应 CSS 和 JS。
- Service Worker 更新时不再后台预取约 2 MB 的搜索索引和文章索引，仍预取三刊元数据以保留离线目录；两个大索引改为首次使用时缓存。
- Service Worker 返回网络内容时不再等待缓存写入完成；先克隆响应，再通过 `event.waitUntil` 后台写入。首页与静态资源都走此路径。
- Cloudflare Pages 的 `/assets/*` 浏览器缓存由每次校验改为 1 天；CSS/JS 使用版本化 URL，资源版本更新为 `20261101r`。

## 验收与限制

- `python scripts/check_sw_navigate.py` 的 5 项通过，包括新增“缓存写入卡住，首页仍立即响应”；反向自检 2/2 通过。
- `tinycss2` 解析 CSS 无错误；`node --check assets/js/app.js`、`node --check sw.js`、`git -c core.whitespace=cr-at-eol diff --check` 通过。已确认实际页面文件没有外部/本地字体加载声明。
- Playwright 浏览器在本环境禁止本地 HTTP (`net::ERR_NETWORK_ACCESS_DENIED`) 和 `file:` 协议，无法完成真实页面截图。此前移除访问门做视觉核对被自动审批拒绝，不绕过。
- 旧数据问题：红旗文稿 1 篇标记有全文但正文缺失；党建研究 2026 年第 10 期目录有 31 篇文章但正文分片缺失。本轮未改数据。

## 下一步

- 如能在真实浏览器访问线上站点，记录首次访问与重复访问的网络瀑布图，核对字体请求消失、缓存命中及首屏时间。

## 踩过的坑

- CSS 顺序为 `style.css`、`books.css`、`one.css`、`system.css`。旧桌面侧栏在 `style.css` 的媒体查询中设为 flex/sticky/full-height，必须在最后一层完整覆盖布局属性，不能只改宽度。
- 桌面板块列表旧规则是卡片网格，需要一起覆盖为连续列表；`article-layout:has(...)` 旧规则会让正文在本文目录存在时偏离标题轴线。
- 站点正文底栏与文末相关阅读是不同容器；不可把相关阅读一起固定。
- `.git` 写入可能需要 `require_escalated`。推送时可能出现凭据程序无交互警告，需用 `git ls-remote` 核对远端提交。
- CSS 有 CRLF，diff 检查用 `core.whitespace=cr-at-eol`。
- 阅读设置面板由 `init()` 移进底栏菜单；改层级时需要同时检查 `.reading-operation-menu` 和 `.ap-settings-panel` 的旧规则。顶部返回按钮移除后，仍要覆盖旧的文章 header grid areas。
- `readingIssueMenu` 在 `renderArticleFooter()` 中动态生成，每次换文章都会重建；目录内的导航入口应放在此处。`toggleIssueContents()` 会将当前文章滚进可视区，因此导航标题需 sticky。
- 正文标题在 `renderMarkdown()` 中不全是 h 标签：Markdown 标题转为 `p.md-heading`，中文数字标题为 `p.md-subheading`，独立加粗行是 `p.md-bold`。这三类原先都显式设为 `text-indent: 0`。
- SW 的 fetch 事件需要立即调用 `event.waitUntil` 续命；等到异步回调中再调用可能遇到事件已失活。响应应在等待缓存写入前先 `clone()`。
- `scripts/check_sw_navigate.py --self-test` 在 sandbox 的默认 TEMP 目录写入会被拒绝；将 `TEMP` 和 `TMP` 临时指向 workspace 内空目录后可通过，跑完删除该空目录。
