# 交接记录

## 当前任务

党内刊物静态阅读网站通过 GitHub `main` 与 Cloudflare Pages 部署。当前用户反馈文章阅读页的返回按钮不好操作，设置按钮展开后遮挡整屏、看不到正文样式变化，要求改进阅读操作路径。用户此前要求直接做完并同步 GitHub。

## 本轮已完成

- 阅读页新增随滚动保持可见的细顶栏，左侧为 44px 高触控区域的“返回列表”，滚动后显示当前文章的简短标题。返回入口不再局限于文章开头。
- 设置面板改成底栏上方的紧凑浮层，桌面宽度最多 376px、移动端高度最多半屏；字号、主题等调整时正文仍在视野里。设置项置于收藏/分享/原文操作上方，并保留关闭按钮与点击外部关闭的行为。
- 设置浮层打开时暂时隐藏可能重叠的右下角阅读进度按钮。
- 资源版本更新为 `20261101o`。

## 验收与限制

- `tinycss2` 解析 `assets/css/system.css` 无错误；`node --check assets/js/app.js`、`node --check sw.js`、`git -c core.whitespace=cr-at-eol diff --check` 通过。
- Playwright 浏览器在本环境禁止本地 HTTP (`net::ERR_NETWORK_ACCESS_DENIED`) 和 `file:` 协议，无法完成真实页面截图。此前移除访问门做视觉核对被自动审批拒绝，不绕过。
- 旧数据问题：红旗文稿 1 篇标记有全文但正文缺失；党建研究 2026 年第 10 期目录有 31 篇文章但正文分片缺失。本轮未改数据。

## 下一步

- 如能在真实浏览器看到登录后的页面，核对窄屏中浮层高度、顶部返回栏与正文的视觉比例。

## 踩过的坑

- CSS 顺序为 `style.css`、`books.css`、`one.css`、`system.css`。旧桌面侧栏在 `style.css` 的媒体查询中设为 flex/sticky/full-height，必须在最后一层完整覆盖布局属性，不能只改宽度。
- 桌面板块列表旧规则是卡片网格，需要一起覆盖为连续列表；`article-layout:has(...)` 旧规则会让正文在本文目录存在时偏离标题轴线。
- 站点正文底栏与文末相关阅读是不同容器；不可把相关阅读一起固定。
- `.git` 写入可能需要 `require_escalated`。推送时可能出现凭据程序无交互警告，需用 `git ls-remote` 核对远端提交。
- CSS 有 CRLF，diff 检查用 `core.whitespace=cr-at-eol`。
- 阅读设置面板由 `init()` 移进底栏菜单；改层级时需要同时检查 `.reading-operation-menu` 和 `.ap-settings-panel` 的旧规则。顶部返回按钮从文章 header 移走后也要覆盖旧的 header grid areas。
