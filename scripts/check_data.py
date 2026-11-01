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

sys.path.insert(0, SCRIPT_DIR)
from canonical_sections import ALIASES    # noqa: E402  板块名归一表（改名合并）
from refresh_sections import url_key     # noqa: E402  URL 匹配键（忽略协议与年份段）

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

    # 板块名体检：meta 里不该再出现抓取脚本的兜底值
    #   "目 录" —— 来源站并没有叫"目录"的栏目，这是解析器把目录页标题当成了板块
    #   （还有全角空格 / nbsp 两种写法）
    #   "评论" —— 老版本把微博分享控件 <span class="big">评论</span> 当成了栏目
    # 两者都会在板块页上渲染成误导性的卡片，必须为空。
    placeholder_sections = collections.Counter()
    for a in meta:
        sec = ''.join((a.get('s') or '').split())
        if sec in ('目录', '评论'):
            placeholder_sections[sec] += 1

    # 板块名归一表体检：同一栏目被来源站改过名之后，meta 里不该再出现旧写法，
    # 否则板块页上会出现两张长得很像的卡片（详见 scripts/canonical_sections.py）。
    alias_leaks = collections.Counter()
    for a in meta:
        sec = ''.join((a.get('s') or '').split())
        if sec in ALIASES:
            alias_leaks[sec] += 1

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
    if placeholder_sections:
        print('    !! 存在兜底板块名（不是真实栏目，会在板块页渲染成误导性卡片）：'
              + '、'.join('%s %d 条' % (k, v) for k, v in placeholder_sections.items()))
    else:
        print('    板块名: 无兜底值（"目 录"/"评论"）')
    if alias_leaks:
        print('    !! 存在未归一的旧板块名（同一栏目的旧写法，板块页会多出相似的卡片）：'
              + '、'.join('%s %d 条' % (k, v) for k, v in alias_leaks.items()))
    else:
        print('    板块名: 无未归一的旧写法')
    return len(meta), dup_count, {
        'articles': len(meta),
        'issues': len(issues),
        'shards': len(shards),
        'missing_body': len(missing_body),
        'orphan_shards': orphan_shards,
        'placeholder_sections': dict(placeholder_sections),
        'alias_leaks': dict(alias_leaks),
    }


def check_catalog_order():
    """目录顺序体检：meta 里每一期的文章顺序，必须与官网目录页的顺序一致。

    基准是 data/catalog_order.json —— 由 scripts/fix_catalog_order.py 从官网
    目录页抓下来的顺序快照（o = 官网列出的顺序，x = 官网没列出的部分）。
    快照存在才查这条：没有快照时只提示，不算失败。
    """
    print('\n[catalog_order] 目录顺序（对照官网目录页快照）')
    snap = load('data/catalog_order.json')
    if snap is None:
        print('    缺少快照 data/catalog_order.json，跳过（跑一次 scripts/fix_catalog_order.py --apply 生成）')
        return 0
    bad = 0
    for key, name, meta_path, _ in MAGAZINES:
        meta = load(meta_path) or []
        groups = {}
        for a in meta:
            groups.setdefault('%d-%d' % (a['y'], a['i']), []).append(url_key(a['u']))
        snap_mag = snap.get(key) or {}
        checked = 0
        for slug, rec in snap_mag.items():
            want = list(rec.get('o') or []) + list(rec.get('x') or [])
            have = groups.get(slug) or []
            if have != want:
                bad += 1
                if len(have) != len(want):
                    print(f'    !! {name} {slug} 条数不符：本地 {len(have)} / 快照 {len(want)}')
                else:
                    print(f'    !! {name} {slug} 顺序与官网目录页不一致')
                continue
            checked += 1
        print(f'    {name}: 校验 {checked}/{len(snap_mag)} 期顺序一致')
    print('    目录顺序不一致的期数: %d' % bad)
    return bad


def check_search_index():
    """跨刊标题索引体检（规则 S1~S4）。

    索引 data/search_index.json 是派生产物，唯一权威源是三份 meta.json。
    这里强制断言二者一致，避免改了 meta 却忘了重建索引。
    """
    print('\n[search_index] 跨刊标题索引')
    path = 'data/search_index.json'
    full = os.path.join(BASE_DIR, path)
    if not os.path.exists(full):
        print(f'    !! 缺少 {path}（跑一次 python scripts/build_search_index.py 生成）')
        return 1

    size = os.path.getsize(full)
    with open(full, encoding='utf-8') as f:
        idx = json.load(f)

    rows = idx.get('rows') or []
    cols = idx.get('cols') or []
    bad = 0

    # S2 逐行可寻址：先建 (mag) -> {(y,i,u)} 的集合
    by_mag = {}
    for key, _name, meta_path, _issues in MAGAZINES:
        meta = load(meta_path) or []
        by_mag[key] = set((a['y'], a['i'], a['u']) for a in meta)

    # S1 行数
    want_rows = sum(len(load(mp) or []) for _k, _n, mp, _i in MAGAZINES)
    if len(rows) != want_rows:
        print(f"    !! S1 行数不符：索引 {len(rows)} 行，三刊 meta 合计 {want_rows} 行")
        bad += 1
    else:
        print(f'    S1 行数一致：{len(rows)} 行')

    # S2 逐行可寻址
    missing = 0
    first_bad = None
    for row in rows:
        if len(row) != 5:
            missing += 1
            if first_bad is None:
                first_bad = row
            continue
        mag, y, i, _t, u = row
        if (y, i, u) not in by_mag.get(mag, set()):
            missing += 1
            if first_bad is None:
                first_bad = row
    if missing:
        print(f'    !! S2 有 {missing} 行在 meta 中找不到对应条目，示例 {first_bad}')
        bad += 1
    else:
        print('    S2 逐行可寻址：全部命中')

    # S3 同一刊物内 URL 无重复
    # 注意：**跨刊**允许重复 —— 实测三刊 meta 合计 7415 行、唯一 URL 7413 个，
    # 差的两条是「网站声明」这篇文章同时出现在《求是》和《红旗文稿》的目录里
    # （http / https 各一组）。那是真实数据，不是索引的错；
    # 全局去重会破坏 S1（行数必须等于三刊 meta 条目数之和），也不能做。
    counts = {}
    uniques = {}
    for r in rows:
        if len(r) != 5:
            continue
        counts[r[0]] = counts.get(r[0], 0) + 1
        uniques.setdefault(r[0], set()).add(r[4])
    dup_total = 0
    for mag in sorted(counts):
        d = counts[mag] - len(uniques[mag])
        if d:
            print(f'    !! S3 {mag} 在索引内有 {d} 条重复 URL')
        dup_total += d
    if dup_total:
        bad += 1
    else:
        print('    S3 同一刊物内 URL 无重复')

    # S4 体积
    limit = 1572864
    if size > limit:
        print(f'    !! S4 体积 {size} 字节，超过上限 {limit} 字节')
        bad += 1
    else:
        print(f'    S4 体积 {size} 字节（上限 {limit}）')

    if cols != ['m', 'y', 'i', 't', 'u']:
        print(f"    !! cols 为 {cols}，应为 ['m', 'y', 'i', 't', 'u']")
        bad += 1

    print('    索引问题数: %d' % bad)
    return bad


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

    ph_total = sum(sum((st.get('placeholder_sections') or {}).values()) for st in stats.values())
    alias_total = sum(sum((st.get('alias_leaks') or {}).values()) for st in stats.values())
    print(f'\n合计文章数: {total_before}   重复条目: {total_dup}')
    print(f'板块名体检: 兜底值 {ph_total} 条   未归一旧写法 {alias_total} 条')

    order_bad = check_catalog_order()
    index_bad = check_search_index()

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
