#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
为「直接双击 index.html」的用法准备数据（file:// 模式）。

为什么需要这一步
----------------
浏览器在 file:// 下把每个本地文件都当成独立来源，会拦截 fetch()/XHR，
所以「拷贝文件夹到单机电脑 → 双击 index.html」时，三个杂志的数据一条都读不出来
（Console 里是 TypeError: Failed to fetch）。

但 <script src="..."> 不受这条限制：同目录下的 .js 可以正常载入。
本脚本把 data/ 下的 json 另存成 file-mode/ 下的同名 .js，
站点在 file:// 下改用 <script> 读它们，就能在不启动任何服务的情况下使用。

    data/counts.json            ->  file-mode/data/counts.js
    data/qs/meta.json           ->  file-mode/data/qs/meta.js
    data/qs/issues/2019-1.json  ->  file-mode/data/qs/issues/2019-1.js

正文不需要另存一份：articles/ 下的 markdown 备份在 file:// 下取不到，
但期次分片（issues/*.json）里本来就带正文，站点会自动改走分片，
代价是打开单篇文章要加载整期分片（约 200 KB～400 KB）而不是单个 md。

用法
----
    python3 scripts/prepare_file_mode.py            # 生成（已是最新的会跳过）
    python3 scripts/prepare_file_mode.py --check    # 只体检，不生成
    python3 scripts/prepare_file_mode.py --clean    # 删掉 file-mode/ 目录

生成物在 file-mode/ 目录，已在 .gitignore 里，不进版本库。
数据更新后重跑一次即可。
"""

import argparse
import json
import os
import shutil
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUT_DIR = os.path.join(BASE_DIR, 'file-mode')
REGISTRY = '__DJYJ_FILE_DATA__'

# 本地存储用到的数据文件（站点会按这些相对路径去取）
MAGAZINES = [
    ('qs', '求是', 'data/qs/meta.json', 'data/qs/issues'),
    ('hqwg', '红旗文稿', 'data/hqwg/meta.json', 'data/hqwg/issues'),
    ('djyj', '党建研究', 'data/meta.json', 'data/issues'),
]


def rel_path(abs_path):
    return os.path.relpath(abs_path, BASE_DIR).replace(os.sep, '/')


def out_path_for(json_rel):
    """data/qs/meta.json -> file-mode/data/qs/meta.js"""
    return os.path.join(OUT_DIR, json_rel[:-len('.json')] + '.js')


def build_js(json_rel, raw_text):
    """把一段 JSON 文本包成可被 <script> 载入的 JS。

    JSON 是 JS 表达式的一个子集，只有 U+2028 / U+2029 两个行分隔符在
    老版本 JS 字符串字面量里不合法（ES2019 才放开），这里统一转义，
    保证 Chrome 69 也能正常解析。
    """
    text = raw_text.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    return ('window.%s=window.%s||{};window.%s[%s]=%s;\n'
            % (REGISTRY, REGISTRY, REGISTRY, json.dumps(json_rel), text))


def iter_json_files():
    for dirpath, dirnames, filenames in os.walk(DATA_DIR):
        dirnames.sort()
        for fn in sorted(filenames):
            if fn.endswith('.json'):
                yield rel_path(os.path.join(dirpath, fn))


def build_js_text(md_rel, raw_text):
    """把 markdown 正文包成可被 <script> 载入的 JS（键前缀 text:，与 JSON 数据区分）。"""
    text = raw_text.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    return ('window.%s=window.%s||{};window.%s[%s]=%s;\n'
            % (REGISTRY, REGISTRY, REGISTRY, json.dumps('text:' + md_rel), json.dumps(text)))


def missing_body_map():
    """有正文标记、但期次分片里查不到正文的文章 -> 它的 markdown 备份路径。

    这几篇在 HTTP 下靠 articles/*.md 兜底；file:// 下取不到 md，
    所以要单独转一份 .js，否则这些文章会变成"没有正文"。
    """
    idx_path = os.path.join(BASE_DIR, 'data/article_index.json')
    with open(idx_path, encoding='utf-8') as f:
        idx = json.load(f)
    out = {}
    for key, name, meta_rel, issues_rel in MAGAZINES:
        meta_path = os.path.join(BASE_DIR, meta_rel)
        if not os.path.exists(meta_path):
            continue
        with open(meta_path, encoding='utf-8') as f:
            meta = json.load(f)
        have = set()
        issues_dir = os.path.join(BASE_DIR, issues_rel)
        if os.path.isdir(issues_dir):
            for fn in sorted(os.listdir(issues_dir)):
                if not fn.endswith('.json'):
                    continue
                with open(os.path.join(issues_dir, fn), encoding='utf-8') as f:
                    have |= set(json.load(f).keys())
        index = idx.get(key) or {}
        for a in meta:
            if not a.get('h'):
                continue
            if a['u'] in have:
                continue
            md_path = index.get(a['u'])
            if md_path:
                out[a['u']] = md_path
    return out


def generate_missing_bodies():
    """给正文不在分片里的文章补一份 .js 正文，并写出对应关系表。"""
    missing = missing_body_map()
    made = 0
    for url, md_rel in sorted(missing.items()):
        src = os.path.join(BASE_DIR, md_rel)
        if not os.path.exists(src):
            print('    [跳过] 找不到 markdown 备份: %s' % md_rel)
            continue
        dst = os.path.join(OUT_DIR, md_rel + '.js')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(src, encoding='utf-8') as f:
            raw = f.read()
        payload = build_js_text(md_rel, raw)
        tmp = dst + '.tmp'
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(payload)
        os.replace(tmp, dst)
        made += 1
    # 对应关系表（很小，file:// 下用它知道哪几篇要单独读正文）
    rel = 'missing_bodies.json'
    dst = os.path.join(OUT_DIR, rel[:-len('.json')] + '.js')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    payload = build_js(rel, json.dumps(missing, ensure_ascii=False))
    tmp = dst + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(payload)
    os.replace(tmp, dst)
    print('正文不在分片里的文章: %d 篇（已单独转出 %d 份 .js 正文）' % (len(missing), made))
    return missing


def generate(check_only=False, clean=False):
    if clean:
        if os.path.isdir(OUT_DIR):
            shutil.rmtree(OUT_DIR)
            print('已删除 %s' % rel_path(OUT_DIR))
        else:
            print('没有 %s 目录，无需清理' % rel_path(OUT_DIR))
        return 0

    files = list(iter_json_files())
    if not files:
        print('data/ 下没找到 json，无法生成')
        return 1

    made = 0
    skipped = 0
    stale = []
    total_bytes = 0
    t0 = time.time()
    for rel in files:
        src = os.path.join(BASE_DIR, rel)
        dst = out_path_for(rel)
        with open(src, encoding='utf-8') as f:
            raw = f.read()
        if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            skipped += 1
            total_bytes += os.path.getsize(dst)
            continue
        stale.append(rel)
        if check_only:
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        payload = build_js(rel, raw)
        tmp = dst + '.tmp'
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(payload)
        os.replace(tmp, dst)
        made += 1
        total_bytes += os.path.getsize(dst)

    print('扫描 json: %d 个' % len(files))
    if check_only:
        print('需要重新生成: %d 个%s' % (len(stale), ('，例如 ' + stale[0]) if stale else ''))
        return 1 if stale else 0
    print('新生成: %d 个   已是最新: %d 个' % (made, skipped))
    generate_missing_bodies()
    print('产物目录: %s   合计 %.1f MB   用时 %.1fs'
          % (rel_path(OUT_DIR), total_bytes / 1048576.0, time.time() - t0))
    return 0


def check_coverage():
    """体检：file:// 模式下每篇有正文的文章，都能在期次分片里找到正文。"""
    print('--- 正文覆盖体检（file:// 模式下正文只走期次分片）---')
    bad = 0
    for key, name, meta_rel, issues_rel in MAGAZINES:
        meta_path = os.path.join(BASE_DIR, meta_rel)
        if not os.path.exists(meta_path):
            continue
        with open(meta_path, encoding='utf-8') as f:
            meta = json.load(f)
        want = set(a['u'] for a in meta if a.get('h'))
        have = set()
        issues_dir = os.path.join(BASE_DIR, issues_rel)
        if os.path.isdir(issues_dir):
            for fn in sorted(os.listdir(issues_dir)):
                if not fn.endswith('.json'):
                    continue
                with open(os.path.join(issues_dir, fn), encoding='utf-8') as f:
                    have |= set(json.load(f).keys())
        missing = want - have
        print('  %-5s 有正文 %4d 篇   分片里缺 %d 篇' % (key, len(want), len(missing)))
        if missing:
            bad += len(missing)
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='只体检，不生成')
    ap.add_argument('--clean', action='store_true', help='删掉 file-mode/ 目录')
    args = ap.parse_args()

    if args.check:
        rc = generate(check_only=True)
        check_coverage()
        return rc

    rc = generate()
    check_coverage()
    return rc


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.exit(main() or 0)
