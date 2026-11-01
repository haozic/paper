#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
跨刊标题索引生成器。

为什么要这个脚本
----------------
站内检索原先锁死在"当前这一本刊"，想跨刊找一篇文章只能三本各搜一遍。
本脚本从三份 meta.json 生成一份紧凑的全局标题索引 data/search_index.json，
让前端一次请求就能跨三刊按标题匹配。

索引是**派生产物**：三份 meta.json 仍是唯一权威源。
`scripts/check_data.py` 的 S1~S4 规则会强制断言二者一致（**由 Task 2 落地**）。

索引形状
--------
    {
      "v": "20261101a",                  # 索引自身版本，meta 变了就要升
      "cols": ["m", "y", "i", "t", "u"], # 固定列序
      "rows": [                          # 每行 5 列
        ["qs", 2019, 1, "本期导读", "http://..."],
        ...
      ]
    }

行序（前端取到即得"新→旧"，不必在客户端再排）：
    刊物按展示顺序 qs → hqwg → djyj（不是字母序）
    → 年份降序 → 期号降序 → 期内沿用 meta.json 现有顺序（= 官网目录顺序）

用法
----
    python scripts/build_search_index.py             # 生成 data/search_index.json
    python scripts/build_search_index.py --check     # 重新生成并逐字节比对，不一致退出码 1
    python scripts/build_search_index.py --self-test # 跑内置用例（含反向自检）
    python scripts/build_search_index.py --print-avg # 打印各刊每期正文分片实测均值字节
"""

import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, ValueError):      # Python < 3.7 / 非标准流
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)

INDEX_VERSION = '20261101a'
INDEX_PATH = 'data/search_index.json'

# 刊物**展示顺序**：与 app.js 的 MAGAZINES、check_data.py 的 MAGAZINES 一致。
# 不是字母序（字母序会是 djyj → hqwg → qs），前端按这个顺序分组展示。
MAG_ORDER = ['qs', 'hqwg', 'djyj']

# 三刊 meta 路径，顺序同 MAG_ORDER
META_PATHS = [
    ('qs', 'data/qs/meta.json'),
    ('hqwg', 'data/hqwg/meta.json'),
    ('djyj', 'data/meta.json'),
]

MAX_INDEX_BYTES = 1_572_864     # 1.5 MB


def load_json(rel_path):
    full = os.path.join(BASE_DIR, rel_path)
    with open(full, encoding='utf-8') as f:
        return json.load(f)


def build_index(metas):
    """metas: [(mag, meta_list), ...] → 索引 dict。

    行序：刊物展示顺序 → 年降 → 期降 → 期内 meta 原有顺序。
    """
    rows = []
    by_mag = dict(metas)
    for mag in MAG_ORDER:
        meta = by_mag.get(mag) or []
        # 年份降序、期号降序；同一年同一期内部保持 meta 原有顺序（稳定排序）
        indexed = list(enumerate(meta))
        indexed.sort(key=lambda pair: (-pair[1]['y'], -pair[1]['i'], pair[0]))
        for _pos, a in indexed:
            rows.append([mag, a['y'], a['i'], a['t'], a['u']])
    return {'v': INDEX_VERSION, 'cols': ['m', 'y', 'i', 't', 'u'], 'rows': rows}


def dump_index(index):
    return json.dumps(index, ensure_ascii=False, separators=(',', ':'))
def read_disk():
    full = os.path.join(BASE_DIR, INDEX_PATH)
    if not os.path.exists(full):
        return None
    with open(full, 'rb') as f:
        return f.read()


def write_disk(text):
    full = os.path.join(BASE_DIR, INDEX_PATH)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


def load_metas():
    return [(mag, load_json(path)) for mag, path in META_PATHS]


def print_avg():
    """打印各刊每期正文分片的实测均值字节，供 app.js 的 BODY_AVG_BYTES 常量对账。"""
    for mag, meta_path in META_PATHS:
        meta = load_json(meta_path)
        issues_dir = os.path.join(BASE_DIR, os.path.dirname(meta_path), 'issues')
        sizes = []
        seen = set()
        for a in meta:
            if not a.get('h'):
                continue
            key = '%d-%d' % (a['y'], a['i'])
            if key in seen:
                continue
            seen.add(key)
            full = os.path.join(issues_dir, key + '.json')
            if os.path.exists(full):
                sizes.append(os.path.getsize(full))
        if sizes:
            print('%-6s 期数 %3d   总计 %8.1f MB   每期均值 %d 字节'
                  % (mag, len(sizes), sum(sizes) / 1048576.0, sum(sizes) // len(sizes)))
# --------------------------------------------------------------- 自检用例
# 规则编号（_check_rules 真正检查的规则，R1~R8）：
#   R1  索引行数 = 三刊 meta 条目数之和
#   R2  索引 cols 固定为 ["m","y","i","t","u"]
#   R3  每行都能在对应刊的 meta 里找到同一条（mag/y/i/u 四元组）
#   R4  同一刊物内 URL 无重复（跨刊允许重复：「网站公告」同时列在《求是》和《红旗文稿》）
#   R5  体积不超过 MAX_INDEX_BYTES
#   R6  行序：刊物展示顺序 qs → hqwg → djyj，且同一刊的行必须连续成块
#   R7  行序：年份降序、期号降序，期内保持 meta 原有顺序
#   R8  dump_index 输出可被 json.loads 还原，且与原对象相等
#
# 用例标签（self_test 里的一条条断言，不是一条规则）：
#   C1  正对照：结构合规的样本 → R1~R8 全部零错误
#   C2  空 meta 不炸，返回空 rows
#   C3  反向自检：同一刊物内 URL 重复 → 必须命中 R4
#   C4  反向自检：漏一行 → 必须命中 R1
#   C5  反向自检：刊别写错 → 必须命中 R6
#   C6  反向自检：顺序被打乱 → 必须命中 R7
#   C7  鉴别力：R1 必须是因为"行数少了"而失败，不是被别的规则顺带带崩

def _sample_metas():
    """构造一份结构完全合规的三刊样本（正对照用）。

    刻意包含一条**跨刊重复的 URL**（hqwg 的那篇与 qs 的那篇指向同一页面，
    与真实数据里「网站公告」同时列在两本刊目录里的情况同构），
    用来锁死「跨刊重复 → R4 零错误」这条语义。
    """
    return [
        ('qs', [
            {'t': '本期导读', 'a': '', 's': '', 'y': 2019, 'i': 1, 'u': 'http://q/1', 'h': 1},
            {'t': '新篇A', 'a': '甲', 's': '评论', 'y': 2020, 'i': 2, 'u': 'http://q/2', 'h': 1},
            {'t': '新篇B', 'a': '乙', 's': '评论', 'y': 2020, 'i': 1, 'u': 'http://q/3', 'h': 1},
        ]),
        ('hqwg', [
            {'t': '红旗篇', 'a': '丙', 's': '理论', 'y': 2021, 'i': 1, 'u': 'http://h/1', 'h': 1},
            {'t': '跨刊公告', 'a': '', 's': '', 'y': 2020, 'i': 1, 'u': 'http://q/2', 'h': 1},
        ]),
        ('djyj', [
            {'t': '党建篇', 'a': '丁', 's': '本刊特稿', 'y': 2022, 'i': 1, 'u': 'http://d/1', 'h': 0},
        ]),
    ]


def _check_rules(index, metas):
    """跑一遍规则，返回 {规则编号: 错误信息列表}。"""
    errs = {}
    def add(rule, msg):
        errs.setdefault(rule, []).append(msg)

    rows = index['rows']
    want_n = sum(len(m) for _k, m in metas)
    if len(rows) != want_n:
        add('R1', '行数 %d，应为 %d' % (len(rows), want_n))
    if index.get('cols') != ['m', 'y', 'i', 't', 'u']:
        add('R2', 'cols 为 %r' % (index.get('cols'),))

    # 建查表：key_sets 用于 R3 的 O(1) 可寻址判断，first_pos 用于 R7 的期内原序比对。
    # first_pos 只记**首次**出现的下标 —— meta 里 (y,i,u) 可能重复，
    # 取最后一个会让同一份数据得出不稳定的结论。
    by_mag = dict(metas)
    key_sets = {}
    first_pos = {}
    for mag, meta in metas:
        ks = set()
        pos = {}
        for k, a in enumerate(meta):
            ks.add((a['y'], a['i'], a['u'], a['t']))
            k3 = (a['y'], a['i'], a['u'])
            if k3 not in pos:
                pos[k3] = k
        key_sets[mag] = ks
        first_pos[mag] = pos

    for row in rows:
        if len(row) != 5:
            add('R3', '行长度 %d：%r' % (len(row), row))
            continue
        mag, y, i, t, u = row
        if (y, i, u, t) not in key_sets.get(mag, set()):
            add('R3', '索引行在 meta 中找不到对应条目：%r' % (row,))

    # R4 同一刊物内 URL 无重复
    # 注意：**跨刊**允许重复 —— 实测三刊 meta 合计 7415 行、唯一 URL 7413 个，
    # 「网站公告」这篇文章同时列在《求是》和《红旗文稿》的目录里（http/https 各一组）。
    # 那是真实数据，不是索引的错；全局去重会破坏 R1（行数必须等于 meta 条目数之和），
    # 还会丢掉《红旗文稿》的目录条目。
    counts = {}
    uniques = {}
    for row in rows:
        if len(row) != 5:
            continue
        counts[row[0]] = counts.get(row[0], 0) + 1
        uniques.setdefault(row[0], set()).add(row[4])
    for mag in sorted(counts):
        d = counts[mag] - len(uniques[mag])
        if d:
            add('R4', '%s 在索引内有 %d 条重复 URL' % (mag, d))

    size = len(dump_index(index).encode('utf-8'))
    if size > MAX_INDEX_BYTES:
        add('R5', '体积 %d 超过上限 %d' % (size, MAX_INDEX_BYTES))

    # R6 刊物顺序：展示顺序 qs → hqwg → djyj，且同一刊的行必须连续成块
    seen_mags = []
    for row in rows:
        if row[0] not in seen_mags:
            seen_mags.append(row[0])
    if seen_mags != [m for m in MAG_ORDER if m in seen_mags]:
        add('R6', '刊物顺序为 %r' % (seen_mags,))
    blocks = []
    for row in rows:
        if not blocks or blocks[-1] != row[0]:
            blocks.append(row[0])
    if blocks != seen_mags:
        add('R6', '同一刊的行未连续成块，实际分块 %r' % (blocks,))

    # R7 年降、期降、期内保持原顺序
    # 「旧→新」才算违规：a 比 b 旧即 (a.y, a.i) < (b.y, b.i)
    for mag in MAG_ORDER:
        sub = [r for r in rows if r[0] == mag]
        for a, b in zip(sub, sub[1:]):
            if (a[1], a[2]) < (b[1], b[2]):
                add('R7', '%s 段内顺序错：%r 之后是 %r' % (mag, a, b))
                break
        pos = first_pos.get(mag) or {}
        for a, b in zip(sub, sub[1:]):
            if a[1] == b[1] and a[2] == b[2]:
                pa = pos.get((a[1], a[2], a[4]))
                pb = pos.get((b[1], b[2], b[4]))
                if pa is not None and pb is not None and pa > pb:
                    add('R7', '%s 期内顺序被打乱：%r 在 %r 之后' % (mag, a, b))
                    break

    return errs


def self_test():
    metas = _sample_metas()
    index = build_index(metas)

    cases = []

    def case(rule, ok, detail):
        cases.append((rule, ok, detail))

    # ---- C1 正对照：结构完全合规的样本应当零错误 ----
    # 样本里刻意含一条跨刊重复的 URL，所以 C1 同时锁死「跨刊重复 → R4 零错误」
    errs = _check_rules(index, metas)
    case('C1', not errs.get('R1'), '正对照：无 R1 错误')
    case('C1', not errs.get('R2'), '正对照：无 R2 错误')
    case('C1', not errs.get('R3'), '正对照：无 R3 错误')
    case('C1', not errs.get('R4'), '正对照：无 R4 错误（含跨刊重复 URL）')
    case('C1', not errs.get('R5'), '正对照：无 R5 错误')
    case('C1', not errs.get('R6'), '正对照：无 R6 错误')
    case('C1', not errs.get('R7'), '正对照：无 R7 错误')
    case('C1', json.loads(dump_index(index)) == index, '正对照：dump/load 往返一致')

    # ---- C2 空 meta 不炸 ----
    case('C2', build_index([])['rows'] == [], '空 meta 返回空 rows')

    # ---- C3 反向自检：同一刊物内 URL 重复必须被 R4 抓到 ----
    bad = build_index(metas)
    bad['rows'].append(list(bad['rows'][0]))
    e = _check_rules(bad, metas)
    case('C3', 'R4' in e, '反向自检：同刊 URL 重复 → 命中 R4（实际命中 %s）' % (sorted(e.keys()),))

    # ---- C4 反向自检：注入「漏一行」必须被 R1 抓到 ----
    bad = build_index(metas)
    bad['rows'] = bad['rows'][:-1]
    e = _check_rules(bad, metas)
    case('C4', 'R1' in e, '反向自检：漏一行 → 命中 R1（实际命中 %s）' % (sorted(e.keys()),))

    # ---- C5 反向自检：刊别写错必须被 R6 抓到 ----
    bad = build_index(metas)
    if bad['rows']:
        bad['rows'][0][0] = 'hqwg' if bad['rows'][0][0] != 'hqwg' else 'djyj'
    e = _check_rules(bad, metas)
    case('C5', 'R6' in e, '反向自检：刊别写错 → 命中 R6（实际命中 %s）' % (sorted(e.keys()),))

    # ---- C6 反向自检：顺序被打乱必须被 R7 抓到 ----
    bad = build_index(metas)
    if len(bad['rows']) >= 2:
        bad['rows'][0], bad['rows'][1] = bad['rows'][1], bad['rows'][0]
    e = _check_rules(bad, metas)
    case('C6', 'R7' in e, '反向自检：顺序打乱 → 命中 R7（实际命中 %s）' % (sorted(e.keys()),))

    # ---- C7 鉴别力：R1 必须真的因为"少了一行"而失败，
    #      而不是被别的规则先报错才"通过" ----
    bad = build_index(metas)
    bad['rows'] = bad['rows'][:-1]
    e = _check_rules(bad, metas)
    case('C7', e.get('R1') and '行数' in e['R1'][0],
         '鉴别力：R1 的报错说的是行数（实际：%s）' % (e.get('R1'),))

    failed = 0
    print('=' * 64)
    print('索引生成器自检')
    print('=' * 64)
    for rule, ok, detail in cases:
        if not ok:
            failed += 1
        print('  %s %-4s %s' % ('OK  ' if ok else 'FAIL', rule, detail))
    print('')
    print('  用例 %d 条，失败 %d 条' % (len(cases), failed))
    if failed:
        print('❌ 自检未通过')
        return 1
    print('✅ 自检通过')
    return 0
def main():
    if '--self-test' in sys.argv:
        return self_test()
    if '--print-avg' in sys.argv:
        print_avg()
        return 0

    metas = load_metas()
    index = build_index(metas)
    text = dump_index(index)
    size = len(text.encode('utf-8'))

    if size > MAX_INDEX_BYTES:
        print('!! 索引体积 %d 字节，超过上限 %d 字节，拒绝写盘' % (size, MAX_INDEX_BYTES))
        return 1

    if '--check' in sys.argv:
        disk = read_disk()
        if disk is None:
            print('!! 缺少 %s，请先运行 python scripts/build_search_index.py' % INDEX_PATH)
            return 1
        if disk != text.encode('utf-8'):
            print('!! %s 与三份 meta.json 不一致，请重新生成' % INDEX_PATH)
            print('   磁盘 %d 字节 / 应为 %d 字节' % (len(disk), size))
            return 1
        print('OK   %s 与三份 meta.json 一致（%d 字节 / %d 行）'
              % (INDEX_PATH, size, len(index['rows'])))
        return 0

    write_disk(text)
    print('已生成 %s：%d 行，%d 字节（%.1f KB）'
          % (INDEX_PATH, len(index['rows']), size, size / 1024.0))
    return 0
if __name__ == '__main__':
    sys.exit(main())
