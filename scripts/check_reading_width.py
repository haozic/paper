#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阅读页宽度（页宽 / 页边距）体检。

为什么要有这个脚本
------------------
2026-10-30 用户反馈"正文阅读页调整页边距的按钮没有反应"。查下来事件绑定、
变量写入、按钮高亮全都没问题，根因在 CSS 表达方式：

    .article-page-body {
        max-width: calc(var(--article-w-base) + var(--article-w-delta));  /* 860px ± */
        box-sizing: border-box;
    }

窄视口下元素宽被视口顶住，max-width 根本不生效：
    视口 799px，基准 860px
      窄 (-80)  → max-width 780px → 元素 780px → 正文 684px
      标准 (0)  → max-width 860px → 元素 799px → 正文 703px
      宽 (+120) → max-width 980px → 元素 799px → 正文 703px  ← 与标准像素级相同
手机上（375px）三档全部 0 变化。也就是说"宽"这一档是**死档**，
点下去没有任何视觉变化，又不报错、不白屏，肉眼很难归因。

现在改成双机制：
    1) --article-gutter 控制左右留白（用户说的"页边距"），三档硬拉开差异；
    2) --article-w-delta 控制 max-width，宽屏上继续调整整栏宽度。
两套一起，任何视口宽度下三档都能看出差别。

这个脚本把"三档必须产生不同的正文宽度"变成可断言的规则，并带反向自检，
证明它对"只有 max-width"的旧写法确实会报错（避免体检本身变成摆设）。

用法
----
    python -u scripts/check_reading_width.py            # 体检
    python -u scripts/check_reading_width.py --self-test # 反向自检
"""

import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = __file__.rsplit("scripts", 1)[0]
CSS_PATH = ROOT + "assets/css/style.css"
HTML_PATH = ROOT + "index.html"

# 参与"正文栏"的四个容器：横向留白与栏宽必须四者一致，否则改档位时会错位
CONTAINERS = [".article-page-body", ".ap-header-inner", ".ap-continue", ".article-page-footer"]

# 代表性视口宽度（移动端小屏 / 常见手机 / 平板 / 桌面 / 大屏）
VIEWPORTS = [320, 375, 414, 639, 767, 768, 1024, 1280, 1440, 1920]

# 正文宽下限：窄档也不能窄到读不了
MIN_CONTENT_WIDTH = 200


def strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def media_768_blocks(css):
    """取出所有 @media (min-width: 768px) 块的内部文本（花括号配对）。"""
    out = []
    for m in re.finditer(r"@media\s*\(\s*min-width\s*:\s*768px\s*\)", css):
        i = css.find("{", m.end())
        if i < 0:
            continue
        depth = 0
        for j in range(i, len(css)):
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    out.append(css[i + 1:j])
                    break
    return out


def root_var(scope, name):
    """在给定 CSS 作用域里取 :root 声明的变量值（返回数字或 None）。"""
    for m in re.finditer(r":root\s*\{([^}]*)\}", scope):
        mm = re.search(re.escape(name) + r"\s*:\s*(-?[\d.]+)px", m.group(1))
        if mm:
            return float(mm.group(1))
    return None


def attr_var(scope, attr, name):
    """取 html[data-article-width="attr"] 声明的变量值。"""
    pat = r'html\[data-article-width\s*=\s*"' + re.escape(attr) + r'"\]\s*\{([^}]*)\}'
    for m in re.finditer(pat, scope):
        mm = re.search(re.escape(name) + r"\s*:\s*(-?[\d.]+)px", m.group(1))
        if mm:
            return float(mm.group(1))
    return None


def rule_blocks(css, selector):
    """取某个选择器的所有规则块内容。"""
    pat = re.escape(selector) + r"\s*(?:,[^{]*)?\{([^}]*)\}"
    return re.findall(pat, css)


def parse_deltas(html):
    """从 index.html 的页宽按钮上读出三档偏移值（窄/标准/宽）。"""
    deltas = {}
    for m in re.finditer(r'data-w="(-?\d+)"', html):
        d = int(m.group(1))
        key = "narrow" if d < 0 else ("wide" if d > 0 else "standard")
        deltas[key] = d
    return deltas


def content_width(viewport, max_width, gutter):
    """正文实际宽度：元素宽 = min(视口, max-width)，再减去左右留白。"""
    return min(viewport, max_width) - 2 * gutter


def check(css, html):
    """返回错误列表（空列表 = 通过）。"""
    errors = []
    css = strip_comments(css)

    # --- 1. 不得使用 Chrome 69 不支持的 min()/clamp() ---
    for fn in ("min(", "clamp("):
        if fn in css:
            errors.append("style.css 使用了 Chrome 69 不支持的 %s），请改用媒体查询分段" % fn)

    # --- 2. --article-gutter 必须在三档都定义 ---
    base_gutter = root_var(css, "--article-gutter")
    if base_gutter is None:
        errors.append(":root 未定义 --article-gutter（页边距变量缺失，页宽档位会退化成死档）")
        return errors  # 变量都没有，后面的算式没法算

    media = "\n".join(media_768_blocks(css))
    desk_gutter = root_var(media, "--article-gutter")
    if desk_gutter is None:
        desk_gutter = base_gutter

    gutters = {
        "standard": (base_gutter, desk_gutter),
        "narrow": (attr_var(css, "narrow", "--article-gutter"),
                   attr_var(media, "narrow", "--article-gutter")),
        "wide": (attr_var(css, "wide", "--article-gutter"),
                 attr_var(media, "wide", "--article-gutter")),
    }
    for key, (mob, desk) in gutters.items():
        if mob is None:
            errors.append('html[data-article-width="%s"] 未定义 --article-gutter（%s 档会退化成死档）' % (key, key))
        if desk is None:
            errors.append('@media (min-width:768px) 内 html[data-article-width="%s"] 未定义 --article-gutter' % key)

    base_w = root_var(css, "--article-w-base")
    desk_w = root_var(media, "--article-w-base")
    if base_w is None:
        errors.append(":root 未定义 --article-w-base")
        return errors
    if desk_w is None:
        desk_w = base_w

    # --- 3. 四个容器都要用同一套留白与栏宽 ---
    for sel in CONTAINERS:
        blocks = rule_blocks(css, sel)
        if not blocks:
            errors.append("style.css 缺少 %s 规则" % sel)
            continue
        ok_pad = False
        ok_max = False
        for b in blocks:
            if "var(--article-gutter" in b:
                ok_pad = True
            if "calc(var(--article-w-base" in b and "var(--article-w-delta" in b:
                ok_max = True
        if not ok_pad:
            errors.append("%s 的横向留白没有取自 var(--article-gutter)，改档位时会与正文错位" % sel)
        if not ok_max:
            errors.append("%s 的 max-width 不是 calc(var(--article-w-base) + var(--article-w-delta))" % sel)

    # --- 4. 三档在每个视口下都必须产生不同的正文宽度 ---
    deltas = parse_deltas(html)
    if set(deltas) != {"narrow", "standard", "wide"}:
        errors.append("index.html 的页宽按钮档位不全，读到 %s" % sorted(deltas))
        return errors

    for vw in VIEWPORTS:
        desktop = vw >= 768
        w_base = desk_w if desktop else base_w
        widths = {}
        for key in ("narrow", "standard", "wide"):
            mob, desk = gutters[key]
            gutter = desk if desktop else mob
            if gutter is None:
                continue
            widths[key] = content_width(vw, w_base + deltas[key], gutter)
        if len(widths) < 3:
            continue
        if len(set(widths.values())) != 3:
            errors.append("视口 %dpx 下三档正文宽度相同（%s），存在点了没反应的'死档'"
                          % (vw, widths))
        if not (widths["narrow"] < widths["standard"] < widths["wide"]):
            errors.append("视口 %dpx 下三档宽度不是'窄<标准<宽'单调递增：%s" % (vw, widths))
        if widths["narrow"] < MIN_CONTENT_WIDTH:
            errors.append("视口 %dpx 下窄档正文只有 %dpx，太窄读不了" % (vw, widths["narrow"]))

    return errors


OLD_CSS = """
:root {
    --article-w-base: 760px;
    --article-w-delta: 0px;
}
@media (min-width: 768px) {
    :root { --article-w-base: 860px; }
}
.article-page-body {
    max-width: calc(var(--article-w-base) + var(--article-w-delta));
    padding: 24px 18px 56px;
}
.ap-continue {
    max-width: calc(var(--article-w-base) + var(--article-w-delta));
    padding: 10px 18px;
}
.article-page-footer {
    max-width: calc(var(--article-w-base) + var(--article-w-delta));
    padding: 0 18px 72px;
}
"""

OLD_HTML = """
<button class="asp-btn" data-w="-80">窄</button>
<button class="asp-btn" data-w="0">标准</button>
<button class="asp-btn" data-w="120">宽</button>
"""

# 第二种旧写法：留白变量有了，但三档共用同一个值 —— 窄视口下三档宽度依然相同
DEAD_GUTTER_CSS = """
:root {
    --article-w-base: 760px;
    --article-w-delta: 0px;
    --article-gutter: 18px;
}
html[data-article-width="narrow"] { --article-gutter: 18px; }
html[data-article-width="wide"]   { --article-gutter: 18px; }
@media (min-width: 768px) {
    :root { --article-w-base: 860px; --article-gutter: 48px; }
    html[data-article-width="narrow"] { --article-gutter: 48px; }
    html[data-article-width="wide"]   { --article-gutter: 48px; }
}
.article-page-body {
    max-width: calc(var(--article-w-base) + var(--article-w-delta));
    padding: 24px var(--article-gutter, 18px) 56px;
}
.ap-header-inner {
    max-width: calc(var(--article-w-base) + var(--article-w-delta));
    padding: 0 var(--article-gutter, 18px);
}
.ap-continue {
    max-width: calc(var(--article-w-base) + var(--article-w-delta));
    padding: 10px var(--article-gutter, 18px);
}
.article-page-footer {
    max-width: calc(var(--article-w-base) + var(--article-w-delta));
    padding: 0 var(--article-gutter, 18px) 72px;
}
"""


def self_test():
    """反向自检：拿两种"死档"写法喂进去，必须报错。"""
    print("=" * 68)
    print("反向自检（证明体检对'死档'写法有鉴别力）")
    print("=" * 68)
    passed = True

    cases = [
        ("旧写法：完全没有 --article-gutter（只有 max-width）", OLD_CSS, OLD_HTML),
        ("死档写法：三档共用同一个留白，窄视口下宽度仍然相同", DEAD_GUTTER_CSS, OLD_HTML),
    ]
    for title, css, html in cases:
        errs = check(css, html)
        if errs:
            print("  OK   %s → 判定为错误（%d 条）" % (title, len(errs)))
            for e in errs[:2]:
                print("         - " + e)
        else:
            print("  FAIL %s → 竟然通过了体检，这个体检没有鉴别力" % title)
            passed = False
    print("  %s 反向自检" % ("OK  " if passed else "FAIL"))
    return 0 if passed else 1


def main():
    if "--self-test" in sys.argv:
        return self_test()

    print("=" * 68)
    print("阅读页宽度（页宽 / 页边距）体检")
    print("=" * 68)
    with open(CSS_PATH, encoding="utf-8") as f:
        css = f.read()
    with open(HTML_PATH, encoding="utf-8") as f:
        html = f.read()

    errors = check(css, html)
    if errors:
        print("❌ 发现 %d 个问题：" % len(errors))
        for e in errors:
            print("   - " + e)
        return 1

    print("✅ 三档页宽/页边距在所有代表性视口下均产生不同宽度，且容器对齐一致")
    print("✅ 未使用 Chrome 69 不支持的 min()/clamp()")
    return 0


if __name__ == "__main__":
    sys.exit(main())
