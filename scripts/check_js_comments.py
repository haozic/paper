#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
JS 注释层体检：找出"块注释被提前闭合"这一类静默破坏脚本的 bug

为什么需要这个脚本
------------------
JS 的块注释**不嵌套**。块注释内部一旦出现 `*/`，注释就提前结束，
后面的注释文字会被当成代码解析。这类 bug 的恶劣之处在于：

  * **语法完全合法** —— acorn / node --check / eslint 一律通过，
    所以"跑一遍语法检查"根本发现不了；
  * **运行期才炸** —— 求值阶段抛 ReferenceError，Service Worker 直接
    "script evaluation failed"，整个离线能力静默失效。

真实案例（2026-10-30，sw.js）：
    /* ... (data/**/issues/*.json) ... */
    ↑ 文件头注释里的 `data/**/` 含有 `*/`，提前闭合了注释
    紧接着的 `issues/*.json）...` 被当成代码 → issues is not defined
    随后 `/*` 又开启了一段新注释，把后面的 `'use strict'` 也吞了进去。

**本项目采用的硬规则**：JS 的块注释里不允许出现 `/*`。
路径一律写成 `data 各刊的 issues 目录`、`articles 目录下的 .md`
这种不含 `/*` 的形式。理由是块注释不嵌套，注释里的任何 `/*`
都是"下一个 `*/` 会提前闭合注释"的引信，而作者很难当场察觉。

本脚本做两类检查：

  A. 词法扫描：区分代码 / 字符串 / 模板串 / 行注释 / 块注释，
     报告块注释内部出现 "/*" 的位置。
  B. 求值冒烟（需要 node）：在 mock 的 Service Worker 全局环境里
     真正求值 sw.js，捕获求值期异常，并检查 4 个事件监听器都注册了。

用法：
  python scripts/check_js_comments.py              # A + B（node 缺失时自动跳过 B）
  python scripts/check_js_comments.py --no-runtime # 只跑 A
  python scripts/check_js_comments.py --list       # 列出被扫描的文件
  python scripts/check_js_comments.py --self-test  # 反向自检（证明检查有鉴别力）

有问题返回非 0 退出码。
"""

import os
import re
import subprocess
import sys
import tempfile

# Windows 控制台默认 GBK，直接打印中文会抛 UnicodeEncodeError。
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, ValueError):      # Python < 3.7 / 非标准流
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 不扫描的目录
SKIP_DIR = re.compile(r'(^|[\\/])(\.git|node_modules|__pycache__|\.claude)([\\/]|$)')

# 重点扫描的 JS 文件（相对 BASE_DIR）；其余 .js 也会被顺带扫到
JS_FILES = [
    'assets/js/app.js',
    'sw.js',
]


# ---------------------------------------------------------------- 词法扫描

def scan_block_comment_nesting(text):
    """扫描 JS 源码，报告块注释内部出现 "/*" 的位置。

    区分代码 / 字符串 / 模板串 / 行注释 / 块注释，只在块注释内部报，
    因此字符串、模板串、行注释里的 "/*" 不会误报。

    返回 [(line, col, line_text, block_start_line)]；line/col 均为 1-based。
    """
    problems = []
    i = 0
    n = len(text)
    line = 1
    col = 1
    state = 'code'          # code | line | block | str | tmpl
    quote = ''
    block_start_line = 0

    lines = text.split('\n')

    def cur_line_text():
        idx = line - 1
        if 0 <= idx < len(lines):
            return lines[idx].strip()
        return ''

    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ''

        if state == 'code':
            if c == '/' and nxt == '/':
                state = 'line'
                i += 2
                col += 2
                continue
            if c == '/' and nxt == '*':
                state = 'block'
                block_start_line = line
                i += 2
                col += 2
                continue
            if c in ('"', "'"):
                state = 'str'
                quote = c
                i += 1
                col += 1
                continue
            if c == '`':
                state = 'tmpl'
                quote = c
                i += 1
                col += 1
                continue
            if c == '\n':
                line += 1
                col = 1
                i += 1
                continue
            i += 1
            col += 1
            continue

        if state == 'line':
            if c == '\n':
                state = 'code'
                line += 1
                col = 1
                i += 1
                continue
            i += 1
            col += 1
            continue

        if state == 'block':
            if c == '*' and nxt == '/':
                state = 'code'
                i += 2
                col += 2
                continue
            if c == '/' and nxt == '*':
                problems.append((line, col, cur_line_text(), block_start_line))
                i += 2
                col += 2
                continue
            if c == '\n':
                line += 1
                col = 1
                i += 1
                continue
            i += 1
            col += 1
            continue

        # 单双引号字符串 / 模板串
        if c == '\\':
            i += 2
            col += 2
            continue
        if c == quote:
            state = 'code'
            i += 1
            col += 1
            continue
        if c == '\n':
            # 未闭合的字符串：容错，按换行继续（真实代码里几乎不会出现）
            line += 1
            col = 1
            i += 1
            continue
        i += 1
        col += 1

    return problems


# ------------------------------------------------------- SW 求值冒烟（node）

# 在 mock 的 Service Worker 全局环境里求值 sw.js。
# 覆盖 Worker 作用域实际会用到的东西：self / caches / URL / Request / Response。
NODE_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const path = process.argv[1];

const src = fs.readFileSync(path, 'utf8');
const listeners = {};

const ctx = {
  console: { log(){}, warn(){}, error(){} },
  URL, Promise, Request, Response, RegExp, JSON, Math, Date,
  Object, Array, String, Number, Boolean, Error, TypeError,
  decodeURIComponent, encodeURIComponent, setTimeout, clearTimeout,
  self: {
    location: { search: '?v=test', origin: 'https://example.invalid' },
    addEventListener: (t, f) => { listeners[t] = f; },
    skipWaiting: () => Promise.resolve(),
    clients: { claim: () => Promise.resolve() },
  },
  caches: {
    open: () => Promise.resolve({}),
    keys: () => Promise.resolve([]),
    match: () => Promise.resolve(null),
    delete: () => Promise.resolve(false),
  },
};

vm.createContext(ctx);
try {
  vm.runInContext(src, ctx, { filename: path });
} catch (e) {
  console.error('EVAL_FAILED ' + (e && e.name) + ': ' + (e && e.message));
  process.exit(1);
}

const need = ['install', 'activate', 'fetch', 'message'];
const missing = need.filter(t => !listeners[t]);
if (missing.length) {
  console.error('MISSING_LISTENERS ' + missing.join(','));
  process.exit(1);
}
console.log('OK');
"""


def run_sw_eval(sw_path):
    """在 mock SW 环境里求值 sw.js。

    返回 (ok, message)。ok 为 None 表示跳过（node 不可用）。
    """
    try:
        proc = subprocess.run(
            ['node', '-e', NODE_HARNESS, sw_path],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        return None, '跳过：未找到 node'
    except subprocess.TimeoutExpired:
        return False, '求值超时（60 秒）'

    out = (proc.stdout or '').strip()
    err = (proc.stderr or '').strip()
    if proc.returncode == 0 and out.endswith('OK'):
        return True, '求值通过，install/activate/fetch/message 四个监听器均已注册'

    # 优先取我们自己打印的结论行，其次取 stderr 里第一行真正的错误
    for line in (err + '\n' + out).split('\n'):
        if 'EVAL_FAILED' in line or 'MISSING_LISTENERS' in line:
            return False, line.strip()
    detail = err.split('\n')[0] if err else (out or ('退出码 %s' % proc.returncode))
    return False, detail


# ---------------------------------------------------------------- 反向自检

# (用例名, 源码, 期望命中条数)
SELF_TEST_CASES = [
    ('真实事故形态：注释里写 data/**/issues 路径',
     '/* 头注释 (data/**/issues/*.json) 说明 */\nvar a = 1;\n', 1),
    ('注释里写 articles/*.md 这类路径',
     '/* 正文备份在 articles/*.md */\nvar a = 1;\n', 1),
    ('字符串里的 /* 不算注释',
     'var s = "/* not a comment */";\nvar a = 1;\n', 0),
    ('行注释里的 /* 不算注释',
     '// 见 data/*.json\nvar a = 1;\n', 0),
    ('模板字符串里的 /* 不算注释',
     'var s = `/* x */`;\nvar a = 1;\n', 0),
    ('普通代码不误报',
     'var a = 1;\nfunction f(){ return /re/g; }\n', 0),
]


def self_test():
    """反向自检：证明本脚本的检查确实有鉴别力。

    既要能抓到真实事故形态，也不能对字符串 / 行注释 / 模板串误报。
    """
    print('=' * 72)
    print('JS 注释层体检 · 反向自检')
    print('=' * 72)

    passed = 0
    failed = 0

    for (name, src, expect) in SELF_TEST_CASES:
        got = len(scan_block_comment_nesting(src))
        ok = (got == expect)
        print('  %s %s（期望 %d 处，实际 %d 处）'
              % ('OK  ' if ok else 'FAIL', name, expect, got))
        if ok:
            passed += 1
        else:
            failed += 1

    # 求值冒烟的反向对照：把真实 bug 注入一份 sw.js 副本，必须求值失败
    sw_path = os.path.join(BASE_DIR, 'sw.js')
    if not os.path.isfile(sw_path):
        print('  SKIP 求值冒烟反向对照（未找到 sw.js）')
    else:
        with open(sw_path, encoding='utf-8') as f:
            good = f.read()
        # 还原真实事故：把文件头注释里的路径写回带 "*/" 的形态
        bad = good.replace('data 各刊的 issues 目录', 'data/**/issues/*.json')
        if bad == good:
            print('  SKIP 求值冒烟反向对照（无法注入事故形态，sw.js 注释已改写）')
        else:
            with tempfile.TemporaryDirectory() as tmp:
                bad_path = os.path.join(tmp, 'sw-bad.js')
                with open(bad_path, 'w', encoding='utf-8') as f:
                    f.write(bad)
                ok_bad, msg_bad = run_sw_eval(bad_path)
                ok_good, msg_good = run_sw_eval(sw_path)

            c1 = (ok_bad is False)
            print('  %s 注入事故形态后求值必须失败（实际：%s）'
                  % ('OK  ' if c1 else 'FAIL', msg_bad))
            passed += 1 if c1 else 0
            failed += 0 if c1 else 1

            c2 = (ok_good is True)
            print('  %s 正常 sw.js 求值必须通过（实际：%s）'
                  % ('OK  ' if c2 else 'FAIL', msg_good))
            passed += 1 if c2 else 0
            failed += 0 if c2 else 1

    print('')
    print('%d/%d 通过' % (passed, passed + failed))
    return 0 if failed == 0 else 1


# ---------------------------------------------------------------- 主流程

def rel(p):
    return os.path.relpath(p, BASE_DIR).replace('\\', '/')


def main():
    argv = sys.argv[1:]
    show_list = '--list' in argv
    no_runtime = '--no-runtime' in argv

    if '--self-test' in argv:
        return self_test()

    print('=' * 72)
    print('JS 注释层体检（防"块注释提前闭合"）')
    print('=' * 72)

    targets = []
    for relpath in JS_FILES:
        p = os.path.join(BASE_DIR, relpath.replace('/', os.sep))
        if os.path.isfile(p):
            targets.append(p)
        else:
            print('  跳过（文件不存在）：%s' % relpath)

    # 顺带扫一遍仓库里其它 .js（子目录里的），避免漏网
    extra = []
    for root, dirs, files in os.walk(BASE_DIR):
        dirs[:] = [d for d in dirs if not SKIP_DIR.search(d)]
        for f in files:
            if f.lower().endswith('.js'):
                p = os.path.join(root, f)
                if p not in targets:
                    extra.append(p)
    targets.extend(sorted(extra))

    if show_list:
        for p in targets:
            print('  扫描：%s' % rel(p))
        print('')

    problems = []
    for p in targets:
        with open(p, encoding='utf-8') as f:
            text = f.read()
        for (line, col, snippet, block_start) in scan_block_comment_nesting(text):
            problems.append((rel(p), line, col, snippet, block_start))

    print('扫描：%d 个 JS 文件' % len(targets))
    print('')

    if problems:
        print('❌ 发现 %d 处"块注释内出现 /*"（有提前闭合注释的风险）：' % len(problems))
        for (r, line, col, snippet, block_start) in problems:
            print('  %s:%d:%d' % (r, line, col))
            print('      %s' % snippet)
            print('      ↑ 该块注释始于第 %d 行。JS 块注释不嵌套，注释里出现 "/*" 时，'
                  % block_start)
            print('        后面的 "*/" 会提前闭合注释，把注释文字当成代码解析。')
            print('        请把路径改写成不含 "/*" 的形式。')
            print('')
    else:
        print('✅ 未发现"块注释内出现 /*"')

    # ---- B. 求值冒烟 ----
    print('')
    sw_path = os.path.join(BASE_DIR, 'sw.js')
    if no_runtime:
        print('求值冒烟：已按 --no-runtime 跳过')
    elif not os.path.isfile(sw_path):
        print('求值冒烟：跳过（未找到 sw.js）')
    else:
        ok, msg = run_sw_eval(sw_path)
        if ok is None:
            print('求值冒烟：%s' % msg)
        elif ok:
            print('✅ 求值冒烟：%s' % msg)
        else:
            print('❌ 求值冒烟失败：%s' % msg)
            problems.append(('sw.js', 0, 0, msg, 0))

    print('')
    if problems:
        print('❌ 体检未通过：%d 处问题' % len(problems))
        return 1
    print('✅ 体检通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
