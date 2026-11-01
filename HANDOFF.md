# 交接记录

## 当前任务

党内刊物静态阅读网站通过 GitHub `main` 和 Cloudflare Pages 部署。用户希望首页封面醒目、正文阅读顺畅，并要求任务完成后同步 GitHub。本轮针对：首页三本刊物封面太小；正文页底部三按钮要固定；右下角阅读进度环与返回顶部按钮显示异常。

## 已完成

- 首页三刊封面从桌面 92px、手机 70px 的小图恢复为主视觉。桌面三列大封面，手机横滑大封面；继续使用 `background-size: contain`，确保封面完整。
- 将上一篇、操作、下一篇从文末 footer 拆到独立 `readingDock`，固定在视口底部；操作菜单从底栏向上展开，正文末尾留出安全空间。
- 找到右下角按钮异常的原因：`books.css` 将 `.article-page .back-to-top` 改成 `position: static`。在最后加载的 `one.css` 恢复 fixed，并放在底栏上方；进度值夹在 0–1 范围内。
- 文章关闭时隐藏底栏，新文章打开时重置操作菜单和阅读设置状态。资源版本为 `20261101k`。
- 上轮已完成：首页移除重复最新文章区、缩小底部专题链接；正文页文末三按钮及阅读设置、收藏、分享、原文操作；杂志与正文统一简约风格。

## 验收与限制

- `node --check assets/js/app.js`、`node --check sw.js`、`git -c core.whitespace=cr-at-eol diff --check` 已通过。
- 站点存在访问密码门，无法直接核对登录后的真实浏览器画面；此前临时移除遮罩的自动审批被拒绝，不能绕过。
- 旧数据问题：红旗文稿有 1 篇标记有全文但正文缺失；党建研究 2026 年第 10 期目录有 31 篇文章但正文分片缺失。本轮未改数据。

## 下一步

- 若用户能提供登录后的截图，可针对桌面与手机封面、固定底栏、菜单及进度按钮继续做视觉微调。
- 更新正文数据时，按现有脚本维护首页精选数据 `data/latest.json`。

## 踩过的坑

- CSS 加载顺序为 `style.css`、`books.css`、`one.css`。封面小图由 `one.css` 最后覆盖造成；进度按钮定位被 `books.css` 改为 static。
- 固定底栏不能直接把含相关阅读的整个 footer 固定，否则相关阅读也会遮盖正文；导航和操作菜单放进单独的 dock。
- `.git` 写入可能需要 `require_escalated`；`git push` 返回 session ID 时持续轮询。推送时偶有凭据程序打印 `fatal: Cannot prompt`，即使命令 exit 0 也要用 `git ls-remote` 核对远端提交。
- 仓库 CSS 有 CRLF，diff whitespace 检查用 `core.whitespace=cr-at-eol`。
