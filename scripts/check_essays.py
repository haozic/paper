#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""《荆楚遴选备考全书》第十章第六节「预测热点大作文完整范例」字面体检。

针对本轮新增的八篇大作文范例，做纯文本层面的合规检查（不依赖浏览器）：
  E1 结构完整 —— 八篇齐全，每篇都有【审题立意】/【参考范文】/【亮点批注】三块
  E2 分论点   —— 每篇恰好三个分论点，且同构句式（以"X"领起）
  E3 字数     —— 每篇范文正文 ≥ 900 字
  E4 段落重复 —— 同一篇内不得出现内容完全相同的正文段落（曾真实发生整段复制）
  E5 英文夹杂 —— 不得出现英文单词（仅允许白名单内的专有缩写）
  E6 Markdown —— 纯 HTML 页面不得残留 ** / __ 标记（不会被渲染）
  E7 乱码     —— 不得出现 U+FFFD、非法控制字符、中英粘连
  E8 体例     —— 不得出现感叹号、网络用语、口语化表达
  E9 自证一致 —— 亮点批注里声明的「嵌入 N 处」必须与所列清单条目数一致

用法：
  python -u scripts/check_essays.py             # 体检
  python -u scripts/check_essays.py --self-test # 反向自检：注入事故写法必须被检出
"""
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "hubei-linxuan-guide", "hubei-linxuan-guide.html")

SECTION_HEAD = '<h3 class="section-title">第六节\u3000预测热点大作文完整范例（8篇）</h3>'
SECTION_TAIL = "<!-- ==================== 第十一章 ==================== -->"
ESSAY_HEAD = '<h4 class="subsection-title">范例'
NUM_CN = "一二三四五六七八"

# 允许出现的英文缩写（政策/技术术语）
ALLOWED_ALNUM = {
    "GDP", "AI", "5G", "6G", "IP", "OK", "PDCA", "CEO", "CTO", "IPO", "ICT",
    "IT", "APP", "EU", "US", "3D", "VR", "AR",
}

# 网络用语 / 口语化黑名单
BANNED_WORDS = [
    "点赞", "种草", "打卡", "博主", "内卷", "躺平", "摆烂", "破防", "emo",
    "yyds", "绝绝子", "真香", "好家伙", "拉满", "划重点", "搞事情",
    "棒棒哒", "666", "哈哈哈", "反正就是", "也就是说说",
]

ESSAY_MIN_CHARS = 900


def strip_tags(html):
    """去标签，取可见文本。"""
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    html = re.sub(r"<[^>]+>", "\n", html)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                 ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        html = html.replace(a, b)
    return html


def read_section():
    raw = open(TARGET, "rb").read().decode("utf-8")
    i = raw.find(SECTION_HEAD)
    if i < 0:
        raise SystemExit("FATAL: 未找到第六节标题 '%s'，文件结构可能已改" % SECTION_HEAD)
    j = raw.find(SECTION_TAIL, i)
    if j < 0:
        raise SystemExit("FATAL: 未找到第十一章分隔注释，第六节可能被截断")
    return raw[i:j]


def split_essays(section_html):
    """按 h4 切成八篇，返回 [(编号, 标题, 正文HTML)]。"""
    parts = re.split(r"(?=<h4 class=\"subsection-title\">范例[" + NUM_CN + r"]\u3000)", section_html)
    out = []
    for p in parts:
        m = re.match(r'<h4 class="subsection-title">范例([' + NUM_CN + r'])\u3000(.+?)</h4>', p)
        if m:
            out.append((m.group(1), m.group(2), p))
    return out


def check(section_html):
    """返回 (errors, infos)。errors 非空即失败。"""
    errors = []
    infos = []
    text_all = strip_tags(section_html)

    # ---- E7 乱码 / 非法字符 / 中英粘连 ----
    for ch in ("\ufffd", "\ufffe"):
        if ch in text_all:
            errors.append("E7 出现替换字符 %r（乱码）" % ch)
    if re.search(r"[\u0080-\u009f]", text_all):
        errors.append("E7 出现非法控制字符")
    if re.search(r"[\u4e00-\u9fff][A-Za-z]{2,}[\u4e00-\u9fff]", text_all):
        errors.append("E7 疑似中英粘连（中文之间夹着英文单词）")

    # ---- E5 英文夹杂 ----
    for w in sorted(set(re.findall(r"[A-Za-z]{2,}", text_all))):
        if w.upper() in ALLOWED_ALNUM:
            continue
        errors.append("E5 出现未授权英文单词：%r" % w)

    # ---- E6 Markdown 残留 ----
    if "**" in section_html:
        errors.append("E6 出现 Markdown 加粗标记 **（纯 HTML 不会渲染）")
    if re.search(r"(?<!\w)__(?!\w)", section_html):
        errors.append("E6 出现 Markdown 下划线标记 __")

    # ---- E8 体例：感叹号 / 网络用语 ----
    if "！" in text_all or "!" in text_all:
        errors.append("E8 正文出现感叹号（全书体例为陈述句）")
    for w in BANNED_WORDS:
        if w in text_all:
            errors.append("E8 出现网络用语/口语化词：%r" % w)

    # ---- E1/E2/E3/E4/E9 逐篇 ----
    essays = split_essays(section_html)
    if len(essays) != 8:
        errors.append("E1 范例数量为 %d，应为 8" % len(essays))
    for num, title, body in essays:
        for need in ("【审题立意】", "【参考范文】"):
            if need not in body:
                errors.append("E1 范例%s 缺少 %s" % (num, need))
        if "亮点批注：" not in body:
            errors.append("E1 范例%s 缺少亮点批注" % num)

        m = re.search(r'<p class="example-label">【参考范文】</p>([\s\S]*?)</div>', body)
        if not m:
            errors.append("E1 范例%s 无法定位【参考范文】正文区间" % num)
            continue
        essay_html = m.group(1)
        essay_text = re.sub(r"\s+", "", strip_tags(essay_html))
        n = len(essay_text)
        infos.append("范例%s %s：正文 %d 字" % (num, title[:20], n))
        if n < ESSAY_MIN_CHARS:
            errors.append("E3 范例%s 正文仅 %d 字，低于 %d 字下限" % (num, n, ESSAY_MIN_CHARS))

        subs = re.findall(r"<p>\s*<strong>(以[\u201c\"][^\u201d\"]{1,4}[\u201d\"][^<]{2,40}\u3002)</strong>",
                          essay_html)
        if len(subs) != 3:
            errors.append("E2 范例%s 分论点 %d 个，应为 3 个：%s" % (num, len(subs), subs))
        else:
            for s in subs:
                if not re.match(r"^\u4ee5[\u201c\"][^\u201d\"]{1,4}[\u201d\"]", s):
                    errors.append("E2 范例%s 分论点句式不同构：%s" % (num, s))

        paras = [re.sub(r"\s+", "", x) for x in strip_tags(essay_html).split("\n")]
        paras = [x for x in paras if len(x) >= 40]
        seen = set()
        for x in paras:
            if x in seen:
                errors.append("E4 范例%s 存在完全重复的正文段落：%s…" % (num, x[:36]))
            seen.add(x)

        ann = re.search(r"<div class=\"callout callout-tip\"><strong>亮点批注：</strong>([\s\S]*?)</div>", body)
        if ann:
            ann_text = re.sub(r"\s+", " ", strip_tags(ann.group(1)))
            # 取含「N 处」的那一句，按顿号切分实列条目
            for sent in ann_text.split("\u3002"):
                dec = re.search(r"(\d+)\s*处", sent)
                if not dec:
                    continue
                items = [x for x in sent.split("\u3001") if x.strip()]
                n_declared = int(dec.group(1))
                if len(items) != n_declared:
                    errors.append("E9 范例%s 批注声明 %d 处，该句实列 %d 项，不一致：%s"
                                  % (num, n_declared, len(items), sent[:80]))
                else:
                    infos.append("范例%s 批注声明 %d 处，该句实列 %d 项，一致" % (num, n_declared, len(items)))
                break
    return errors, infos


SELF_TEST_CASES = [
    ("段落整段复制", "E4", "dup"),
    ("英文夹杂", "E5", "fancy"),
    ("Markdown 加粗残留", "E6", "**加粗**"),
    ("乱码替换字符", "E7", "\ufffd"),
    ("中英粘连", "E7", "这是fancy的正文"),
    ("网络用语", "E8", "内卷"),
    ("感叹号", "E8", "！"),
    ("缺审题立意", "E1", "no-lih"),
    ("缺亮点批注", "E1", "no-ann"),
    ("批注数字对不上", "E9", "bad-count"),
    ("分论点只有两个", "E2", "two-subs"),
    ("字数不足", "E3", "short"),
]

# 自检用：合规骨架
CN = list(NUM_CN)
SUB_TPL = ['以"甲"立论，破"一困"。', '以"乙"立论，破"二困"。', '以"丙"立论，破"三困"。']
FILLER = "此处是一段用于自检的占位正文，用来把段落长度撑到阈值以上，同时保证各段内容互不相同。"


def _filler(tag, times=10):
    return (FILLER + tag) * times


def build_essay(idx, defect=None):
    """构造一篇结构合规的自检用范例；defect 用于定点注入事故写法。"""
    cn = CN[idx]
    subs = list(SUB_TPL)
    if defect == "two-subs":
        subs = subs[:2]

    paras = []
    if defect == "dup":
        paras.append("<p>%s</p>" % (_filler("甲段", 12)))
        paras.append("<p>%s</p>" % (_filler("甲段", 12)))
    elif defect == "short":
        paras.append("<p>太短了。</p>")
    else:
        for k, s in enumerate(subs):
            tail = ""
            if defect == "fancy" and k == 0:
                tail = "这里夹了 fancy 这个英文词。"
            elif defect == "**加粗**" and k == 0:
                tail = "这里留了 **加粗** 标记。"
            elif defect == "\ufffd" and k == 0:
                tail = "这里有乱码\ufffd字符。"
            elif defect == "这是fancy的正文" and k == 0:
                tail = "这里有fancy粘连。"
            elif defect == "内卷" and k == 0:
                tail = "这里用了内卷这个词。"
            elif defect == "！" and k == 0:
                tail = "这里有感叹号！"
            paras.append("<p><strong>%s</strong>%s%s</p>" % (s, _filler("第%s段" % (k + 1), 8), tail))

    essay_box = ('<div class="example-box"><p class="example-label">【参考范文】</p>'
                 '<p><strong>自检标题%s</strong></p>%s</div>' % (cn, "".join(paras)))

    if defect == "no-lih":
        lih = ""
    else:
        lih = ('<div class="example-box"><p class="example-label">【审题立意】</p>'
               '<p>身份定位：省直机关干部视角。核心矛盾：供给与需求两头脱节。'
               '政策对标：相关政策文件。价值排序：先急后缓。</p></div>')
    if defect == "no-ann":
        ann = ""
    else:
        if defect == "bad-count":
            ann_txt = "本篇分论点同构，湖北元素共嵌入 3 处（甲、乙）。"
        else:
            ann_txt = "本篇分论点同构，湖北元素共嵌入 2 处（甲、乙）。"
        ann = ('<div class="callout callout-tip"><strong>亮点批注：</strong>%s</div>' % ann_txt)

    return ('<h4 class="subsection-title">范例%s\u3000自检标题%s</h4>%s%s%s'
            % (cn, cn, lih, essay_box, ann))


def build_section(defect=None, defect_idx=0):
    essays = []
    for i in range(8):
        essays.append(build_essay(i, defect if i == defect_idx else None))
    return SECTION_HEAD + "".join(essays) + SECTION_TAIL


def main():
    self_test = "--self-test" in sys.argv
    section = read_section()
    errors, infos = check(section)

    for i in infos:
        print("INFO ", i)
    if errors:
        print("\nFAIL 共 %d 项：" % len(errors))
        for e in errors:
            print("  -", e)
        if not self_test:
            sys.exit(1)
    else:
        print("\nOK  第六节字面体检通过（可见文本 %d 字）" % len(strip_tags(section)))

    if self_test:
        print("\n--- 反向自检（注入事故写法，必须被检出） ---")
        bad = 0

        # 正对照：合规骨架本身必须零错误
        base_errors, _ = check(build_section())
        if base_errors:
            bad += 1
            print("  MISS 正对照（合规骨架）-> 骨架本身报错：%s" % base_errors[0][:70])
        else:
            print("  OK   正对照：合规骨架零错误")

        for name, code, defect in SELF_TEST_CASES:
            e2, _ = check(build_section(defect))
            hit = [x for x in e2 if x.startswith(code)]
            if hit:
                print("  OK   %-14s -> %s" % (name, hit[0][:66]))
            else:
                bad += 1
                got = ("；".join(e2[:2])) if e2 else "（无错误）"
                print("  MISS %-14s -> 期望 %s 命中，实际：%s" % (name, code, got[:80]))
        if bad:
            print("\nFAIL 反向自检 %d 项未达预期" % bad)
            sys.exit(1)
        print("\nOK  反向自检全部达预期（1 正对照 + %d 注入用例）" % len(SELF_TEST_CASES))


if __name__ == "__main__":
    main()
