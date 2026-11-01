# 三刊阅读视觉方向预览

这是独立于正式站点的交互示意。打开 `index.html` 可切换首页、杂志页与正文页。封面使用项目现有图片；文章标题、正文和收藏列表只用于展示排版，并非正式刊物数据。

桌面预览：[首页](previews/demo-home.jpg) · [杂志页](previews/demo-magazine.jpg) · [正文页](previews/demo-reading.jpg)；手机预览：[首页](previews/demo-mobile-home.jpg) · [正文页](previews/demo-mobile-reading.jpg)。

## 调研结论

| 参考 | 值得借鉴 | 不直接照搬的部分 |
| --- | --- | --- |
| [The New Yorker 的期刊档案](https://www.newyorker.com/archive) | 以最新一期、年份、期号建立阅读路径 | 大型新闻站的栏目和商业入口过多 |
| [The Paris Review 的期刊归档](https://www.theparisreview.org/back-issues) | 把封面和期号当作出版物的核心标识 | 其英文艺术刊物的字形与封面语言不适合直接迁移 |
| [ONE · 一个](https://wufazhuce.com/) | 减少首页文本与控件，让内容成为视觉主角 | 每日单篇模式不同于三刊、逐期的资料结构 |
| [Readwise Reader 的长文模式](https://docs.readwise.io/reader/guides/workflows/longform-reading) | 长文阅读时降低工具栏存在感，阅读设置按需出现 | 不需要迁移它的完整阅读工作流 |
| [Broadsheet](https://github.com/xyovo/broadsheet) | 中文报刊式标题层级、目录与文章索引 | 报纸首页的多栏密度不适合三本刊物封面 |
| [QuietPages](https://github.com/xocothemes/quietpages) | 独立刊物的归档、文章结构与克制的编辑感 | 现成的博客内容模型、字体和依赖都不适合直接套用 |
| [AstroPaper](https://github.com/satnaing/astro-paper) | 静态搜索、目录、无障碍和阅读页信息组织 | 当前网站已有静态数据与检索，不值得只为换外观重建框架 |
| [Hugo PaperMod](https://github.com/adityatelange/hugo-PaperMod) | 简洁、快速的博客导航和正文布局 | 对“刊物 → 年份 → 期号 → 文章”的四层结构支持不足 |

## 建议采用的方向

**当代期刊书架**：首页让三本完整封面承担主视觉；杂志页用大刊名、当期封面和连续文章索引形成清楚的层次；正文页保持单栏阅读，工具收进轻面板。全站使用系统字体与相同的纸色、墨色、细线和小幅暗红点缀。

优先改变布局秩序和间距，不增加装饰。尤其要控制正文行宽、封面比例与目录密度。正式实现时沿用现有数据、搜索、收藏、离线与 GitHub/Cloudflare Pages 部署结构，逐页替换样式和必要交互即可。

## Demo 范围

- 三页可切换，首页封面可进入对应刊物。
- 杂志页可切换目录、板块和收藏示意列表，文章行可进入阅读页。
- 阅读页可切换目录、字号和纸张底色，并可进入下一篇示意文章。
- 手机与桌面使用同一份 HTML/CSS；无框架、无远程字体或运行时依赖。

本预览用于确认视觉方向。它没有接入正式站点的真实目录、文章或登录门，不能替代功能验收。
