# -*- coding: utf-8 -*-
"""分镜要素抽取（v0.3.6）。

用途：**把分镜内容直接嵌进 layout_preview.html**。
用户在生图前打开**一个文件**就能同时看到
  - 文章排版效果（模板渲染的成品版式）
  - 每个图位旁这页分镜要画什么（主体 / 动作 / 配角 / 背景 / 景别 / 情绪）
从而确认「文字说的」和「画面画的」对不对得上，确认后再跑图、生图、推公众号。

为什么不再单独出一个"分镜脚本"文件：
    用户要的是**一个地方**看全部。拆成两个文件等于让用户两边对照，反而
    增加负担。所以分镜内容作为 layout_preview 的内嵌区块。

设计原则 —— 抽取而非翻译：
    LLM 的英文表述自由，翻译表永远追不上，逐词替换必然产出
    「雪y / 跪ing / 芦苇荡s」这类中英残骸，比英文原文更难读。
    规则：扫出整句里可译片段（人名/道具/动作）按位置拼中文；
    译不出就保留完整英文原句 —— 要么干净中文，要么完整英文。
"""
from __future__ import annotations

import re

# 从七要素 visual 里抽要素标签（planner prompt 约定的段名）
_SEG_PATTERNS = {
    "subject": re.compile(r"\bSUBJECT\s*\d*\s*[:：]\s*([^;.]+)", re.I),
    "action": re.compile(r"\bACTION\s*[:：]\s*([^;.]+)", re.I),
    "secondary": re.compile(
        r"\b(?:SECONDARY|SUBJECT\s*2|ACCOMPANIED BY)\s*[:：]\s*([^;.]+)", re.I),
    "background": re.compile(r"\bBACKGROUND\s*[:：]\s*([^;.]+)", re.I),
    "camera": re.compile(r"\bCAMERA\s*[:：]\s*([^;.]+)", re.I),
    "mood": re.compile(r"\bMOOD\s*[:：]\s*([^;.]+)", re.I),
}

# 展示顺序与中文标签
SEG_ORDER = (
    ("subject", "主体"),
    ("action", "动作"),
    ("secondary", "配角"),
    ("background", "背景"),
    ("camera", "景别"),
    ("mood", "情绪"),
)

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


def _tidy(s: str, limit: int = 46) -> str:
    """把英文要素压成紧凑速记。"""
    t = re.sub(r"\[[^\]]*\]", "", s or "")
    t = re.sub(r"\s+", " ", t).strip(" ,;:-.")
    t = re.sub(r"\b(\w+)\s+(and|with|on|in|of|at|to)\s+", r"\1 ", t, flags=re.I)
    t = re.sub(r"\s*,\s*(and|with|or)\s*", " ", t, flags=re.I)
    for junk in ("clearly", "visible", "detailed", "realistic",
                 "the ", "a ", "an ", "is ", "are ", "being "):
        t = re.sub(r"\b" + junk + r"\b", "", t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,;:-.")
    if len(t) > limit:
        t = t[:limit].rstrip(" ,;:-.") + "…"
    return t


def _seg(visual: str, key: str, limit: int = 46) -> str:
    """抽一个要素段并转成中文速记。译不出就保留完整英文原句。"""
    m = _SEG_PATTERNS[key].search(visual or "")
    if not m:
        return ""
    s = re.sub(r"\[GENDER:\w+\]", "", m.group(1).strip().rstrip(".;"))
    if not s:
        return ""

    hits: list[tuple[int, str]] = []
    for table in (_ENTITY_ZH, _VERB_ZH):
        for en, zh in table.items():
            for m2 in re.finditer(re.escape(en), s, flags=re.I):
                hits.append((m2.start(), zh))
    hits.sort(key=lambda x: (x[0], -len(x[1])))
    picked: list[tuple[int, str]] = []
    last_end = -1
    for pos, zh in hits:
        if pos >= last_end:
            picked.append((pos, zh))
            last_end = pos + len(zh)

    parts = [zh for _, zh in picked]
    # 长词吃掉短词（竹杖旌节 吃掉 旌节）
    parts = [z for z in parts
             if not any(z != other and z in other for other in parts)]
    if parts:
        return _tidy(" ".join(dict.fromkeys(parts)), limit)
    return _tidy(s, limit)


def page_elements(p) -> list[tuple[str, str]]:
    """单页分镜要素 → [(中文标签, 内容), ...]，空内容剔除。

    供 layout_preview.html 在图位旁展示"这页要画什么"。

    p 可以是 StoryPage dataclass，也可以是 dict（storyboard.json）。
    """
    if isinstance(p, dict):
        visual = p.get("visual") or ""
    else:
        visual = getattr(p, "visual", "") or ""
    out: list[tuple[str, str]] = []
    for key, label in SEG_ORDER:
        v = _seg(visual, key)
        if v:
            out.append((label, v))
    if not out and visual.strip():
        first = visual.strip().split(";")[0][:80]
        out.append(("画面", first))
    return out
