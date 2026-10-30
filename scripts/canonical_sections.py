#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""板块名归一表：把"同一个栏目、不同时期的不同写法"统一成一个规范名。

为什么需要
----------
2026-10-30 修完"求是 137 期整期被解析成'目录'"之后，板块页上又暴露出
**同一栏目被拆成多张卡片**的情况。追查发现来源站给同一个栏目在不同时期
用过不同的名字，前端按名字分组就会把一个栏目拆成几个看起来重复的卡片。

三类成因：

  1. **来源站改过栏目名**（求是）
     2025 年第 19、20 期的目录页里专栏名是"体系化学理化研究"，
     从 2025 年第 21 期起改成了"体系化学理化研究阐释"。
     证据（目录页原始 HTML）：
       2025-19  <span style="font-family: 楷体;">体系化学理化研究</span>│<strong>构建21世纪政治经济学的几点思考</strong>
       2025-21  <span style="font-family: 楷体;">体系化学理化研究阐释</span>│<strong>经济发展理念的创新和突破</strong>
     两期是同一条连续的文章系列（"——学习习近平经济思想的XXX"），确属同一栏目。

  2. **同一个名字用了不同的装饰符号**（党建研究）
     来源站在"学习贯彻习近平总书记关于党的建设的重要思想"后面，
     2024 年第 1、2 期用"·"，第 3~7 期改用"●"，其余字完全一样。

  3. **栏目类型前缀时有时无**（党建研究）
     "深入贯彻中央八项规定精神学习教育"这个专题，2025 年第 5、8 期前面
     挂了"专题策划·"，第 7 期没挂 —— 来源站自己的前缀就不统一。
     （"专题策划"本身是刊物的一个栏目类型，2026 年第 8 期还有一组
       主题完全不同的"专题策划"，所以不能把两者并成一个名字。）

原则
----
**只合并有来源站证据的改名，不做"语义相近就归一"的猜测。**
比如党建研究的"调查报告"（2020-12~2025-7）和"调研报告"（2026-2~），
名字虽然像，但来源站是两个不同的标签，且 2020~2022 那批数据是旧版解析器
抓的、板块归属本身不够可靠，**没有合并**，保持来源站原样。

用法
----
    python scripts/canonical_sections.py            # 写盘（归一所有 meta.json）
    python scripts/canonical_sections.py --check     # 只体检，不写盘

体检脚本 check_data.py 会检查：meta 里不应再出现归一表里的旧写法。
"""

import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)

# 归一前的名字 -> 规范名。键、值都按"去空白后"比较。
# 每条都必须在上面的注释里写明来源站证据。
ALIASES = {
    # 求是：专栏改名（2025 年第 21 期起）
    '体系化学理化研究': '体系化学理化研究阐释',

    # 党建研究：同一栏目名用了不同的装饰符号（● / ·）
    '学习贯彻习近平总书记关于党的建设的重要思想●征文':
        '学习贯彻习近平总书记关于党的建设的重要思想·征文',

    # 党建研究：栏目类型前缀"专题策划·"时有时无
    '专题策划·深入贯彻中央八项规定精神学习教育':
        '深入贯彻中央八项规定精神学习教育',
}

# 三本刊的 meta 路径
META_PATHS = {
    'qs': 'data/qs/meta.json',
    'hqwg': 'data/hqwg/meta.json',
    'djyj': 'data/meta.json',
}

_WS_RE = re.compile(r'[\s　\xa0]+')


def strip_ws(name):
    """去掉所有空白（含全角空格 / nbsp）。"""
    return _WS_RE.sub('', name or '')


def canonical(name):
    """把板块名归一成规范名；没在归一表里就原样返回（去空白）。"""
    s = strip_ws(name)
    return ALIASES.get(s, s)


def find_aliases(meta):
    """返回 meta 里仍然使用旧写法的条目。"""
    hits = []
    for a in meta:
        s = strip_ws(a.get('s') or '')
        if s in ALIASES:
            hits.append((a.get('u') or '', s, ALIASES[s]))
    return hits


def apply_to_meta(meta):
    """就地归一 meta 里的板块名，返回 (归一条数, 涉及名字集合)。"""
    changed = 0
    names = set()
    for a in meta:
        s = strip_ws(a.get('s') or '')
        c = ALIASES.get(s)
        if c is not None and c != (a.get('s') or ''):
            a['s'] = c
            changed += 1
            names.add(s + ' -> ' + c)
    return changed, names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true',
                    help='只体检（报告还有哪些旧写法），不写盘')
    args = ap.parse_args()

    total = 0
    for key, rel in META_PATHS.items():
        path = os.path.join(BASE_DIR, rel)
        with open(path, encoding='utf-8') as f:
            meta = json.load(f)

        hits = find_aliases(meta)
        if hits:
            print('[%s] %s' % (key, rel))
            print('    !! 仍有 %d 条使用归一表里的旧写法：' % len(hits))
            for u, old, new in hits[:5]:
                print('       %r -> %r   %s' % (old, new, u))
        else:
            print('[%s] %s  板块名已全部规范' % (key, rel))

        if args.check:
            total += len(hits)
            continue

        changed, names = apply_to_meta(meta)
        if changed:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, separators=(',', ':'))
            print('    已归一 %d 条：%s' % (changed, '、'.join(sorted(names))))
            total += changed

    if args.check:
        print('\n合计仍有旧写法 %d 条' % total)
        return 1 if total else 0
    print('\n合计归一 %d 条' % total)
    return 0


if __name__ == '__main__':
    sys.exit(main())
