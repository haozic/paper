# 交接记录

## 当前任务

党内刊物静态阅读网站通过 GitHub `main` 与 Cloudflare Pages 部署。本轮用户要求阅读页开启首行缩进时，文章内各级标题也跟随缩进，符合中文阅读习惯。用户此前要求直接做完并同步 GitHub。

## 本轮已完成

- 文章内 Markdown 各级标题、中文数字小标题、独立加粗标题，以及原始 HTML 的 h1–h6 标题，统一使用阅读设置的 `--article-indent`。选择“不缩进”时这些标题也回到顶格。
- 主文章标题与导航标题不受影响。资源版本更新为 `20261101q`。

## 验收与限制

- `tinycss2` 解析 `assets/css/style.css` 无错误；`node --check assets/js/app.js`、`node --check sw.js`、`git -c core.whitespace=cr-at-eol diff --check` 通过。
- Playwright 浏览器在本环境禁止本地 HTTP (`net::ERR_NETWORK_ACCESS_DENIED`) 和 `file:` 协议，无法完成真实页面截图。此前移除访问门做视觉核对被自动审批拒绝，不绕过。
- 旧数据问题：红旗文稿 1 篇标记有全文但正文缺失；党建研究 2026 年第 10 期目录有 31 篇文章但正文分片缺失。本轮未改数据。

## 下一步

- 如能在真实浏览器看到登录后的页面，核对各级标题在“缩进/不缩进”两档下的实际对齐。

## 踩过的坑

- CSS 顺序为 `style.css`、`books.css`、`one.css`、`system.css`。旧桌面侧栏在 `style.css` 的媒体查询中设为 flex/sticky/full-height，必须在最后一层完整覆盖布局属性，不能只改宽度。
- 桌面板块列表旧规则是卡片网格，需要一起覆盖为连续列表；`article-layout:has(...)` 旧规则会让正文在本文目录存在时偏离标题轴线。
- 站点正文底栏与文末相关阅读是不同容器；不可把相关阅读一起固定。
- `.git` 写入可能需要 `require_escalated`。推送时可能出现凭据程序无交互警告，需用 `git ls-remote` 核对远端提交。
- CSS 有 CRLF，diff 检查用 `core.whitespace=cr-at-eol`。
- 阅读设置面板由 `init()` 移进底栏菜单；改层级时需要同时检查 `.reading-operation-menu` 和 `.ap-settings-panel` 的旧规则。顶部返回按钮移除后，仍要覆盖旧的文章 header grid areas。
- `readingIssueMenu` 在 `renderArticleFooter()` 中动态生成，每次换文章都会重建；目录内的导航入口应放在此处。`toggleIssueContents()` 会将当前文章滚进可视区，因此导航标题需 sticky。
- 正文标题在 `renderMarkdown()` 中不全是 h 标签：Markdown 标题转为 `p.md-heading`，中文数字标题为 `p.md-subheading`，独立加粗行是 `p.md-bold`。这三类原先都显式设为 `text-indent: 0`。
