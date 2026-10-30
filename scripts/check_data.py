#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据体检脚本：检查三本党刊的 meta / 正文分片 / counts / article_index 是否一致、有无重复、期号是否连续。

数据布局（2026-10 起改为按期分片）
----------------------------------
    data/qs/meta.json      + data/qs/issues/<年>-<期>.json
    data/hqwg/meta.json    + data/hqwg/issues/<年>-<期>.json
    data/meta.json         + data/issues/<年>-<期>.json
    data/counts.json       # 首页计数（文章数 / 期数）
    data/article_index.json# URL → markdown 备份路径

用法：
    python scripts/check_data.py            # 只检查，不修改
    python scripts/check_data.py --dedup    # 检查并就地去重（meta.json + article_index.json）

对应文档：docs/UPDATE_FLOW.md
"""

import json
import os
import sys
import collections

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)

MAGAZINES = [
    ('qs', '求是', 'data/qs/meta.json', 'data/qs/issues'),
    ('hqwg', '红旗文稿', 'data/hqwg/meta.json', 'data/hqwg/issues'),
    ('djyj', '党建研究', 'data/meta.json', 'data/issues'),
]


def load(path):
    full = os.path.join(BASE_DIR, path)
    if not os.path.exists(full):
        return None
    with open(full, encoding='utf-8') as f:
        return json.load(f)


def save(path, data):
    full = os.path.join(BASE_DIR, path)
    with open(full, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))


def shard_name(year, issue):
    return '%s-%s.json' % (year, issue)


def list_shards(issues_dir):
    """返回 {分片文件名: (年, 期)}，只认 <年>-<期>.json。"""
    full = os.path.join(BASE_DIR, issues_dir)
    out = {}
    if not os.path.isdir(full):
        return out
    for fn in os.listdir(full):
        if not fn.endswith('.json'):
            continue
        stem = fn[:-5]
        if '-' not in stem:
            continue
        year, _, issue = stem.partition('-')
        if not year.isdigit() or not issue.isdigit():
            continue
        out[fn] = (int(year), int(issue))
    return out


def check_one(key, name, meta_path, issues_dir):
    meta = load(meta_path)
    if meta is None:
        print(f'[{key}] {name}: 缺少 {meta_path}')
        return 0, 0, {}

    counter = collections.Counter(a['u'] for a in meta)
    dup_urls = [u for u, c in counter.items() if c > 1]
    dup_count = len(meta) - len(counter)

    issues = sorted({(a['y'], a['i']) for a in meta})
    no_full = sum(1 for a in meta if not a.get('h'))

    # 正文分片覆盖检查（按期分片，单片 ~200KB，逐片加载）
    missing_body = []
    body_cache = {}
    for a in meta:
        if not a.get('h'):
            continue
        skey = (a['y'], a['i'])
        if skey not in body_cache:
            body_cache[skey] = load(os.path.join(issues_dir, shard_name(*skey)))
        body = body_cache[skey]
        if body is None:
            missing_body.append(f"{a['y']}年第{a['i']}期 分片缺失（{shard_name(*skey)}）")
            continue
        if a['u'] not in body:
            missing_body.append(f"{a['u']} 无正文")

    # 孤儿分片：磁盘上有分片，但 meta 里没有这一期
    shards = list_shards(issues_dir)
    meta_issue_set = set(issues)
    orphan_shards = sorted(fn for fn, tag in shards.items() if tag not in meta_issue_set)

    # meta 标了有正文的期次里，有多少期完全没有分片（整期无正文属正常）
    no_body_issues = sorted(s for s in meta_issue_set if s not in set(shards.values()))

    print(f'[{key}] {name}')
    print(f'    文章总数: {len(meta)}   唯一URL: {len(counter)}   重复条目: {dup_count}')
    print(f'    期号范围: {issues[0][0]}年第{issues[0][1]:02d}期 ~ {issues[-1][0]}年第{issues[-1][1]:02d}期'
          f'   共 {len(issues)} 期')
    print(f'    无全文(h=0): {no_full} 篇')
    print(f'    正文分片: {len(shards)} 个   整期无正文: {len(no_body_issues)} 期')
    recent = issues[-4:]
    for y, i in recent:
        n = sum(1 for a in meta if a['y'] == y and a['i'] == i)
        print(f'      {y}年第{i:02d}期: {n} 篇')
    if missing_body:
        print(f'    !! 正文缺失 {len(missing_body)} 处，例如: {missing_body[0]}')
    if orphan_shards:
        print(f'    !! 孤儿分片 {len(orphan_shards)} 个（meta 中无对应期次），例如: {orphan_shards[0]}')
    if dup_count:
        print(f'    !! 存在重复 URL {dup_count} 条')
    return len(meta), dup_count, {
        'articles': len(meta),
        'issues': len(issues),
        'shards': len(shards),
        'missing_body': len(missing_body),
        'orphan_shards': orphan_shards,
    }


def main():
    dedup = '--dedup' in sys.argv

    print('=' * 64)
    print('数据体检')
    print('=' * 64)
    total_before = 0
    total_dup = 0
    stats = {}
    for key, name, meta_path, issues_dir in MAGAZINES:
        n, d, st = check_one(key, name, meta_path, issues_dir)
        stats[key] = st
        total_before += n
        total_dup += d

    # counts.json 交叉检查（首页计数）
    counts = load('data/counts.json')
    print('\n[counts.json] ' + ('缺失' if counts is None else '校验'))
    for key, name, _meta_path, _issues_dir in MAGAZINES:
        if counts is None:
            break
        want = stats.get(key) or {}
        have = counts.get(key) or {}
        if have.get('articles') != want.get('articles') or have.get('issues') != want.get('issues'):
            print(f"    !! {name}: counts 记录 {have} 与 meta 实测 {want} 不一致")
        else:
            print(f"    {name}: 文章 {have.get('articles')} 篇 / 期 {have.get('issues')} 期  一致")

    # article_index.json 交叉检查
    idx = load('data/article_index.json') or {}
    idx_total = sum(len(v) for v in idx.values())
    print(f'\n[article_index] 映射总数: {idx_total}   杂志: {", ".join(idx.keys())}')
    for key, name, meta_path, _ in MAGAZINES:
        meta = load(meta_path) or []
        want = {a['u'] for a in meta if a.get('h')}
        have = set(idx.get(key, {}).keys())
        missing = want - have
        if missing:
            print(f'    !! {name}: {len(missing)} 篇有正文但缺 md 映射（示例 {list(missing)[0]}）')

    print(f'\n合计文章数: {total_before}   重复条目: {total_dup}')

    if dedup and total_dup:
        print('\n开始去重...')
        for key, name, meta_path, _ in MAGAZINES:
            meta = load(meta_path)
            seen = set()
            uniq = []
            for a in meta:
                if a['u'] not in seen:
                    seen.add(a['u'])
                    uniq.append(a)
            if len(uniq) != len(meta):
                save(meta_path, uniq)
                print(f'  {name}: {len(meta)} -> {len(uniq)}')
        idx = load('data/article_index.json') or {}
        for key in list(idx.keys()):
            before = len(idx[key])
            idx[key] = {u: p for u, p in idx[key].items()}
            if len(idx[key]) != before:
                print(f'  article_index[{key}]: {before} -> {len(idx[key])}')
        save('data/article_index.json', idx)
        print('去重完成')
    elif dedup:
        print('\n无需去重。')


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
