#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""《湖北省直遴选面试指南》结构与字面体检。

这是手写长文，与《备考全书》第六节那批范例一样容易出低级差错（段落复制、
英文夹杂、乱码、Markdown 标记残留）。脚本覆盖 10 类规则：

  E1 结构完整 —— 八个 chapter 齐全，每章有标题与节；侧边栏 partNames 覆盖全部章号
  E2 目录锚点 —— 目录里每个 href="#xxx" 都能在文档里找到同名 id
  E3 标题层级 —— h2.chapter-title 只出现在 chapter 内，section-title 不越级
  E4 Markdown —— 不得残留 ** / __ 标记（纯 HTML 不渲染）
  E5 英文夹杂 —— 正文不得出现未授权英文单词
  E6 乱码     —— 不得出现替换字符 / 非法控制字符 / 中英粘连
  E7 体例     —— 不得出现感叹号、网络用语、口语化表达（第三方热词表按来源原文录入，
                该表单独从俚语扫描中摘出，定位失败即退回全页扫描）
  E8 段落重复 —— 同一节内不得出现内容完全相同的正文段落
  E9 事实锚点 —— 关键考情数据必须仍在文中（防止后续编辑把依据删掉）
  E10 模拟练习 —— 八道仿真题齐全，参考答案用 details 折叠且默认收起，不得写成空壳

用法：
  python -u scripts/check_mianshi.py             # 体检
  python -u scripts/check_mianshi.py --self-test # 反向自检（1 正对照 + N 注入用例）
"""
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "hubei-linxuan-mianshi", "hubei-linxuan-mianshi.html")

EXPECT_CHAPTERS = 9
EXPECT_TOC = [
    "#ch1", "#ch2", "#ch3", "#ch4", "#ch5", "#ch6", "#ch7", "#ch8", "#ch9",
]

# 模拟练习章：八道仿真题，参考答案默认折叠
PRACTICE_CHAPTER = "ch8"
PRACTICE_COUNT = 8
PRACTICE_MIN_ANSWER = 150

ALLOWED_ALNUM = {
    "GDP", "AI", "5G", "6G", "IP", "OK", "PDCA", "IT", "APP", "EU", "US",
    "3D", "VR", "AR", "PPT", "PDF",
}

BANNED_WORDS = [
    "点赞", "种草", "打卡", "博主", "内卷", "躺平", "摆烂", "破防", "emo",
    "yyds", "绝绝子", "真香", "好家伙", "拉满", "划重点", "搞事情",
    "棒棒哒", "哈哈哈", "反正就是", "也就是说说", "很不错哦",
]

# 关键考情事实：任一条被删掉都说明内容被改坏了
FACT_ANCHORS = [
    ("面试权重 50%", ["×0.5", "0.5"]),
    ("面试权重 40%", ["0.4"]),
    ("专业测试权重 20%", ["0.2"]),
    ("满分100分", ["满分100分"]),
    ("1人面试80分门槛", ["80分"]),
    ("面试测查表述", ["履行职责所要求的基本能力素质"]),
    ("省直20分钟4题", ["20分钟4题"]),
    ("逐题5、5、4、4", ["5、5、4、4"]),
    ("考官7人左右", ["7人左右"]),
    ("放弃不再递补", ["不再进行递补"]),
    ("防止简单以分取人", ["防止简单地以分取人"]),
    ("试用期6个月", ["6个月"]),
    ("公示期5个工作日", ["5个工作日"]),
    ("差额考察2:1", ["2:1"]),
    ("专业测试5:1", ["5:1"]),
    ("资格复审3:1", ["3:1"]),
    ("考场规则八条", ["考场规则八条"]),
    ("普通话作答", ["普通话作答"]),
    ("回答完毕", ["回答完毕"]),
    ("不得透露个人信息", ["不得透露个人信息"]),
    ("五大题型", ["综合分析", "应急应变", "组织协调", "人际关系", "岗位匹配"]),
    ("热点紧扣时政", ["紧扣时政"]),
    ("官方未公布评分表声明", ["官方评分表从未公开"]),
    ("第三方统计口径声明", ["47套"]),
]


def strip_tags(html):
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    html = re.sub(r"<[^>]+>", "\n", html)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                 ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        html = html.replace(a, b)
    return html


def read_page():
    return open(TARGET, "rb").read().decode("utf-8")


# 第三方热词表（表头含"面试涉及的主要热点"）按来源原文录入，其中含"网红"打卡点
# 一类当年时政流行语。那是考试热词的引用，不是本指南的行文用语，故从俚语扫描中
# 摘出这张表；表格以表头定位，表头一旦被改写，定位随即失效并退回全页扫描，
# 即"宁可误报、不可漏报"。
QUOTED_TABLE_MARK = "面试涉及的主要热点"


def drop_quoted_hotword_table(html):
    """把第三方热词表整块摘出，返回处理后的 HTML。"""
    out = []
    pos = 0
    for m in re.finditer(r"<table[\s\S]*?</table>", html):
        if QUOTED_TABLE_MARK in strip_tags(m.group(0)):
            out.append(html[pos:m.start()])
            pos = m.end()
    out.append(html[pos:])
    return "".join(out)


def check(html):
    errors = []
    infos = []

    text_all = strip_tags(html)

    # ---- E1 结构完整 ----
    chapters = re.findall(r'<section class="chapter"[^>]*id="([^"]+)"', html)
    if len(chapters) != EXPECT_CHAPTERS:
        errors.append("E1 章节数为 %d，应为 %d：%s" % (len(chapters), EXPECT_CHAPTERS, chapters))
    else:
        infos.append("章节 %d 个：%s" % (len(chapters), " ".join(chapters)))

    for cid in chapters:
        m = re.search(r'<section class="chapter"[^>]*id="%s">(.*?)</section>' % re.escape(cid),
                      html, re.S)
        if not m:
            errors.append("E1 章节 %s 正文未闭合" % cid)
            continue
        body = m.group(1)
        if not re.search(r'<h2 class="chapter-title">', body):
            errors.append("E1 章节 %s 缺少 chapter-title" % cid)
        if not re.search(r'class="section-title"', body):
            errors.append("E1 章节 %s 没有任何小节" % cid)

    # 侧边栏 partNames 必须覆盖全部章号
    pm = re.search(r"var partNames = \{([\s\S]*?)\};", html)
    if not pm:
        errors.append("E1 找不到侧边栏 partNames 映射")
    else:
        nums = set(int(x) for x in re.findall(r"(\d+):", pm.group(1)))
        missing = [i for i in range(1, EXPECT_CHAPTERS + 1) if i not in nums]
        if missing:
            errors.append("E1 侧边栏 partNames 缺少章号：%s" % missing)

    # ---- E2 目录锚点 ----
    toc_block = re.search(r'<div class="toc">(.*?)</div>\s*</div>\s*</div>', html, re.S)
    if not toc_block:
        errors.append("E2 找不到目录区块")
    else:
        hrefs = re.findall(r'href="(#[^"]+)"', toc_block.group(1))
        ids = set(re.findall(r'id="([^"]+)"', html))
        for h in hrefs:
            if h[1:] not in ids:
                errors.append("E2 目录链接 %s 在正文中没有对应 id" % h)
        if sorted(set(hrefs)) != sorted(EXPECT_TOC):
            errors.append("E2 目录条目与预期不符：%s" % sorted(set(hrefs)))
        else:
            infos.append("目录 %d 条，锚点全部命中" % len(hrefs))

    # ---- E3 标题层级 ----
    for cid in chapters:
        m = re.search(r'<section class="chapter"[^>]*id="%s">(.*?)</section>' % re.escape(cid),
                      html, re.S)
        if not m:
            continue
        body = m.group(1)
        if body.count('<h2 class="chapter-title">') != 1:
            errors.append("E3 章节 %s 的 chapter-title 数量不为 1" % cid)
        for h2 in re.findall(r'<h2 class="chapter-title">.*?</h2>', body, re.S):
            pass
        if re.search(r'<h2 class="section-title"', body):
            errors.append("E3 章节 %s 出现 h2.section-title（层级越级）" % cid)
        # section-title 必须在 chapter-title 之后出现
        ct = body.find('<h2 class="chapter-title">')
        st = body.find('class="section-title"')
        if ct >= 0 and st >= 0 and st < ct:
            errors.append("E3 章节 %s 的小节出现在章标题之前" % cid)

    # ---- E4 Markdown 残留 ----
    if "**" in html:
        errors.append("E4 出现 Markdown 加粗标记 **（纯 HTML 不会渲染）")
    if re.search(r"(?<!\w)__(?!\w)", html):
        errors.append("E4 出现 Markdown 下划线标记 __")

    # ---- E5 英文夹杂（只看可见文本，URL 另行剔除）----
    scan_text = re.sub(r"https?://[^\s，。；、）)】\"]+", " ", text_all)
    for w in sorted(set(re.findall(r"[A-Za-z]{2,}", scan_text))):
        if w.upper() in ALLOWED_ALNUM:
            continue
        errors.append("E5 出现未授权英文单词：%r" % w)

    # ---- E6 乱码 ----
    for ch in ("\ufffd", "\ufffe"):
        if ch in text_all:
            errors.append("E6 出现替换字符 %r（乱码）" % ch)
    if re.search(r"[\u0080-\u009f]", text_all):
        errors.append("E6 出现非法控制字符")
    if re.search(r"[\u4e00-\u9fff][A-Za-z]{2,}[\u4e00-\u9fff]", text_all):
        errors.append("E6 疑似中英粘连（中文之间夹着英文单词）")

    # ---- E7 体例 ----
    if "！" in text_all or "!" in text_all:
        errors.append("E7 正文出现感叹号")
    slang_text = strip_tags(drop_quoted_hotword_table(html))
    for w in BANNED_WORDS:
        if w in slang_text:
            errors.append("E7 出现网络用语/口语化词：%r" % w)

    # ---- E8 段落重复 ----
    for cid in chapters:
        m = re.search(r'<section class="chapter"[^>]*id="%s">(.*?)</section>' % re.escape(cid),
                      html, re.S)
        if not m:
            continue
        paras = [re.sub(r"\s+", "", x) for x in strip_tags(m.group(1)).split("\n")]
        paras = [x for x in paras if len(x) >= 40]
        seen = set()
        for p in paras:
            if p in seen:
                errors.append("E8 章节 %s 存在完全重复的正文段落：%s…" % (cid, p[:36]))
            seen.add(p)

    # ---- E9 事实锚点 ----
    for name, needles in FACT_ANCHORS:
        if not any(n in text_all for n in needles):
            errors.append("E9 关键事实缺失：%s" % name)
    infos.append("关键事实锚点 %d 项全部在位" % len(FACT_ANCHORS))

    # ---- E10 模拟练习结构 ----
    pm = re.search(r'<section class="chapter"[^>]*id="%s">(.*?)</section>'
                   % PRACTICE_CHAPTER, html, re.S)
    if not pm:
        errors.append("E10 找不到第八章（模拟练习）")
    else:
        pbody = pm.group(1)
        blocks = re.findall(r"<details([^>]*)>([\s\S]*?)</details>", pbody)
        if len(blocks) != PRACTICE_COUNT:
            errors.append("E10 模拟题数量为 %d，应为 %d" % (len(blocks), PRACTICE_COUNT))
        for idx, (attrs, inner) in enumerate(blocks, 1):
            if re.search(r"\bopen\b", attrs):
                errors.append("E10 第%d题参考答案默认应折叠，不能带 open 属性" % idx)
            sm = re.search(r"<summary>([\s\S]*?)</summary>", inner)
            if not sm:
                errors.append("E10 第%d题参考答案缺少 summary 标签" % idx)
            else:
                label = strip_tags(sm.group(1)).strip()
                if label != "参考答案":
                    errors.append("E10 第%d题折叠标题应为'参考答案'，实际为 %r" % (idx, label))
            ans = re.sub(r"<summary>[\s\S]*?</summary>", " ", inner)
            if len(re.sub(r"\s+", "", strip_tags(ans))) < PRACTICE_MIN_ANSWER:
                errors.append("E10 第%d题参考答案正文过短（不足 %d 字）"
                              % (idx, PRACTICE_MIN_ANSWER))
        nums = re.findall(r'<h4 class="subsection-title">第(\d+)题', pbody)
        if [int(x) for x in nums] != list(range(1, PRACTICE_COUNT + 1)):
            errors.append("E10 模拟题编号应为 1-%d，实际：%s"
                          % (PRACTICE_COUNT, ",".join(nums) if nums else "无"))
        infos.append("模拟题 %d 道，参考答案折叠结构完整" % len(blocks))

    return errors, infos


SELF_TEST_CASES = [
    ("章节数不对", "E1", "chapters"),
    ("目录锚点悬空", "E2", "toc"),
    ("标题层级越级", "E3", "level"),
    ("Markdown 加粗残留", "E4", "**加粗**"),
    ("英文夹杂", "E5", "fancy"),
    ("乱码替换字符", "E6", "\ufffd"),
    ("感叹号", "E7", "！"),
    ("俚语混入正文", "E7", "打卡正文"),
    ("段落整段复制", "E8", "dup"),
    ("关键事实缺失", "E9", "fact"),
    ("答案默认展开", "E10", "open"),
    ("缺少折叠答案", "E10", "缺折叠"),
    ("答案写成空壳", "E10", "空壳答案"),
]

# 例外不得外溢：把俚语写进第三方热词表时，不应触发 E7（该表按来源原文录入）
NEGATIVE_CASES = [
    ("热词表来源原文", "打卡进热词表", "E7"),
]


def build_variant(defect):
    """在合规页面上定点注入事故写法。"""
    html = read_page()
    if defect == "chapters":
        html = re.sub(r'<section class="chapter" id="ch9">[\s\S]*?</section>\s*',
                      "", html, count=1)
    elif defect == "toc":
        html = html.replace('href="#ch7"', 'href="#chNotExist"', 1)
    elif defect == "level":
        html = html.replace('<h3 class="section-title">第一节 从公告读懂面试</h3>',
                            '<h2 class="section-title">第一节 从公告读懂面试</h2>', 1)
    elif defect == "**加粗**":
        html = html.replace("<p><strong>考点定位：</strong>", "<p>**考点定位：**", 1)
    elif defect == "fancy":
        html = html.replace("考官读题加题本", "考官读题加 fancy 题本", 1)
    elif defect == "\ufffd":
        html = html.replace("结构化面试", "结构化面试\ufffd", 1)
    elif defect == "！":
        html = html.replace("综合分析是绝对主力", "综合分析是绝对主力！", 1)
    elif defect == "打卡正文":
        html = html.replace("考官读题加题本", "考官读题加题本，每天打卡", 1)
    elif defect == "打卡进热词表":
        html = html.replace("坚持发扬斗争精神、", "坚持发扬斗争精神、打卡、", 1)
    elif defect == "dup":
        para = "<p>" + ("这是一段用于检验重复段落检测是否生效的占位正文。" * 6) + "</p>"
        html = html.replace("<p><strong>考点定位：</strong>",
                            para + para + "<p><strong>考点定位：</strong>", 1)
    elif defect == "fact":
        # 该事实在正文出现多处，必须全部替换，只改一处仍会被锚点规则放过
        html = html.replace("满分100分", "满分一百分")
    elif defect == "open":
        html = html.replace('<details class="practice-answer">',
                            '<details class="practice-answer" open>', 1)
    elif defect == "缺折叠":
        html = re.sub(r'<details class="practice-answer">[\s\S]*?</details>',
                      "", html, count=1)
    elif defect == "空壳答案":
        html = re.sub(r'<details class="practice-answer">[\s\S]*?</details>',
                      '<details class="practice-answer"><summary>参考答案</summary>'
                      '<div class="practice-answer-body"><p>略。</p></div></details>',
                      html, count=1)
    return html


def main():
    self_test = "--self-test" in sys.argv
    html = read_page()
    errors, infos = check(html)

    for i in infos:
        print("INFO ", i)
    if errors:
        print("\nFAIL 共 %d 项：" % len(errors))
        for e in errors:
            print("  -", e)
        if not self_test:
            sys.exit(1)
    else:
        print("\nOK  《湖北省直遴选面试指南》体检通过（可见文本 %d 字）" % len(strip_tags(html)))

    if self_test:
        print("\n--- 反向自检（注入事故写法，必须被检出） ---")
        bad = 0
        base_errors, _ = check(read_page())
        if base_errors:
            bad += 1
            print("  MISS 正对照（合规页面）-> 页面本身报错：%s" % base_errors[0][:70])
        else:
            print("  OK   正对照：合规页面零错误")

        for name, code, defect in SELF_TEST_CASES:
            e2, _ = check(build_variant(defect))
            hit = [x for x in e2 if x.startswith(code)]
            if hit:
                print("  OK   %-14s -> %s" % (name, hit[0][:66]))
            else:
                bad += 1
                got = ("；".join(e2[:2])) if e2 else "（无错误）"
                print("  MISS %-14s -> 期望 %s 命中，实际：%s" % (name, code, got[:80]))

        for name, defect, code in NEGATIVE_CASES:
            e2, _ = check(build_variant(defect))
            hit = [x for x in e2 if x.startswith(code)]
            if hit:
                bad += 1
                print("  MISS %-14s -> 不应触发 %s，实际：%s" % (name, code, hit[0][:66]))
            else:
                print("  OK   %-14s -> 未触发 %s（例外仅限引用区）" % (name, code))

        if bad:
            print("\nFAIL 反向自检 %d 项未达预期" % bad)
            sys.exit(1)
        print("\nOK  反向自检全部达预期（1 正对照 + %d 注入用例 + %d 例外用例）"
              % (len(SELF_TEST_CASES), len(NEGATIVE_CASES)))


if __name__ == "__main__":
    main()
