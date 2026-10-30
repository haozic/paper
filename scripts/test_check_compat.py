# -*- coding: utf-8 -*-
"""check_compat.py 的反向自测：构造已知结果���用例，验证判定逻辑。

每个用例形如 (说明, CSS 文本, 期望命中的关键字列表)。
关键字为空表示期望"不报错"。

用法：python scripts/test_check_compat.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_compat as cc

CASES = [
    (
        '顶层使用 inset 简写 → 必须报错',
        '.gate { inset: 0; }',
        ['inset'],
    ),
    (
        '顶层 inset 已补长写 → 不报错',
        '.gate { top: 0; right: 0; bottom: 0; left: 0; }',
        [],
    ),
    (
        '@supports (content-visibility: auto) 内的 content-visibility → 不报错（Chrome 69 整块忽略）',
        '@supports (content-visibility: auto) {\n'
        '    .art-item { content-visibility: auto; contain-intrinsic-size: 40px; }\n'
        '}',
        [],
    ),
    (
        '@supports (content-visibility: auto) 内的 inset → 不报错（同上，整块忽略）',
        '@supports (content-visibility: auto) {\n'
        '    .x { content-visibility: auto; inset: 0; }\n'
        '}',
        [],
    ),
    (
        '@supports not (aspect-ratio) 内的 inset → 必须报错（该块在 Chrome 69 上生效）',
        '@supports not (aspect-ratio: 3 / 4) {\n'
        '    .x { inset: 0; }\n'
        '}',
        ['inset'],
    ),
    (
        '@supports (display: grid) 内的 color-mix → 必须报错（Chrome 69 支持 grid，该块会生效）',
        '@supports (display: grid) {\n'
        '    .x { color: color-mix(in srgb, red, blue); }\n'
        '}',
        ['color-mix'],
    ),
    (
        '@media 内（不在 @supports）的 inset → 必须报错',
        '@media (min-width: 768px) {\n'
        '    .x { inset: 0; }\n'
        '}',
        ['inset'],
    ),
    (
        '@supports 内再嵌 @media，inset → 必须报错',
        '@supports not (aspect-ratio: 3 / 4) {\n'
        '    @media (min-width: 768px) {\n'
        '        .x { inset: 0; }\n'
        '    }\n'
        '}',
        ['inset'],
    ),
    (
        'flex 容器用 gap 且无兜底 → 必须报错',
        '.foo { display: flex; gap: 12px; }',
        ['兜底缺失'],
    ),
    (
        'flex 容器用 gap 且有 @supports not 兜底 → 不报错',
        '.foo { display: flex; gap: 12px; }\n'
        '@supports not (aspect-ratio: 3 / 4) {\n'
        '    .foo { gap: 0; }\n'
        '    .foo > * + * { margin-left: 12px; }\n'
        '}',
        [],
    ),
    (
        'flex 容器用 gap，但兜底只写在 @supports (content-visibility) 里 → 必须报错（那不是兜底块）',
        '.foo { display: flex; gap: 12px; }\n'
        '@supports (content-visibility: auto) {\n'
        '    .foo { gap: 0; }\n'
        '}',
        ['兜底缺失'],
    ),
    (
        'grid 容器用 gap → 不报错（grid gap 自 Chrome 66 起支持）',
        '.foo { display: grid; gap: 16px; }',
        [],
    ),
    (
        'flex 容器 gap: 0 → 不报错',
        '.foo { display: flex; gap: 0; }',
        [],
    ),
    (
        '注释里的 inset 不应误报',
        '/* 这里写了 inset: 0 只是注释 */\n.foo { color: red; }',
        [],
    ),
    (
        '注释里的 content-visibility 不应误报',
        '/* content-visibility: auto */\n.foo { color: red; }',
        [],
    ),
]


def run():
    failed = 0
    for desc, css, expect in CASES:
        problems = []
        cc.check_css('t.css', css, problems)
        cc.check_flex_gap_fallback('t.css', css, problems)
        got = ['%s %s' % (p[2], p[3]) for p in problems]
        hit = any(any(k in g for g in got) for k in expect) if expect else (len(problems) == 0)
        if hit:
            print('  OK   %s' % desc)
        else:
            failed += 1
            print('  FAIL %s' % desc)
            print('       期望命中 %s，实际 %s' % (expect, got))
    print('\n%d/%d 通过' % (len(CASES) - failed, len(CASES)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(run())
