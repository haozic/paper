# 交接记录

## 2026-11-01：精简独立 demo 的重复元素与导航

### 当前任务与已完成

用户指出 demo 首页和杂志目录有大量重复元素，且“正文”不应出现在顶部导航。已直接修改 `design-demo/index.html`：首页只留站点名与三本完整封面；去掉标题、英文副标题、封面下重复刊名与底部引导；杂志页仅保留一次刊名、一次期号及文章列表，去掉重复的面包屑、期号注释和每行出处；移除顶部首页/杂志/正文预览切页导航。实际路径为封面 → 杂志目录 → 文章，站点名返回首页，文章出处返回杂志目录。手机杂志页省去再次展示封面，让目录更早出现。同步更新 README 与预览图。

### 验收、卡点和下一步

- Playwright 单次脚本检查：设置面板打开、字号调到 22px、正文目录第二篇可跳转、390px 手机无水平溢出；重拍并检查首页、杂志页、正文页的桌面与手机截图。内联 JS `node --check`、CSS `tinycss2` 和封面路径检查通过。
- 正式站点尚未改造；demo 的内容仍是示意，真实站点登录门与本地浏览器限制同下文。下一步若用户认可新版 demo，再按此路径接入正式站点。
- 本轮新版 demo 与交接文档通过 GitHub `main` 同步，交付时核对本地与远端提交号。

### 踩过的坑

- 预览用的顶部切页导航会被误认为正式网站结构，因此 demo 应让用户按实际阅读路径操作，不能增加仅为演示方便而在产品中不存在的入口。
- 手机杂志页若同时显示刊名、大封面和期号，文章列表会被推到首屏以下；此次在手机端保留首页封面，进入刊物后直接显示目录。

---

## 2026-11-01：网站视觉方向调研与独立 demo

### 当前任务

用户认为现站仍不够现代，要求调研 GitHub 模板与知名阅读网站、博客，说明改造方向并提供可看的 demo。本轮选择先交付独立的交互视觉稿，尚未把样式应用到正式站点。

### 已完成

- 对比 The New Yorker、The Paris Review、ONE、Readwise Reader，以及 AstroPaper、PaperMod、QuietPages、Broadsheet；结论是按“完整封面 → 当期目录 → 单栏正文”建立三刊专属层级，沿用系统字体与现有静态架构。
- 新增 `design-demo/index.html`：可切换首页、杂志页、正文页；杂志目录、板块、收藏示意；正文目录、字号与纸张调整、下一篇示意。封面取用现有三张图片；文章文案均明确标为排版示意。
- 新增 `design-demo/README.md`，包含调研链接、取舍与 demo 范围；`design-demo/previews/` 内提供桌面与手机预览图。
- Playwright 桌面 1440px 与手机 390px 截图已检查；设置面板可见、字号变为 22px、暖色纸张生效、手机无水平溢出。`node --check` 检查内联 JS、`tinycss2` 解析 CSS、三张封面路径检查通过。

### 卡住的问题与下一步

- 正式站点有登录门，当前环境不能访问本地 HTTP 或 `file:` 页面进行真实站点验收；本轮只验证独立 demo。若用户认可视觉方向，下一步把设计逐页接入正式首页、杂志页和正文页，保留现有检索、收藏、离线和部署结构，再做真实页面验收。
- 独立 demo 与交接文档已提交并推送到 GitHub `main`（`5e27161`）；远端提交号已核对。下一步等用户对 demo 方向提出具体意见，再决定正式站点的视觉落地。

### 踩过的坑

- `playwright-cli` 的跨命令会话在该环境下没有可靠地保留页面状态，分别点选后截图曾得到三张完全相同的首页图。后来改为在单次 `run-code` 中 `page.setContent()`、点选、逐页截图；完成后清理了临时脚本和 `.playwright-cli` 输出。
- 因浏览器限制本地 HTTP 与 `file:`，Playwright 用 `setContent()` 并嵌入现有封面图片数据做视觉核对。这不等于正式站点端到端验收。

---

## 当前任务

党内刊物静态阅读网站通过 GitHub `main` 与 Cloudflare Pages 部署。本轮用户要求把正文页右下角导航按钮展开的文字菜单改为向左弹出的两个同尺寸并列图标，分别去网站首页和当前杂志首页。用户此前要求直接做完并同步 GitHub。

## 本轮已完成

- 阅读页右下角导航展开项由文字浮层改为两个并列圆形图标，尺寸与导航圆钮相同，向左弹出。房屋图标进入网站首页，书本图标进入当前杂志首页。
- 图标按钮保留 `title` 和 `aria-label`，不在页面显示文字；保留原有的阅读位置保存、点击外部和 Escape 关闭逻辑。
- 展开采用轻微的向左进入动画；系统要求减少动态效果时关闭动画。资源版本更新为 `20261101t`。

## 验收与限制

- `tinycss2` 解析 CSS 无错误；`node --check assets/js/app.js`、`node --check sw.js`、`git -c core.whitespace=cr-at-eol diff --check` 通过。
- Playwright 浏览器在本环境禁止本地 HTTP (`net::ERR_NETWORK_ACCESS_DENIED`) 和 `file:` 协议，无法完成真实页面截图。此前移除访问门做视觉核对被自动审批拒绝，不绕过。
- 旧数据问题：红旗文稿 1 篇标记有全文但正文缺失；党建研究 2026 年第 10 期目录有 31 篇文章但正文分片缺失。本轮未改数据。

## 下一步

- 如能在真实浏览器访问登录后的文章页，核对四个右下角图标的间距、窄屏宽度及触控操作。

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
- 返回顶部按钮的旧样式分散在 `style.css`、`books.css`、`one.css`、`system.css`，最终位置必须在最后加载的 `system.css` 覆盖。底栏固定在页面底部，新导航圆钮放在其上方，返回顶部再上移，不能简单把导航往底栏下方放。
