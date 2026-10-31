#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把《求是》《红旗文稿》的目录顺序改回官网目录页的顺序。

问题（2026-10-31 查实）
------------------------
2026-07-27 的历史期批量抓取（commit bd71112）把 2019–2025 年旧期文章
按标题 Unicode 码点排了序，于是站内「目录」里每一期的顺序与官网目录页对不上。
实测：求是 188 期里 163 期是标题序，红旗文稿 164 期里 143 期是标题序；
党建研究与两刊的近期期次（2025 年之后）不受影响。

官网旧期目录页的形态（实测 2021 各期）
--------------------------------------
- 目录页就是「该期第一篇文章」的页面，`.highlight` 容器里是一条扁平的文章列表。
  栏目标题不单独成行（只有「目 录」是页标题），所以旧期的栏目无法从页面恢复；
  但**顺序就是 DOM 顺序**，可以照抄。
- 一期的文章散落在好几个日期目录下（2021 年第 6 期同时出现在 /2021-05/31/ 与
  /2021-06/01/），所以不能用「期号目录」过滤链接（scrape_magazines.py 里的
  issue_path_prefix 对旧期不成立），只能靠本地 meta 的 (年,期) 归属来判定
  某条链接算不算本期文章。

做法
----
1. 从官网 mulu.htm 找到该年的汇总页，汇总页里列出该年各期的目录页；
2. 抓每一期的目录页，按 DOM 顺序取出文章链接；
3. 用本地 meta 的 (年,期) 归属过滤出属于本期的条目；
4. 按官网顺序重排 meta.json 里该期占据的槽位（官网没列出的排在本期末尾）；
5. 把官网顺序写成快照 data/catalog_order.json，供 scripts/check_data.py 离线体检。

用法
----
    python -u scripts/fix_catalog_order.py              # 预演（抓官网出报告，不写盘）
    python -u scripts/fix_catalog_order.py --apply      # 写回 meta.json + 快照
    python -u scripts/fix_catalog_order.py --check      # 离线体检（只用已有快照）
    python -u scripts/fix_catalog_order.py --mag qs --year 2021
"""

import argparse
import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

import scrape_magazines as SM          # noqa: E402  复用现成的请求头 / URL 归一
from refresh_sections import url_key   # noqa: E402  复用现成的 URL 匹配键

SNAPSHOT_REL = 'data/catalog_order.json'
MAGS = [
    ('qs', '求是', 'data/qs/meta.json'),
    ('hqwg', '红旗文稿', 'data/hqwg/meta.json'),
]
DELAY = 0.35          # 抓官网的间隔，别把人家站点打疼


# ---------- 基础工具 ----------

def load_json(rel):
    p = os.path.join(BASE_DIR, rel)
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def save_json(rel, data):
    p = os.path.join(BASE_DIR, rel)
    d = os.path.dirname(p)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))


def fetch(url, tries=3):
    """抓一个页面，拿不到返回 None。"""
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=SM.HEADERS, timeout=20, verify=False)
            if r.status_code == 200:
                r.encoding = r.apparent_encoding
                return r.text
            last = 'HTTP %d' % r.status_code
        except Exception as e:
            last = str(e)
        time.sleep(1.0 + i)
    print('    [抓取失败] %s (%s)' % (url, last))
    return None


def issue_slug(year, issue):
    return '%d-%d' % (year, issue)


# ---------- 官网目录页 ----------

def year_page_url(mag_key, year):
    """官网该年的汇总页地址（沿用抓取脚本的取法）。"""
    try:
        return SM.find_year_aggregate_url(mag_key, year)
    except Exception:
        return None


def issue_catalog_urls(html, base, year):
    """从年度汇总页里找出该年每一期的目录页地址。

    汇总页上每期是一个链接，文字形如「《求是》2021年第3期」。
    """
    out = {}
    for href, txt in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        t = re.sub(r'<[^>]+>', '', txt)
        t = re.sub(r'\s+', '', t)
        m = re.search(r'《[^》]+》%d年第(\d+)期' % year, t)
        if m:
            out[int(m.group(1))] = SM.abs_url(href, base)
    return out


def catalog_links(catalog_url, html):
    """目录页里按 DOM 顺序取出的文章链接（已归一成 URL 匹配键）。

    刻意不用 scrape_magazines.parse_qs_hqwg_catalog：
    它的 issue_path_prefix 按「期号目录」过滤，而旧期一篇文章可能落在
    /2021-05/31/ 这样的相邻日期目录下，会被整段漏掉。
    """
    soup = BeautifulSoup(html, 'html.parser')
    content = (soup.find('div', id='detailContent')
               or soup.find('div', class_='highlight')
               or soup.find('div', class_='text'))
    if not content:
        return []
    out = []
    seen = set()
    for a in content.find_all('a', href=True):
        href = SM.abs_url(a['href'], catalog_url)
        if not href.startswith('http'):
            continue
        k = url_key(href)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


# ---------- 本地 meta ----------

def issue_slots(meta):
    """{期号: [该期条目在 meta 数组里的下标]}（条目在数组里是连续的）。"""
    slots = {}
    for idx, a in enumerate(meta):
        slots.setdefault(issue_slug(a['y'], a['i']), []).append(idx)
    return slots


def local_keys(meta, slug):
    return [url_key(meta[i]['u']) for i in issue_slots(meta)[slug]]


def expected_order(local_key_list, official_key_list):
    """官网在前的顺序 + 本地多出来的（保持原相对顺序，排在末尾）。

    多出来的部分按 URL 的**出现次数**算：同一个 URL 在本地出现两次，
    官网只列了一次，那多出来的那一条也得留下，不能凭空消失。
    """
    official = []
    seen = set()
    for k in official_key_list:
        if k in local_key_list and k not in seen:
            official.append(k)
            seen.add(k)
    remaining = list(local_key_list)
    for k in official:
        remaining.remove(k)          # 只扣掉一次，重复出现的保留
    return official, remaining


def reorder_meta(meta, orders):
    """把每一期占据的槽位按新顺序重新分配条目（不改动期与期之间的排布）。

    注意：读源必须用 meta 的拷贝。旧版本写成 new_meta[slot] = new_meta[by_key[k]]，
    边写边读会把还没搬走的条目冲掉 —— 2021 年第 1 期实测丢了 7 篇文章。
    """
    src = list(meta)
    slots = issue_slots(meta)
    new_meta = list(meta)
    for slug, (official, extra) in orders.items():
        idxs = slots.get(slug)
        if not idxs:
            continue
        by_key = {}
        for i in idxs:
            by_key.setdefault(url_key(src[i]['u']), []).append(i)
        wanted = official + extra
        if len(wanted) != len(idxs):
            continue
        for slot, k in zip(idxs, wanted):
            lst = by_key.get(k)
            if lst:
                new_meta[slot] = src[lst.pop(0)]
    return new_meta


def issue_multiset(meta):
    """{期号: 该期 URL 的多重集}，用于校验重排没有丢文章。"""
    out = {}
    for a in meta:
        out.setdefault(issue_slug(a['y'], a['i']), []).append(url_key(a['u']))
    return {k: sorted(v) for k, v in out.items()}


def verify_reorder(before, after):
    """重排只许换顺序，不许换内容。返回不一致的期号列表。"""
    mb, ma = issue_multiset(before), issue_multiset(after)
    bad = []
    for slug, keys in mb.items():
        if ma.get(slug) != keys:
            bad.append(slug)
    return bad


# ---------- 主流程 ----------

def mag_cover_candidates(mag_key):
    """mulu.htm 里的当期封面页（新格式的 c.html）。

    年度汇总页只列到当期为止，最近这一期往往不在列表里，
    但当期封面页本身带目录，可以补上。
    """
    try:
        conf = SM.MAGAZINES[mag_key]
    except KeyError:
        return []
    html = fetch(conf['catalog_url'])
    if not html:
        return []
    out = []
    for h in re.findall(r'href="([^"]*c\.html)"', html):
        u = SM.abs_url(h, conf['catalog_url'])
        if u not in out:
            out.append(u)
    return out


def collect(mag_key, name, meta_rel, years=None, verbose=True):
    """抓官网，产出 {期号: (官网顺序, 本地多出来的)}。"""
    meta = load_json(meta_rel)
    if meta is None:
        print('[%s] 缺少 %s' % (mag_key, meta_rel))
        return None, {}

    key_to_issue = {}
    for a in meta:
        key_to_issue.setdefault(url_key(a['u']), issue_slug(a['y'], a['i']))

    all_years = sorted({a['y'] for a in meta})
    if years:
        all_years = [y for y in all_years if y in years]

    covers = mag_cover_candidates(mag_key)
    orders = {}
    for year in all_years:
        yurl = year_page_url(mag_key, year)
        cat_urls = {}
        if yurl:
            yhtml = fetch(yurl)
            if yhtml:
                cat_urls = issue_catalog_urls(yhtml, yurl, year)
                time.sleep(DELAY)
        if not cat_urls:
            print('  [%s] %d 年：官网汇总页取不到，改用当期封面页' % (name, year))

        local_slugs = set(s for s in issue_slots(meta) if s.startswith('%d-' % year))
        # 年汇总页没列出的期次（如最近一期），用当期封面页兜底
        for slug in sorted(local_slugs - set(cat_urls)):
            issue = int(slug.split('-')[1])
            for cover in covers:
                html = fetch(cover)
                if not html:
                    continue
                links = catalog_links(cover, html)
                mine = [k for k in links if key_to_issue.get(k) == slug]
                if mine:
                    cat_urls[issue] = cover
                    if verbose:
                        print('    %s: 汇总页没列，从当期封面页补上（%s）' % (slug, cover[-28:]))
                    break
                time.sleep(DELAY)

        for issue in sorted(cat_urls):
            slug = issue_slug(year, issue)
            if slug not in issue_slots(meta):
                continue
            html = fetch(cat_urls[issue])
            time.sleep(DELAY)
            if not html:
                continue
            links = catalog_links(cat_urls[issue], html)
            mine = [k for k in links if key_to_issue.get(k) == slug]
            lk = local_keys(meta, slug)
            official, extra = expected_order(lk, mine)
            orders[slug] = (official, extra)
            if verbose:
                flag = '官网列全' if not extra else '官网缺 %d 条' % len(extra)
                print('    %s: 官网 %d 条 / 本地 %d 条 / %s' % (slug, len(official), len(lk), flag))
    return meta, orders


def check_offline():
    """离线体检：meta 里的顺序是否与快照一致。"""
    snap = load_json(SNAPSHOT_REL)
    if snap is None:
        print('缺少快照 %s，先跑一次 fix_catalog_order.py --apply' % SNAPSHOT_REL)
        return 1
    bad = 0
    for key, name, meta_rel in MAGS:
        meta = load_json(meta_rel) or []
        slots = issue_slots(meta)
        for slug, rec in sorted((snap.get(key) or {}).items()):
            want = list(rec.get('o') or []) + list(rec.get('x') or [])
            have = local_keys(meta, slug) if slug in slots else []
            if have != want:
                bad += 1
                print('  !! %s %s 顺序与官网快照不一致' % (name, slug))
    print('离线体检: %d 处不一致' % bad)
    return 1 if bad else 0


def _buggy_reorder_meta(meta, orders):
    """旧版实现：边写边读，会把还没搬走的条目冲掉（曾实测丢了 7 篇文章）。

    只用于反向自检 —— 必须能被 verify_reorder 抓出来。
    """
    slots = issue_slots(meta)
    new_meta = list(meta)
    for slug, (official, extra) in orders.items():
        idxs = slots.get(slug)
        if not idxs:
            continue
        by_key = {}
        for i in idxs:
            by_key.setdefault(url_key(new_meta[i]['u']), i)
        wanted = official + extra
        if len(wanted) != len(idxs):
            continue
        for slot, k in zip(idxs, wanted):
            if k in by_key:
                new_meta[slot] = new_meta[by_key[k]]
    return new_meta


def self_test():
    """自检：重排只换顺序不换内容；反向自检证明校验真能抓到事故写法。"""
    ok = 0
    fail = 0

    def check(name, cond):
        nonlocal ok, fail
        if cond:
            ok += 1
            print('  [OK] %s' % name)
        else:
            fail += 1
            print('  [FAIL] %s' % name)

    print('--- 正对照 ---')
    meta = [
        {'t': '甲', 'u': 'http://x/dukan/qs/2021-01/01/c_1.htm', 'y': 2021, 'i': 1},
        {'t': '乙', 'u': 'http://x/dukan/qs/2021-01/01/c_2.htm', 'y': 2021, 'i': 1},
        {'t': '丙', 'u': 'http://x/dukan/qs/2021-01/01/c_3.htm', 'y': 2021, 'i': 1},
        {'t': '丁', 'u': 'http://x/dukan/qs/2021-02/01/c_4.htm', 'y': 2021, 'i': 2},
    ]
    k1 = url_key('http://x/dukan/qs/2021-01/01/c_1.htm')
    k2 = url_key('http://x/dukan/qs/2021-01/01/c_2.htm')
    k3 = url_key('http://x/dukan/qs/2021-01/01/c_3.htm')
    k4 = url_key('http://x/dukan/qs/2021-02/01/c_4.htm')
    orders = {'2021-1': ([k2, k3, k1], [])}
    out = reorder_meta(meta, orders)
    got = [url_key(a['u']) for a in out[:3]]
    check('重排后第 1 期顺序 = 官网顺序', got == [k2, k3, k1])
    check('第 2 期不受影响', url_key(out[3]['u']) == k4)
    check('重排不改变每期文章集合', verify_reorder(meta, out) == [])
    check('条目总数不变', len(out) == len(meta))
    check('标题跟着条目走（不是只换 URL）', out[0]['t'] == '乙')

    # 官网没列出的条目应排在本期末尾，且保持原相对顺序
    meta2 = [
        {'t': '甲', 'u': 'http://x/dukan/qs/2021-01/01/c_1.htm', 'y': 2021, 'i': 1},
        {'t': '乙', 'u': 'http://x/dukan/qs/2021-01/01/c_2.htm', 'y': 2021, 'i': 1},
        {'t': '丙', 'u': 'http://x/dukan/qs/2021-01/01/c_3.htm', 'y': 2021, 'i': 1},
    ]
    off, extra = expected_order([k1, k2, k3], [k3])
    check('官网只列 1 条时，多出的 2 条进 extra', off == [k3] and extra == [k1, k2])
    out2 = reorder_meta(meta2, {'2021-1': (off, extra)})
    check('多出的条目排在本期末尾', [url_key(a['u']) for a in out2] == [k3, k1, k2])

    print('--- 反向自检（注入事故写法，校验必须抓到）---')
    bad_out = _buggy_reorder_meta(meta, orders)
    check('旧版就地覆盖实现被校验抓到（不能为空）', verify_reorder(meta, bad_out) != [])
    check('旧版实现确实改变了文章集合', sorted(url_key(a['u']) for a in bad_out) !=
          sorted(url_key(a['u']) for a in meta))
    check('正确实现通过同一条校验', verify_reorder(meta, reorder_meta(meta, orders)) == [])

    print('--- 例外用例 ---')
    dup = [
        {'t': '甲', 'u': 'http://x/dukan/qs/2021-01/01/c_1.htm', 'y': 2021, 'i': 1},
        {'t': '甲2', 'u': 'http://x/dukan/qs/2021-01/01/c_1.htm', 'y': 2021, 'i': 1},
        {'t': '乙', 'u': 'http://x/dukan/qs/2021-01/01/c_2.htm', 'y': 2021, 'i': 1},
    ]
    off2, extra2 = expected_order([k1, k1, k2], [k2, k1])
    check('同 URL 重复条目只保留一次在 official 里', off2 == [k2, k1])
    check('重复条目进 extra（不会被丢掉）', extra2 == [k1])
    out3 = reorder_meta(dup, {'2021-1': (off2, extra2)})
    check('重复条目的期次集合不变', verify_reorder(dup, out3) == [])

    print('\n自检结果：通过 %d 项，失败 %d 项' % (ok, fail))
    return 1 if fail else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='写回 meta.json 与顺序快照')
    ap.add_argument('--check', action='store_true', help='只用已有快照离线体检')
    ap.add_argument('--self-test', action='store_true', help='跑重排逻辑的自检')
    ap.add_argument('--mag', help='只处理某一本（qs / hqwg）')
    ap.add_argument('--year', type=int, help='只处理某一年')
    args = ap.parse_args()

    if args.self_test:
        sys.exit(self_test())

    if args.check:
        sys.exit(check_offline())

    years = [args.year] if args.year else None
    snapshot = load_json(SNAPSHOT_REL) or {}
    total_changed = 0
    for key, name, meta_rel in MAGS:
        if args.mag and args.mag != key:
            continue
        print('[%s] %s' % (key, name))
        meta, orders = collect(key, name, meta_rel, years)
        if meta is None:
            continue
        changed = []
        for slug, (official, extra) in sorted(orders.items()):
            lk = local_keys(meta, slug)
            want = official + extra
            if lk != want:
                changed.append(slug)
        total_changed += len(changed)
        print('  -> 需重排 %d 期（共 %d 期）' % (len(changed), len(orders)))
        if changed:
            print('     %s' % ', '.join(changed[:12]) + (' ...' if len(changed) > 12 else ''))

        if args.apply:
            new_meta = reorder_meta(meta, orders)
            # 硬性不变量：重排只许换顺序，每一期的文章集合必须前后完全一致。
            # 一旦对不上就地拒绝写盘，绝不拿半坏的 meta.json 覆盖好的。
            bad = verify_reorder(meta, new_meta)
            if bad:
                print('  !! 重排校验不通过，以下期别的文章集合发生了变化，已放弃写盘：')
                print('     %s' % ', '.join(bad[:12]))
                return 1
            if new_meta != meta:
                save_json(meta_rel, new_meta)
                print('  已写回 %s' % meta_rel)
            snap_mag = snapshot.setdefault(key, {})
            for slug, (official, extra) in orders.items():
                snap_mag[slug] = {'o': official, 'x': extra}
            save_json(SNAPSHOT_REL, snapshot)
            print('  已写回 %s' % SNAPSHOT_REL)

    print('\n合计需重排 %d 期%s' % (total_changed, '（已写盘）' if args.apply else '（预演，未写盘）'))


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
