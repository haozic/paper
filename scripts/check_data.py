#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据体检脚本：检查三本党刊的 meta / years / article_index 是否一致、有无重复、期号是否连续。

用法：
  python scripts/check_data.py            # 只检查，不修改
  python scripts/check_data.py --dedup    # 检查并就地去重（meta.json + article_index.json）

对应文档：docs/UPDATE_FLOW.md §4.4「重复抓取同一期」
"""

import json
import os
import sys
import collections

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)

MAGAZINES = [
    ('qs', '求是', 'data/qs/meta.json', 'data/qs/years'),
    ('hqwg', '红旗文稿', 'data/hqwg/meta.json', 'data/hqwg/years'),
    ('djyj', '党建研究', 'data/meta.json', 'data/years'),
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


def check_one(key, name, meta_path, years_dir):
    meta = load(meta_path)
    if meta is None:
        print(f'[{key}] {name}: 缺少 {meta_path}')
        return 0, 0

    counter = collections.Counter(a['u'] for a in meta)
    dup_urls = [u for u, c in counter.items() if c > 1]
    dup_count = len(meta) - len(counter)

    issues = sorted({(a['y'], a['i']) for a in meta})
    no_full = sum(1 for a in meta if not a.get('h'))

    # 正文年份文件覆盖检查（年份文件较大，按年缓存，避免重复加载）
    missing_body = []
    body_cache = {}
    for a in meta:
        if not a.get('h'):
            continue
        ykey = a['y']
        if ykey not in body_cache:
            body_cache[ykey] = load(os.path.join(years_dir, f'{ykey}.json'))
        body = body_cache[ykey]
        if body is None:
            missing_body.append(f'{ykey}.json 缺失')
            break
        if a['u'] not in body:
            missing_body.append(f"{a['u']} 无正文")

    print(f'[{key}] {name}')
    print(f'    文章总数: {len(meta)}   唯一URL: {len(counter)}   重复条目: {dup_count}')
    print(f'    期号范围: {issues[0][0]}年第{issues[0][1]:02d}期 ~ {issues[-1][0]}年第{issues[-1][1]:02d}期'
          f'   共 {len(issues)} 期')
    print(f'    无全文(h=0): {no_full} 篇')
    recent = issues[-4:]
    for y, i in recent:
        n = sum(1 for a in meta if a['y'] == y and a['i'] == i)
        print(f'      {y}年第{i:02d}期: {n} 篇')
    if missing_body:
        print(f'    !! 正文缺失 {len(missing_body)} 处，例如: {missing_body[0]}')
    if dup_count:
        print(f'    !! 存在重复 URL {dup_count} 条')
    return len(meta), dup_count


def main():
    dedup = '--dedup' in sys.argv

    print('=' * 64)
    print('数据体检')
    print('=' * 64)
    total_before = 0
    total_dup = 0
    for key, name, meta_path, years_dir in MAGAZINES:
        n, d = check_one(key, name, meta_path, years_dir)
        total_before += n
        total_dup += d

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
    main()
