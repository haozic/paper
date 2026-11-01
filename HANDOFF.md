# 交接记录

## 当前任务

党内刊物静态阅读网站通过 GitHub `main` 和 Cloudflare Pages 部署。用户本轮要求除首页三个专题及其独立页面外，统一网站样式、配色、图标和边角。用户希望持续做完并同步 GitHub。

## 已完成

- 新增 `assets/css/system.css`，作为 `style.css`、`books.css`、`one.css` 之后的统一设计层；HTML 与 Service Worker 均加载它。
- 统一首页、杂志目录、搜索、收藏、板块、正文、关于及访问密码页的纸色背景、深墨文字、朱红强调色、边框、圆角、阴影、控件状态和中文字体。三个专题独立页面不加载新样式。
- 全站 SVG 图标线宽统一为 1.8；桌面和手机导航图标统一为 20px；浏览器主题色、favicon 与 manifest 主题色改为新版朱红。
- 阅读设置的夜间模式及自动夜间模式有专门覆盖，避免旧书库 CSS 回到冷灰配色；文章纸张选项仍由原 JS 控制。
- “关于本站”页面移除直接显示访问密码的文字。
- 静态资源版本更新为 `20261101m`。
- 之前已完成：首页三刊大封面居中；正文固定底栏“目录、设置、下一篇”；本期目录列表和进度环定位修复。

## 验收与限制

- `tinycss2` 解析 `system.css` 无错误；`node --check assets/js/app.js`、`node --check sw.js`、`git -c core.whitespace=cr-at-eol diff --check` 通过。提交前再运行一次。
- Playwright 尝试打开本地 `http://127.0.0.1:8765/`，环境返回 `net::ERR_NETWORK_ACCESS_DENIED`；本地浏览器视觉检查未能完成。此前移除访问门做视觉核对被自动审批拒绝，不绕过。
- 旧数据问题：红旗文稿 1 篇标记有全文但正文缺失；党建研究 2026 年第 10 期目录有 31 篇文章但正文分片缺失。本轮未改数据。

## 下一步

- 如有登录后的桌面/手机截图，可继续检查统一设计在真实视口中的细节。

## 踩过的坑

- CSS 加载顺序为 `style.css`、`books.css`、`one.css`、`system.css`；旧夜间规则选择器权重较高，需在最后一层用同等级选择器覆盖。
- 三个专题是独立 HTML 页面，未引用 `system.css`；首页三个入口也未单独改造。
- 用 Python 字节替换 HTML SVG 属性时曾产生字面量反斜杠，已修复并用 `rg` 核对属性是 `stroke-width="1.8"`。
- `.git` 写入可能需要 `require_escalated`。推送偶有凭据程序输出 `fatal: Cannot prompt`，即使命令退出码为 0 也要用 `git ls-remote` 核对远端。
- CSS 有 CRLF，diff 检查用 `core.whitespace=cr-at-eol`。
