# 党内刊物阅读

将《求是》《红旗文稿》《党建研究》《旗帜》和习近平讲话库整理在同一个阅读网站。目录与文章只从各自官方网站采集；本站提供统一检索、收藏、阅读设置和移动端阅读界面。

- 网站：[paper.zhouhao.cn](https://paper.zhouhao.cn/)
- 仓库：[haozic/paper](https://github.com/haozic/paper)
- 更新采集说明：[scripts/README.md](scripts/README.md)

## 阅读与检索

首页展示四本刊物和讲话库。四刊按年、期次和栏目浏览；讲话库按年份浏览。文章页支持目录、上一篇或下一篇、相关阅读、收藏、分享、字号、行距、页宽、首行缩进、纸张和主题设置。收藏和阅读设置保存在当前浏览器的 `localStorage` 中，不会跨设备同步。

首页及目录页使用同一搜索弹层。默认检索四刊标题与讲话库标题、副标题；选择单个来源后，可进一步搜索正文。讲话库正文检索会在用户点击“进一步搜正文”后按年份加载索引，不会在打开首页时下载全部正文。

讲话库与四刊共用首页路由：

```text
/#m=qs                  《求是》目录
/#m=speeches            讲话库目录
/#m=speeches&a=ARTI...  讲话库文章
/#m=speeches&about      从讲话库进入全站关于页
```

## 数据范围

以下是 2026 年 11 月 23 日仓库数据的快照；最新数据请查看网站首页和 `data/counts.json`。

| 来源 | 覆盖范围 | 文章 | 期数 |
| --- | --- | ---: | ---: |
| 《求是》 | 2019 年第 1 期至 2026 年第 22 期 | 3,444 | 190 |
| 《红旗文稿》 | 2020 年第 1 期至 2026 年第 21 期 | 2,277 | 165 |
| 《党建研究》 | 2020 年第 12 期至 2026 年第 10 期 | 1,748 | 71 |
| 《旗帜》 | 2021 年第 7 期至 2026 年第 6 期 | 2,223 | 60 |
| 习近平讲话库 | 2012—2026 年 | 1,540 | 按年浏览 |

讲话库有 1,535 篇已归档正文、5 篇官网原文暂不可读取。部分刊物旧文章也缺少可读取的全文；目录仍保留这些条目，并提供官网来源信息。

## 项目结构

```text
index.html                         首页、四刊目录与阅读页、全站搜索和关于页
assets/js/app.js                   首页路由、四刊阅读及全站搜索
speeches/shell.txt                 按需加载的讲话库界面
speeches/speeches.js               讲话库目录与阅读逻辑
assets/css/{style,books,one,system,modern}.css  样式源码
assets/css/site.css                由五份样式源码生成的发布文件
data/{meta.json,qs/,hqwg/,qz/}    四刊目录与按期正文数据
data/search_index.json             四刊标题索引
data/speeches/index.json           讲话库目录
data/speeches/body_search/         按年分片的讲话库正文索引
articles/speeches/                 讲话库 Markdown 正文
functions/share/index.js           四刊文章的分享预览页
_routes.json                       限定 Pages Function 只处理分享路径
sw.js                              应用外壳与已读数据的离线缓存
scripts/                           抓取、构建与数据检查脚本
.github/workflows/quality.yml      推送和 PR 的质量检查
```

四刊正文主要存于 `data/<刊物>/issues/`；讲话库正文依赖 `articles/speeches/`。部署时需保留整个 `data/`、`articles/speeches/`、`speeches/`、`functions/` 和根目录配置文件。

## 本地运行

这是静态网站，无需前端打包。推荐使用 Python 3.11+ 和 Node.js 22+；本地启动 HTTP 服务：

```bash
python -m http.server 8765
```

然后访问 `http://localhost:8765/`。直接通过 `file://` 打开会使浏览器的 `fetch()` 无法正常读取目录和正文。

修改任一份样式源码后，重建发布文件：

```bash
python scripts/build_styles.py
python scripts/build_styles.py --check
```

## 更新内容

四刊抓取步骤、期次参数和正文修复方法见 [采集脚本说明](scripts/README.md)。抓取脚本需要 `requests` 与 `beautifulsoup4`；纯数据检查和构建脚本不依赖这两个包。

GitHub Actions 的 [Update official content](.github/workflows/auto-update.yml) 每天北京时间 09:17、20:17 自动检查四刊和讲话库官网目录。发现新增内容后，它会抓取、重建索引、更新页面日期与缓存版本，通过数据和脚本检查后提交到 `main`，再由 Cloudflare Pages 的 Git 集成发布；无更新时不提交。抓取或校验失败会使任务失败，不发布部分结果。也可在 GitHub 仓库的 **Actions → Update official content → Run workflow** 手动运行，或本地只读检查：

```bash
python scripts/auto_update.py --check-only
```

需要只在内容更新后收到 QQ 邮件时，到仓库 **Settings → Secrets and variables → Actions** 配置：

- **Secrets**：`UPDATE_MAIL_USER` 填发件 QQ 邮箱地址，`UPDATE_MAIL_PASSWORD` 填该邮箱开启 SMTP 后生成的授权码（不是登录密码）。若收件邮箱不同，再设置可选的 `UPDATE_MAIL_TO`；默认发给同一个邮箱。
- **Variables**：`UPDATE_MAIL_ENABLED` 设为 `true`。未开启时自动更新照常运行，不尝试发邮件。可选的 `UPDATE_MAIL_PORT` 默认为 465；若该端口在运行环境中无法完成发信，可设为 587（STARTTLS）。

工作流只有在新增内容通过检查、提交且推送成功后才发一封摘要邮件，列出新增文章及提交、运行记录链接；没有新增内容时不发送。发信使用 `smtp.qq.com:465` 的加密连接，授权码只由 Actions Secrets 注入。若邮件发送失败，已推送的内容不会回滚，运行记录会显示失败以便排查。
首次配置后，可在 **Actions → Update official content → Run workflow** 勾选 `test_email` 手动测试一次；若本次同时发现新文章，只发送真实更新摘要，不会重复发送测试邮件。

《旗帜》新期的文章与目录可自动更新；官网档案页没有可直接使用的封面，首页封面仍需人工核对并替换。GitHub 定时任务可能延迟；公开仓库连续 60 天无活动时，GitHub 会停用定时任务，届时需在 Actions 页面重新启用。

讲话库从[共产党员网官方目录](https://www.12371.cn/special/xxzd/jh/)采集。更新讲话库目录或文章后，必须重建正文索引：

```bash
python scripts/scrape_speeches.py
python scripts/build_speech_body_search.py
python scripts/check_speeches.py
python scripts/build_speech_body_search.py --check
```

若只需修复已存档讲话正文的乱码，可运行 `python scripts/scrape_speeches.py --repair-encoding`，再重建正文索引并执行上述检查。修复模式只从共产党员网原文重新抓取识别出的异常正文，不改动目录。

四刊元数据更新后，重建跨刊标题索引并检查数据：

```bash
python scripts/build_search_index.py
python scripts/check_data.py
python scripts/build_search_index.py --check
```

发布样式或脚本修改时，同步更新 `index.html`、`assets/js/app.js`、`speeches/speeches.js`、`speeches/shell.txt` 和 `sw.js` 中使用的资源版本号；缓存与发布细节见 [更新流程](docs/UPDATE_FLOW.md)。

## 部署与质量检查

当前网站由 GitHub `main` 分支连接 Cloudflare Pages 自动部署。站点从仓库根目录发布，框架预设为 None，无前端构建命令。`wrangler.jsonc` 将静态资源目录设为 `.`；`functions/share/index.js` 与 `_routes.json` 为四刊文章提供带标题的分享预览。

提交前可运行与 [GitHub Actions](.github/workflows/quality.yml) 相同的核心检查：

```bash
python scripts/check_data.py
python scripts/build_search_index.py --check
python scripts/check_speeches.py
python scripts/build_speech_body_search.py --check
python scripts/build_styles.py --check
node --check assets/js/app.js
node --check speeches/speeches.js
node --check sw.js
node --test scripts/test_reading_progress.js
```

网站通过 Service Worker 缓存应用外壳和已读正文。`_headers` 为静态数据设置长期缓存，因此更新数据或脚本时需同步升级资源版本。访问控制与部署注意事项见 [访问控制文档](docs/ACCESS_CONTROL.md)。

## 更多文档

- [站点架构](docs/ARCHITECTURE.md)
- [内容更新流程](docs/UPDATE_FLOW.md)
- [采集脚本说明](scripts/README.md)
- [阅读体验设计记录](docs/UX_MODERNIZATION.md)

本站代码与文章内容的权利归属不同；收录文章的版权归原作者及出版方。请通过文章中的来源链接核对原文。
