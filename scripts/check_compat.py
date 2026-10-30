#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Chrome 69 兼容性体检

为什么需要这个脚本
------------------
站点承诺支持 Chrome 69（2018 年）。历史上出现过三次静默回归：

  1. UI 重写把 flex `gap` 全面引入，而 Chrome 84 才支持 flex 的 gap
     → 所有横向/纵向间距在旧浏览器上消失；
  2. 旧版 "Chrome 69 Gap Fallback" 段里选择器漏写前导点（`magazine-grid` 而不是
     `.magazine-grid`），规则从未匹配过任何元素，等于没有兜底；
  3. 访问密码门用了 `inset: 0` 简写（Chrome 87+）→ Chrome 69 上遮罩层塌陷成 0 尺寸，
     又因 `body.gate-active { overflow: hidden }` 锁死滚动 → 白屏且滚不动。

本脚本做三类检查：

  A. 特性黑名单：逐条规则块检查是否用了 Chrome 69 不支持的 CSS/JS 特性，
     并识别同规则内（或同文件 @supports 兜底块内）已有的等价旧写法，避免误报。
  B. flex gap 兜底：任何 `display:flex` + `gap` 的容器，都必须在同文件的
     `@supports not (aspect-ratio: ...)` 兜底块里出现等价间距，否则 Chrome 69 上
     间距直接消失（这是第 1、2 条回归的根因）。
  C. 扫描范围：CSS 文件、HTML 内联 <style> 块、JS 文件（含 HTML 内联脚本）。

用法：
  python scripts/check_compat.py            # 检查，有问题返回非 0 退出码
  python scripts/check_compat.py --list     # 顺便打印特性清单与各版本要求

维护方式：往 FEATURES 表里加一行即可，格式为 (类别, 正则, 说明, 引入版本)。
"""

import os
import re
import sys

# Windows 控制台默认 GBK，直接打印 emoji / 中文会抛 UnicodeEncodeError。
# 统一把 stdout 切到 UTF-8，并对无法编码的字符降级为占位符。
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, ValueError):      # Python < 3.7 / 非标准流
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (类别, 正则, 说明, 引入版本)
FEATURES = [
    # ---- CSS 属性 ----
    ('CSS 属性', r'(?<![\w-])inset\s*:', 'inset 简写', 'Chrome 87'),
    ('CSS 属性', r'(?<![\w-])inset-(inline|block)\s*:', 'inset-inline/block 逻辑属性', 'Chrome 87'),
    ('CSS 属性', r'(?<![\w-])accent-color\s*:', 'accent-color 表单控件配色', 'Chrome 93'),
    ('CSS 属性', r'(?<![\w-])content-visibility\s*:', 'content-visibility 渲染跳过', 'Chrome 85'),
    ('CSS 属性', r'(?<![\w-])scrollbar-gutter\s*:', 'scrollbar-gutter 滚动条占位', 'Chrome 94'),
    ('CSS 属性', r'(?<![\w-])text-wrap\s*:', 'text-wrap 换行控制', 'Chrome 114'),
    ('CSS 属性', r'(?<![\w-])text-underline-offset\s*:', 'text-underline-offset', 'Chrome 89'),
    ('CSS 属性', r'(?<![\w-])text-decoration-skip-ink\s*:', 'text-decoration-skip-ink', 'Chrome 89'),
    ('CSS 属性', r'(?<![\w-])line-clamp\s*:', 'line-clamp 标准写法（需 -webkit- 前缀）', 'Chrome 120'),
    ('CSS 属性', r'(?<![\w-])background-clip\s*:\s*text', 'background-clip: text', 'Chrome 120'),
    ('CSS 属性', r'(?<![\w-])color-mix\s*\(', 'color-mix() 颜色函数', 'Chrome 111'),
    ('CSS 属性', r'(?<![\w-])(oklch|oklab|lab|lch)\s*\(', 'oklch()/lab() 现代色彩空间', 'Chrome 111'),
    ('CSS 属性', r'(?<![\w.-])((min|max|clamp)\s*\(\s*[\d.]+(px|rem|em|vw|vh|%))', 'CSS 数学函数 min()/max()/clamp()', 'Chrome 79'),
    ('CSS 属性', r'(?<![\w-])(dvh|svh|lvh|dvw|svw|lvw)\b', '动态视口单位 dvh/svh/lvh', 'Chrome 108'),
    ('CSS 属性', r'(?<![\w-])backdrop-filter\s*:', 'backdrop-filter 毛玻璃', 'Chrome 76'),
    ('CSS 属性', r'(?<![\w-])aspect-ratio\s*:', 'aspect-ratio 宽高比', 'Chrome 88'),
    ('CSS 属性', r'(?<![\w-])appearance\s*:', 'appearance 简写', 'Chrome 84'),

    # ---- CSS 选择器 / at-rule ----
    ('CSS 选择器', r':has\s*\(', ':has() 父选择器', 'Chrome 105'),
    ('CSS 选择器', r':is\s*\(', ':is() 匹配列表', 'Chrome 88'),
    ('CSS 选择器', r':where\s*\(', ':where() 匹配列表', 'Chrome 88'),
    ('CSS 选择器', r':focus-visible', ':focus-visible 焦点样式', 'Chrome 86'),
    ('CSS 选择器', r'::marker', '::marker 列表标记', 'Chrome 86'),
    ('CSS at-rule', r'@container\b', '@container 容器查询', 'Chrome 105'),
    ('CSS at-rule', r'@layer\b', '@layer 级联层', 'Chrome 99'),

    # ---- JS 语法 ----
    ('JS 语法', r'\?\.', '可选链 ?.', 'Chrome 80'),
    ('JS 语法', r'(?<![?+])\?\?(?![?])', '空值合并 ??', 'Chrome 80'),
    ('JS 语法', r'\|\|=|&&=|\?\?=', '逻辑赋值 ||= &&= ??=', 'Chrome 85'),
    ('JS 语法', r'(?<![\w$#&/])#[A-Za-z_$][\w$]*\s*=(?!=)', '类私有字段', 'Chrome 74'),

    # ---- JS 运行时 API ----
    ('JS API', r'Object\.fromEntries\b', 'Object.fromEntries', 'Chrome 73'),
    ('JS API', r'\.matchAll\s*\(', 'String.prototype.matchAll', 'Chrome 73'),
    ('JS API', r'\.replaceAll\s*\(', 'String.prototype.replaceAll', 'Chrome 85'),
    ('JS API', r'structuredClone\s*\(', 'structuredClone', 'Chrome 98'),
    ('JS API', r'\bglobalThis\b', 'globalThis', 'Chrome 71'),
    ('JS API', r'randomUUID\s*\(', 'crypto.randomUUID', 'Chrome 92'),
    ('JS API', r'Promise\.allSettled\b', 'Promise.allSettled', 'Chrome 76'),
    ('JS API', r'Promise\.any\b', 'Promise.any', 'Chrome 85'),
    ('JS API', r'Object\.hasOwn\b', 'Object.hasOwn', 'Chrome 93'),
    ('JS API', r'\.replaceChildren\s*\(', 'Element.replaceChildren', 'Chrome 86'),
    ('JS API', r'\.at\s*\(\s*-', 'Array/String.prototype.at', 'Chrome 92'),
    ('JS API', r'\.findLast(Index)?\s*\(', 'Array.prototype.findLast', 'Chrome 97'),
    ('JS API', r'Intl\.(ListFormat|RelativeTimeFormat|Segmenter)', 'Intl 新增格式化 API', 'Chrome 71'),
    ('JS API', r'URL\.canParse\b', 'URL.canParse', 'Chrome 109'),
    ('JS API', r'\bWeakRef\b', 'WeakRef', 'Chrome 84'),
    ('JS API', r'navigator\.gpu\b', 'WebGPU', 'Chrome 113'),
]

# 同一规则块内出现这些写法即视为已兜底
RULE_FALLBACKS = [
    (r'(?<![\w-])inset\s*:', r'(?<![\w-])(top|right|bottom|left)\s*:'),
    (r'(?<![\w-])appearance\s*:', r'-webkit-appearance\s*:'),
    (r'(?<![\w-])backdrop-filter\s*:', r'-webkit-backdrop-filter\s*:'),
]

# 整份文件里出现即视为已兜底
FILE_FALLBACKS = [
    (r'(?<![\w-])aspect-ratio\s*:', r'@supports\s+not\s*\(\s*aspect-ratio'),
    (r':has\s*\(', r'\.checked'),          # 由 JS 同步 .checked 类
]

SKIP_DIR = re.compile(r'(node_modules|__pycache__|\.git)')


# ---------------------------------------------------------------- 工具函数

def strip_js_strings(line):
    """把字符串字面量内容抹成空串，避免把 URL/锚点里的字符当成语法特性。

    例：history.pushState({}, '', `#m=${key}`) 里的 `#m=` 不是类私有字段。
    """
    out = []
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if ch in '\'"`':
            quote = ch
            i += 1
            while i < n:
                if line[i] == '\\':
                    i += 2
                    continue
                if line[i] == quote:
                    i += 1
                    break
                i += 1
            out.append('""')
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def strip_js_comments(line):
    """去掉行尾 // 注释（字符串已在前面剥离，所以不会误伤 URL 里的 //）。"""
    i = line.find('//')
    if i < 0:
        return line
    # 排除 http:// 这种（字符串剥离后 URL 已变成 ""，这里再兜一层）
    if i > 0 and line[i - 1] == ':':
        return line
    return line[:i]


def css_rules(text):
    """产出 (选择器, 声明块, 起始行号)，跳过 @ 开头的作用域声明。"""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    out = []
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', text):
        sel = ' '.join(m.group(1).split())
        body = m.group(2)
        if not sel or sel.startswith('@'):
            continue
        line = text.count('\n', 0, m.start()) + 1
        out.append((sel, body, line))
    return out


def extract_supports_blocks(css):
    """取出所有 @supports ... { ... } 的内部文本（用于判断兜底覆盖）。"""
    blocks = []
    for m in re.finditer(r'@supports[^{]*\{', css):
        depth = 1
        i = m.end()
        start = i
        while i < len(css) and depth:
            if css[i] == '{':
                depth += 1
            elif css[i] == '}':
                depth -= 1
            i += 1
        blocks.append(css[start:i - 1])
    return blocks


def last_compound(selector):
    """取选择器最后一段复合选择器，如 '.framework-card .steps' -> '.steps'。"""
    parts = re.split(r'[\s>+~]+', selector.strip())
    return parts[-1] if parts else selector


def strip_supports_blocks(css):
    """把 @supports 块整段移除，避免其内部声明被当成"主规则"。"""
    out = css
    for m in list(re.finditer(r'@supports[^{]*\{', out)):
        depth = 1
        i = m.end()
        while i < len(out) and depth:
            if out[i] == '{':
                depth += 1
            elif out[i] == '}':
                depth -= 1
            i += 1
        out = out[:m.start()] + out[i:]
    return out


# ---------------------------------------------------------------- CSS 检查

def check_css(rel, css, problems, base_line=0):
    """检查一段 CSS 文本。base_line 用于 HTML 内联 <style> 的行号偏移。"""
    # FILE_FALLBACKS 的每一项是 (特性正则, 兜底写法正则)；
    # 这里记录的是"该兜底写法在本文件里是否存在"。
    file_has = [(fpat, bool(re.search(need, css))) for fpat, need in FILE_FALLBACKS]

    for sel, body, line in css_rules(css):
        for cat, pattern, desc, ver in FEATURES:
            if not cat.startswith('CSS'):
                continue
            for m in re.finditer(pattern, body):
                decl_line = body.count('\n', 0, m.start()) + line + base_line
                ok = False
                for fpat, need in RULE_FALLBACKS:
                    if re.search(fpat, body) and re.search(need, body):
                        ok = True
                        break
                if not ok:
                    for fpat, present in file_has:
                        if present and re.search(fpat, m.group(0)):
                            ok = True
                            break
                if ok:
                    continue
                snippet = body.strip().split('\n')[0][:90]
                problems.append((rel, decl_line, cat, desc, ver, snippet))
    return file_has


def check_flex_gap_fallback(rel, css, problems, base_line=0):
    """任何 display:flex + gap 的容器，都必须在同文件的 @supports 兜底块里出现。

    flex 的 gap 需要 Chrome 84+，Chrome 69 上会整体丢失间距。
    """
    supports = extract_supports_blocks(css)
    if not supports:
        covered = set()
    else:
        covered = set()
        for blk in supports:
            for sel, _body, _ln in css_rules(blk):
                for p in sel.split(','):
                    covered.add(last_compound(p.strip()))

    main_css = strip_supports_blocks(css)

    # 收集每个容器的 display 集合与 gap 声明
    displays = {}
    gaps = {}
    for sel, body, line in css_rules(main_css):
        for p in [s.strip() for s in sel.split(',')]:
            key = last_compound(p)
            d = re.search(r'(?<![\w-])display\s*:\s*([\w-]+)', body)
            if d:
                displays.setdefault(key, set()).add(d.group(1))
            g = re.search(r'(?<![\w-])gap\s*:\s*([^;]+)', body)
            if g:
                gaps.setdefault(key, []).append((g.group(1).strip(), line, sel))

    for key, items in sorted(gaps.items()):
        disp = displays.get(key, set())
        if not ({'flex', 'inline-flex'} & disp):
            continue                      # grid 的 gap 自 Chrome 66 起支持，无需兜底
        for val, line, sel in items:
            if val in ('0', '0px', 'normal'):
                continue
            if key in covered:
                continue
            problems.append((
                rel, line + base_line, 'CSS 兜底缺失',
                'flex 容器 %s 用了 gap: %s，但 @supports 兜底块里没有它'
                % (key, val), 'Chrome 84',
                sel[:90],
            ))
            break


# ---------------------------------------------------------------- JS 检查

def check_js(rel, text, problems, base_line=0):
    for i, raw in enumerate(text.split('\n'), 1):
        stripped = raw.strip()
        if stripped.startswith('//') or stripped.startswith('*') or stripped.startswith('<!--'):
            continue
        code = strip_js_comments(strip_js_strings(raw))
        if not code.strip():
            continue
        for cat, pattern, desc, ver in FEATURES:
            if not cat.startswith('JS'):
                continue
            if re.search(pattern, code):
                problems.append((rel, i + base_line, cat, desc, ver, stripped[:90]))


# ---------------------------------------------------------------- 主流程

def iter_files(exts):
    for root, dirs, files in os.walk(BASE_DIR):
        dirs[:] = [d for d in dirs if not SKIP_DIR.search(d)]
        for f in files:
            if os.path.splitext(f)[1].lower() in exts:
                yield os.path.join(root, f)


def rel(p):
    return os.path.relpath(p, BASE_DIR).replace('\\', '/')


def main():
    show_list = '--list' in sys.argv
    problems = []

    css_files = []
    js_files = []
    html_files = []
    for p in iter_files({'.css'}):
        css_files.append(p)
    for p in iter_files({'.js'}):
        js_files.append(p)
    for p in iter_files({'.html', '.htm'}):
        html_files.append(p)

    for p in css_files:
        with open(p, encoding='utf-8') as f:
            css = f.read()
        check_css(rel(p), css, problems)
        check_flex_gap_fallback(rel(p), css, problems)

    for p in js_files:
        with open(p, encoding='utf-8') as f:
            check_js(rel(p), f.read(), problems)

    for p in html_files:
        with open(p, encoding='utf-8') as f:
            html = f.read()
        # 内联 <style>：按 CSS 检查，行号对齐到原文件
        for m in re.finditer(r'<style[^>]*>(.*?)</style>', html, re.S | re.I):
            base_line = html.count('\n', 0, m.start(1))
            check_css(rel(p), m.group(1), problems, base_line)
            check_flex_gap_fallback(rel(p), m.group(1), problems, base_line)
        # 内联 <script>：按 JS 检查
        for m in re.finditer(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html, re.S | re.I):
            base_line = html.count('\n', 0, m.start(1))
            check_js(rel(p), m.group(1), problems, base_line)

    print('=' * 72)
    print('Chrome 69 兼容性体检')
    print('=' * 72)
    print('扫描：%d 个 CSS，%d 个 JS，%d 个 HTML（含内联 style/script）'
          % (len(css_files), len(js_files), len(html_files)))
    print('特性库：%d 条' % len(FEATURES))

    if show_list:
        print('\n---- 特性清单 ----')
        for cat, pattern, desc, ver in FEATURES:
            print('  %-10s %-36s %s' % (cat, desc, ver))

    if problems:
        print('\n发现 %d 处 Chrome 69 不兼容的用法：\n' % len(problems))
        for r, ln, cat, desc, ver, snippet in problems:
            print('  %s:%d  [%s] %s（%s）' % (r, ln, cat, desc, ver))
            if snippet:
                print('      %s' % snippet)
        print('\n处理方式：')
        print('  1) 同规则内补等价旧写法（inset → top/right/bottom/left；')
        print('     appearance → -webkit-appearance；backdrop-filter → -webkit-backdrop-filter）；')
        print('  2) 用 @supports not (aspect-ratio: ...) 提供兜底块；')
        print('  3) flex 容器带 gap 的，必须在 @supports 兜底块里出现等价 margin；')
        print('  4) 改用等价的旧写法；')
        print('  5) 确实无法降级时，在该行加注释说明，并在此表放行。')
        return 1

    print('\n✅ 未发现 Chrome 69 不兼容的用法')
    return 0


if __name__ == '__main__':
    sys.exit(main())
