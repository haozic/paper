# 交接记录

## 当前任务

按新确认的结构优化首页、杂志页与正文页，保持 GitHub / Cloudflare Pages 静态部署。

## 已完成

- 首页增加三刊标题搜索、三刊最新文章入口与刊物选择分区。
- 杂志页明确检索范围与按板块/期号浏览导航。
- 正文页增加标题目录锚点与阅读设置无障碍名称。
- 全站应用暖纸白、深墨色、克制朱红的中文编辑式视觉系统和响应式布局。
- 更新静态资源版本号，避免部署后命中旧缓存。
- 首页最新文章数据拆为 `data/latest.json`（424 字节），由 `scripts/build_home_latest.py` 从元数据生成；更新刊物数据后需执行该脚本。

## 验收

- `node --check assets/js/app.js` 通过。
- `python scripts/check_compat.py` 通过。
- `git -c core.whitespace=cr-at-eol diff --check` 通过。仓库 CSS 使用 CRLF，检查时需指定 `cr-at-eol`。
- `python scripts/check_data.py` 发现既有正文数据问题：红旗文稿有 1 篇标记有全文但正文缺失；党建研究 2026 年第 10 期目录存在 31 篇文章但分片检查显示整期缺失。未在本次布局改造中改动正文数据。

## 部署

- 当前版本号：`20261101e`。
- 发布流程：推送 GitHub `main` 后由 Cloudflare Pages 自动部署。
- 需在部署后检查首页搜索/最新文章、目录锚点、夜间模式和窄屏排版。
