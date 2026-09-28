"""对话内分镜脚本（v0.3.5）—— 生图前给用户看的精简版。

为什么需要这个：
    生图很贵（12 页通常十几分钟 + 额度），而且用户反馈过「以往生图总是
    很多次才能成功」。所以必须先把**文字内容和画面意图的匹配**确认掉，
    再决定跑不跑图。

    但之前给用户的产物有两类问题：
      1. storyboard.json —— 多层嵌套，人读不了
      2. 排版预览 HTML —— 要开文件，而且展示的是"渲染后长什么样"，
         不是"这张图打算画什么"

    本模块解决的是第三个问题：**一屏之内读完全部分镜**，
    左边是文字说什么，右边是画面打算画什么，逐页对齐。

设计原则：
    - 对话里直接可读，不依赖开文件
    - 每页三行：章节题 / 文字说什么 / 画面画什么
    - 画面摘要从七要素 visual 里自动抽取（SUBJECT/ACTION/关键元素），
      不倒出 800 字英文原文
    - 匹配问题自动标出来，用户一眼看到哪几页图文不符
"""
from __future__ import annotations

import re

# 从七要素 visual 里抽要素标签（planner prompt 约定的段名）
_SEG_PATTERNS = {
    "subject": re.compile(r"\bSUBJECT\s*\d*\s*[:：]\s*([^;.]+)", re.I),
    "action": re.compile(r"\bACTION\s*[:：]\s*([^;.]+)", re.I),
    "secondary": re.compile(r"\b(?:SECONDARY|SUBJECT\s*2|ACCOMPANIED BY)\s*[:：]\s*([^;.]+)", re.I),
    "background": re.compile(r"\bBACKGROUND\s*[:：]\s*([^;.]+)", re.I),
    "camera": re.compile(r"\bCAMERA\s*[:：]\s*([^;.]+)", re.I),
    "mood": re.compile(r"\bMOOD\s*[:：]\s*([^;.]+)", re.I),
}


def _tidy(s: str, limit: int = 46) -> str:
    """把英文要素压成紧凑速记：去冗余虚词、去尾部修饰、统一用中文标点。"""
    t = re.sub(r"\[[^\]]*\]", "", s or "")
    t = re.sub(r"\s+", " ", t).strip(" ,;:-.")
    t = re.sub(r"\b(\w+)\s+(and|with|on|in|of|at|to)\s+", r"\1 ", t, flags=re.I)
    t = re.sub(r"\s*,\s*(and|with|or)\s*", " ", t, flags=re.I)
    # 常见英文冗余词删掉（对用户判断画面没帮助）
    for junk in ("clearly", "clearly visible", "visible", "detailed", "realistic",
                 "the ", "a ", "an ", "is ", "are ", "being "):
        t = re.sub(r"\b" + junk + r"\b", "", t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,;:-.")
    if len(t) > limit:
        t = t[:limit].rstrip(" ,;:-.") + "…"
    return t


# 画面描述里高频人名/道具 → 中文速记。用户看的是"画面讲什么故事"，
# 不是英文 prompt。
# v0.3.5 修正：上一版做了逐词替换，产出 "雪y" / "跪ing" / "芦苇荡s" 这类
# 拼接垃圾，比英文原文更难读。现在策略是：
#   - 人名/道具：整词替换（Su Wu -> 苏武，安全）
#   - 动作动词：整词替换（kneeling -> 跪姿，安全）
#   - 认不出的：**整句保留英文**，宁可保留也不误导。
_ENTITY_ZH = {
    "Su Wu": "苏武", "Li Ling": "李陵", "Zhang Zhong": "张中",
    "Chang Hui": "常惠", "Xiongnu Khan": "匈奴单于",
    "Han Envoy": "汉使", "Han envoy": "汉使", "Han spy": "汉使密探",
    "Emperor Zhaodi": "汉昭帝", "Emperor Guangwu": "汉光武帝",
    "Emperor": "皇帝", "Zhaodi": "昭帝", "Guangwu": "光武帝",
    "bamboo staff": "竹杖旌节", "staff": "旌节", "sheep": "羊群",
    "sparrow": "飞鸟", "camp tents": "军帐", "city gate": "城门",
    "palace interior": "宫殿", "cave interior": "洞穴",
    "dark pine forest": "松林", "reeds": "芦苇荡", "steppe": "草原",
}
_VERB_ZH = {
    "kneeling": "跪地", "kneels": "跪地", "bows": "躬身", "bowing": "躬身",
    "shouting": "呼喊", "weeping": "落泪", "crying": "落泪",
    "eating": "进食", "drinking": "饮水", "herding": "牧羊",
    "walking": "行走", "running": "奔跑", "holding": "手捧",
    "presenting": "呈献", "dismounting": "下马", "saluting": "行礼",
    "escorted": "被押送", "leading": "率领", "signaling": "打手势",
    "toasting": "举杯", "slamming": "猛砸", "pulling": "拉扯",
}
# 这些词出现说明主体抽的是长描述，直接放弃翻译更诚实
_SKIP_TRANSLATE = re.compile(
    r"wearing|hair|beard|robe|coat|armor|garment|aged|age |yo\b|"
    r"tattered|formal|wearing|holding a |tall|slim|thick|thin",
    re.I,
)


def _zh(s: str) -> str:
    """整词替换人名/道具/动词；其余原样保留。"""
    t = s
    for table in (_ENTITY_ZH, _VERB_ZH):
        for en, zh in table.items():
            t = re.sub(r"\b" + re.escape(en) + r"\b", zh, t, flags=re.I)
    return t


def _seg(visual: str, key: str, limit: int = 46) -> str:
    """抽要素段并转成中文速记。

    v0.3.5 两次修正的教训：逐词替换 LLM 的自由英文表达必然产出中英混杂的
    垃圾（"Su Wu, 30yo Han envoy , wearing formal dark ro" / "苏武 跪地 snow"），
    比原文更难读。翻译表永远追不上 LLM 的措辞自由。

    现在的可靠策略 —— **抽取而非翻译**：
      1. 扫出整句里所有已知的**中文可译片段**（人名/道具/动作），
         按出现顺序拼成中文短语
      2. 译不出任何实质内容 → 保留英文原句（诚实，不误导）
    这样要么给出干净中文，要么给出完整英文，不会出现拼接残骸。
    """
    m = _SEG_PATTERNS[key].search(visual or "")
    if not m:
        return ""
    s = re.sub(r"\[GENDER:\w+\]", "", m.group(1).strip().rstrip(".;"))
    if not s:
        return ""

    # 1) 按出现位置收集所有可译片段
    hits: list[tuple[int, str]] = []
    for table in (_ENTITY_ZH, _VERB_ZH):
        for en, zh in table.items():
            for m2 in re.finditer(re.escape(en), s, flags=re.I):
                hits.append((m2.start(), zh))
    # 去重叠（同一片段内，长词优先：bamboo staff 先于 staff）
    hits.sort(key=lambda x: (x[0], -len(x[1])))
    picked: list[tuple[int, str]] = []
    last_end = -1
    for pos, zh in hits:
        if pos >= last_end:
            picked.append((pos, zh))
            last_end = pos + len(zh)

    # 去冗余：若某个译词包含另一个译词，只保留长的（竹杖旌节 吃掉 旌节）
    zh_parts = [zh for _, zh in picked]
    zh_parts = [
        z for z in zh_parts
        if not any(z != other and z in other for other in zh_parts)
    ]
    if zh_parts:
        out = " ".join(dict.fromkeys(zh_parts))   # 去重保序
        return _tidy(out, limit)

    # 2) 译不出 → 保留英文原句
    return _tidy(s, limit)


def _first_clause(text: str, limit: int = 60) -> str:
    """取第一句（按中文句号/问号/叹号断）。"""
    t = (text or "").strip()
    if not t:
        return ""
    for sep in ("。", "？", "！"):
        i = t.find(sep)
        if 0 < i <= limit + 20:
            return t[:i + 1]
    return t if len(t) <= limit else t[:limit].rstrip() + "…"


def render_page(p: dict) -> str:
    """单页三行块：章节题 / 文字 / 画面。"""
    no = p.get("page", "?")
    hl = p.get("highlight") or ""
    cap = (p.get("caption") or "").strip()
    body = (p.get("body") or "").strip()
    visual = p.get("visual") or ""
    kws = p.get("keywords") or []

    head = f"**p{no:02d}**"
    if hl:
        head += f" {hl}"
    if cap:
        head += f" — {cap}"

    lines = [head]

    # 文字侧：正文首句 + 字数；关键词单独一行
    b1 = _first_clause(body)
    if b1:
        lines.append(f"　　文字：{b1}（{len(body)} 字）")
    elif body:
        lines.append(f"　　文字：{body[:40]}…（{len(body)} 字）")
    if kws:
        lines.append("　　高亮：" + " · ".join(kws[:5]))

    # 画面侧：主体 + 动作 + 次要人物
    subj = _seg(visual, "subject")
    act = _seg(visual, "action")
    sec = _seg(visual, "secondary")
    bg = _seg(visual, "background")

    pic_parts = []
    if subj:
        pic_parts.append(subj)
    if act:
        pic_parts.append(act)
    if sec:
        pic_parts.append("配角 " + sec)
    if bg:
        pic_parts.append(bg)
    if pic_parts:
        lines.append("　　画面：" + " / ".join(pic_parts))
    elif visual:
        lines.append("　　画面：" + _first_clause(visual, 80))
    else:
        lines.append("　　画面：（空）")

    return "\n".join(lines)


def render_script(raw: dict, health: dict | None = None,
                  alignment: dict | None = None) -> str:
    """整篇分镜脚本（对话内可读）。"""
    pages = raw.get("pages", [])
    title = raw.get("title") or raw.get("topic", "")
    style = raw.get("style_id", "")
    tpl = raw.get("recommended_template", "?")

    out: list[str] = []
    out.append(f"## 《{title}》分镜脚本 · {len(pages)} 页")
    if raw.get("subtitle"):
        out.append(f"*{raw['subtitle']}*")
    out.append(f"`{style}` · 模板 `{tpl}`")
    out.append("")
    out.append("**确认顺序：文字说什么 → 画面画什么 → 是否对得上**")
    out.append("")

    for p in pages:
        out.append(render_page(p))
        out.append("")

    # 体检摘要（只在有问题时提）
    if health and health["stats"]["errors"]:
        s = health["stats"]
        bad = sorted({i.page for i in health["issues"] if i.level == "error"})
        out.append("---")
        out.append(f"⚠️ 必修 {s['errors']} 项，涉及页 {bad}")

    if alignment:
        risky = [r for r in alignment.get("results", [])
                 if r.get("severity") in ("high", "medium")]
        if risky:
            out.append("---")
            out.append("### ⚠️ 图文不符风险（跑图前建议先改）")
            out.append("")
            for r in risky:
                no = r["page"]
                page = next((x for x in pages if x.get("page") == no), {})
                tag = "🔴" if r["severity"] == "high" else "🟡"
                out.append(f"{tag} **p{no:02d}** {page.get('highlight', '')}")
                miss_a = r.get("caption_missing_actions") or []
                miss_e = r.get("caption_missing_entities") or []
                if miss_a:
                    out.append(f"　　caption 里的动作画面没画：**{'、'.join(miss_a)}**")
                if miss_e:
                    out.append(f"　　caption 里的人物画面没画：**{'、'.join(miss_e)}**")
                ba = r.get("body_missing_actions") or []
                be = r.get("body_missing_entities") or []
                if len(ba) >= 2:
                    out.append(f"　　正文提到但画面没画的动作：{'、'.join(ba)}")
                if len(be) >= 2:
                    out.append(f"　　正文提到但画面没画的人物：{'、'.join(be)}")
                out.append("")

    return "\n".join(out).rstrip() + "\n"
