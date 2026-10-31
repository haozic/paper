#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
清洗 meta.json 里被网页页脚污染的"作者"字段。

问题（2026-10-31 查实）
----------------------
《求是》2019 年以后每一期的《经济社会发展统计图表》系列，目录页上并没有单独的
作者署名，抓取脚本把整段正文（包括发布时间、扫码提示、网站声明、评论引导）
当成了作者，写进了 meta 的 a 字段。实测 166 条，线上目录里会显示成：

    经济社会发展统计图表：… ｜国家统计局2019-01-16 09:00:00扫描二维码分享到手机
    标签 -网站编辑 - 赵雁【网站声明】【纠错】【打印】评论登录新浪微博@求是发表
    评论。请您文明上网、理性发言并遵守相关规…

清洗规则
--------
作者字段里一旦出现发布时间（YYYY-MM-DD）或网页页脚特征串，就在它之前截断。
对受影响的 166 条而言，截出来的作者统一是「国家统计局」——正是官网上的署名。
其余条目一律不动。

用法：
    python -u scripts/clean_meta_authors.py            # 预演（打印将被改的条目）
    python -u scripts/clean_meta_authors.py --apply    # 写回 meta.json
    python -u scripts/clean_meta_authors.py --self-test
"""

import argparse
import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)

MAGS = [
    ('qs', '求是', 'data/qs/meta.json'),
    ('hqwg', '红旗文稿', 'data/hqwg/meta.json'),
    ('djyj', '党建研究', 'data/meta.json'),
]

# 网页页脚的特征串
JUNK_MARKS = [
    '扫描二维码分享到手机', '扫一扫', '【网站声明】', '【纠错】', '【打印】',
    '标签 -网站编辑', '发表评论', '请您文明上网', '责任编辑', '打印本页',
    '分享到', '微博', '微信', '上一篇', '下一篇', '返回顶部', '版权所有',
]

# 发布时间
DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')


def clean_author(author):
    """返回清洗后的作者；没有污染就原样返回。"""
    s = (author or '').strip()
    if not s:
        return author
    cut = len(s)
    m = DATE_RE.search(s)
    if m:
        cut = min(cut, m.start())
    for mark in JUNK_MARKS:
        i = s.find(mark)
        if i >= 0:
            cut = min(cut, i)
    if cut >= len(s):
        return author
    out = s[:cut].strip()
    # 截断后可能留下尾部标点
    out = out.rstrip(' 　、，,；;：:·-—')
    return out


def load(rel):
    with open(os.path.join(BASE_DIR, rel), encoding='utf-8') as f:
        return json.load(f)


def save(rel, data):
    with open(os.path.join(BASE_DIR, rel), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))


def scan(meta):
    """返回被污染的条目列表 [(下标, 原作者, 清洗后)]。"""
    out = []
    for i, a in enumerate(meta):
        new = clean_author(a.get('a'))
        if new != a.get('a'):
            out.append((i, a.get('a'), new))
    return out


def self_test():
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
    check('正常的作者不受影响',
          clean_author('白春礼') == '白春礼')
    check('空作者不受影响', clean_author('') == '')
    check('None 不受影响', clean_author(None) is None)
    check('长机构名不受影响',
          clean_author('中共中央党史和文献研究院') == '中共中央党史和文献研究院')
    check('带括号的署名不受影响',
          clean_author('同 心') == '同 心')

    dirty = '国家统计局2019-01-16 09:00:00（国家统计局提供）扫描二维码分享到手机标签 -网站编辑 - 赵雁【网站声明】【纠错】【打印】评论登录新浪微博@求是发表评论。请您文明上网、理性发言并遵守相关规'
    check('发布时间前的部分被保留', clean_author(dirty) == '国家统计局')
    check('页脚被切掉', '扫描二维码' not in clean_author(dirty))
    check('评论引导被切掉', '发表评论' not in clean_author(dirty))

    check('没有日期但有页脚时也截断',
          clean_author('某作者扫描二维码分享到手机') == '某作者')
    check('尾部标点被去掉',
          clean_author('某作者、2020-01-01 09:00:00') == '某作者')

    print('--- 反向自检（注入事故写法，校验必须抓到）---')
    # 事故写法：只按整串精确匹配，遇到带日期变体就漏
    def buggy(author):
        s = (author or '').strip()
        if s.startswith('国家统计局2019-01-16 09:00:00（国家统计局提供）扫描二维码分享到手机标签 -网站编辑 - 赵雁【网站声明】【纠错】【打印】评论登录新浪微博@求是发表评论。请您文明上网、理性发言并遵守相关规'):
            return '国家统计局'
        return author

    variant = '国家统计局2020-05-16 09:00:00扫描二维码分享到手机标签 -网站编辑 - 张芯蕊【网站声明】【纠错】【打印】'
    check('事故写法漏掉了变体（说明必须用规则而不是整串匹配）',
          buggy(variant) != '国家统计局')
    check('正确规则能处理该变体', clean_author(variant) == '国家统计局')

    print('--- 例外用例 ---')
    check('作者里带四位数字但不是日期的不被误伤',
          clean_author('中共中央党史和文献研究院') == '中共中央党史和文献研究院')
    check('只截一次不会重复截',
          clean_author(clean_author(dirty)) == '国家统计局')

    print('\n自检结果：通过 %d 项，失败 %d 项' % (ok, fail))
    return 1 if fail else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='写回 meta.json')
    ap.add_argument('--self-test', action='store_true', help='跑清洗规则的自检')
    args = ap.parse_args()

    if args.self_test:
        sys.exit(self_test())

    total = 0
    for key, name, rel in MAGS:
        meta = load(rel)
        bad = scan(meta)
        total += len(bad)
        print('[%s] %s: %d 条作者字段被污染' % (key, name, len(bad)))
        for i, old, new in bad[:3]:
            print('    %d-%d  %s' % (meta[i]['y'], meta[i]['i'], (meta[i].get('t') or '')[:30]))
            print('       旧: %s' % (old or '')[:64])
            print('       新: %s' % new)
        if args.apply and bad:
            for i, old, new in bad:
                meta[i]['a'] = new
            save(rel, meta)
            print('  已写回 %s' % rel)
        elif bad:
            print('  （预演，未写盘）')
    print('\n合计需要清洗 %d 条%s' % (total, '（已写盘）' if args.apply else '（预演，未写盘）'))


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
