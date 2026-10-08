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
    "subject": re.compile(r"\bSUBJECT\s*\d*\s*[:：]\s*(.+)", re.I),
    "action": re.compile(r"\bACTION\s*[:：]\s*(.+)", re.I),
    "secondary": re.compile(
        r"\b(?:SECONDARY|SUBJECT\s*2|ACCOMPANIED BY)\s*[:：]\s*(.+)", re.I),
    "background": re.compile(r"\bBACKGROUND\s*[:：]\s*(.+)", re.I),
    "camera": re.compile(r"\bCAMERA\s*[:：]\s*(.+)", re.I),
    "mood": re.compile(r"\bMOOD\s*[:：]\s*(.+)", re.I),
}

# v0.3.7：planner 被要求在每段末尾写 `// 中文速记`。
# 这是**用户可读性**的正解 —— 让 LLM 自己写中文，比我们事后猜词表翻译准得多，
# 也解决"内容显示不全"（速记短，不会被截断）。
# 只吃「// + 中文」这一段，遇到下一个英文标签/标点就停，
# 否则 "旌节. SECONDARY: 50 Han riders" 会被整段吞进速记。
_ZH_NOTE = re.compile(r"//\s*([一-鿿][^;.\n]*)")

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

# v0.3.7：镜头 / 配色 / 场景是**固定术语**（七要素铁律里就规定了取值范围），
# 用词典整词覆盖比猜句意准得多。补上这层后 CAMERA / MOOD 也不再是英文。
_TERM_ZH = {
    # 景别
    "extreme wide shot": "大远景", "wide shot": "远景", "medium shot": "中景",
    "three-quarter shot": "四分之三中景", "close-up shot": "近景",
    "close up": "近景", "insert extreme close": "极特写", "insert shot": "特写",
    # 角度
    "eye level": "平视", "low angle": "仰拍", "high angle": "俯拍",
    "birds eye": "鸟瞰", "worms eye": "虫视", "dutch tilt": "斜角",
    # 景深
    "deep focus": "全景深", "shallow depth of field": "浅景深",
    "shallow dof": "浅景深", "rack focus": "变焦对焦",
    # 氛围 / 配色
    "somber": "肃穆", "solemn": "庄严", "grim": "冷峻", "tense": "紧张",
    "desaturated": "低饱和", "muted": " muted", "vivid": "鲜明",
    "warm wash": "暖调", "cold blue": "冷蓝", "sepia": "旧褐",
    # 场景
    "snowy": "雪", "snow": "雪", "frozen": "冰封", "jagged": "嶙峋",
    "mountain": "山", "mountains": "群山", "valley": "谷", "horizon": "地平线",
    "steppe": "草原", "desert": "荒漠", "camp": "营地", "palace": "宫殿",
    "court": "朝堂", "gates": "城门外", "wall": "城墙", "bamboo": "竹",
    "reed": "芦苇", "reeds": "芦苇荡", "pine": "松", "rocks": "岩石",
    # 常见道具 / 场所（v0.3.7 补：实测 leftover 长句集中在这几类）
    "candle": "烛光", "tallow candle": "烛台", "chains": "铁链",
    "iron chains": "铁链", "wooden bars": "木栅", "cell": "地窖",
    "yurt": "毡帐", "tent": "帐篷", "silhouettes": "剪影", "silhouette": "剪影",
    "blood": "血迹", "stained": "沾染", "surrounding": "围住",
    "chestnut": "栗色", "ox-tail": "牦牛尾", "horses": "马", "horse": "马",
    "camels": "骆驼", "camel": "骆驼", "riders": "骑兵", "supplies": "辎重",
    "willow": "柳", "tomb": "坟墓", "bones": "白骨", "skeleton": "骸骨",
    "tundra": "苔原", "wasteland": "荒原", "wilderness": "荒野",
    "dungeon": "地牢", "prison": "牢房", "snowfield": "雪原",
    "ridge": "山脊", "gale": "狂风", "blizzard": "暴风雪",
    "flames": "火焰", "firelight": "火光", "moonlight": "月光",
    "darkness": "幽暗", "gloom": "阴翳", "crowd": "人群",
    # 形容词 / 材质 / 器物（v0.3.7 第二轮补：残留英文集中在这些词）
    "coarse": "粗粝", "texture": "肌理", "texture of": "", "ground": "地面",
    "blurred": "虚化", "white": "白", "bare earth": "裸土", "patches": "斑块",
    "grave mounds": "坟冢", "mounds": "土丘", "interior": "内部",
    "dimly lit": "幽暗", "burning": "燃烧", "burning low": "低燃",
    "steaming": "热气腾腾", "hot liquid": "热饮", "tea": "茶", "wine": "酒",
    "cup": "杯", "winding": "蜿蜒", "road": "路", "stretching": "延伸",
    "distance": "远方", "winter": "冬", "pale": "苍白", "ochre": "赭黄",
    "indigo": "靛青", "crimson": "朱红", "vermilion": "朱砂",
    "travel-worn": "风尘仆仆", "tattered": "褴褛", "weathered": "风霜",
    "stoic": "坚忍", "hollow": "凹陷", "gaunt": "消瘦", "emaciated": "枯瘦",
    "silhouetted": "剪影", "backlit": "逆光", "rim light": "轮廓光",
}
_TERM_ZH["muted"] = "灰调"


# 任何要素标签（用于把 visual 切成段）。
#
# v0.3.7 关键教训：LLM 实际有**两种**写法，必须都认：
#   A) 大写七要素：SUBJECT: / ACTION: / CAMERA: / MOOD: / BACKGROUND:
#   B) 首字大写自然段：Foreground: / Midground: / Background: / Lighting: / Mood:
# 实测同一批 10 页里，LLM 全部用 B 写法且不含 SUBJECT/ACTION，
# 只认 A 会导致「主体/动作」两栏空、「背景」栏显示英文 —— 用户看不懂。
# 所以这里同时收录两种，并把 B 写法映射到统一 key。
_ANY_LABEL = re.compile(
    r"\b(SUBJECT\s*\d*|ACTION|SECONDARY|SECONDRY|SECODARY|"
    r"ACCOMPANIED\s+BY|FOREGROUND|MIDGROUND|BACKGROUND|"
    r"CAMERA|SHOT|ANGLE|MOOD|PLACEMENT|COMPOSITION|"
    r"DEPTH\s+LAYERS|LIGHTING|EXPRESSION|CHARACTER\s+BIBLE)\s*[:：]",
    re.I,
)


def _split_segments(visual: str) -> list[tuple[str, str]]:
    """把 visual 切成 [(规范化 key, 该段内容), ...]。

    v0.3.7：这是抽取正确性的地基。visual 是 LLM 自由写的长文本，
    标签可能重复出现，分隔符也不统一（有 . / ; / 换行）。
    所以只能**按标签出现位置**切，不能按分隔符切，也不能 search 取第一个。

    两种写法的归一化（实测 LLM 会任选其一，必须都认）：
      A) 大写七要素  SUBJECT: / ACTION: / CAMERA: / MOOD: / BACKGROUND:
      B) 自然段写法  Character bible: … / [无标签镜头句] / Foreground:
                      Midground: / Background: / Lighting: / Mood:
    B 写法的对应关系：
      开头无标签的镜头句（含 shot / lens / angle）→ camera
      Character bible / Expression               → subject
      Midground（动作发生层）                     → action
      Foreground                                → secondary
      Background                                → background
      Lighting / Mood                           → mood
    """
    v = visual or ""
    marks = list(_ANY_LABEL.finditer(v))
    if not marks:
        return []

    out: list[tuple[str, str]] = []

    def _push(key: str, content: str) -> None:
        c = content.strip()
        if not c:
            return
        # 开头无标签的镜头句 → camera
        if not any(k for k, _ in out) and _looks_like_camera(c):
            out.append(("camera", c))
        else:
            out.append((key, c))

    # 首个标签之前的内容：可能是镜头句，也可能是角色描述
    _push("subject", v[:marks[0].start()])

    for i, m in enumerate(marks):
        key = _norm_key(m.group(1))
        end = marks[i + 1].start() if i + 1 < len(marks) else len(v)
        _push(key, v[m.end():end])

    return out


_CAMERA_HINT = re.compile(
    r"\b(shot|lens|mm\b|angle|close-?up|wide|medium|framing|"
    r"dof|focus|establishing|low angle|high angle|bird's eye|eye level)\b",
    re.I,
)


def _looks_like_camera(text: str) -> bool:
    return bool(_CAMERA_HINT.search(text or ""))


def _norm_key(label: str) -> str:
    k = re.sub(r"[\s_]*\d*", "", label).upper()
    return {
        "ACCOMPANIED BY": "SECONDARY",
        "MIDGROUND": "ACTION",
        "FOREGROUND": "SECONDARY",
        "SHOT": "CAMERA",
        "ANGLE": "CAMERA",
        "COMPOSITION": "CAMERA",
        "PLACEMENT": "CAMERA",
        "DEPTHLAYERS": "SECONDARY",
        "LIGHTING": "MOOD",
        "EXPRESSION": "SUBJECT",
        "CHARACTERBIBLE": "SUBJECT",
    }.get(k, k).lower()


def _tidy(s: str, limit: int = 60) -> str:
    """把英文要素压成紧凑速记。

    v0.3.7：**默认不截断**。上一版固定 46 字上限，导致
    "vast snowy horizon, distant city walls flying…" 这类被砍成「…」，
    用户看到的是残缺信息 —— 而审阅分镜的前提是信息完整。
    现在只在真的超长时截断，且抬高上限到 60。
    """
    t = re.sub(r"\[[^\]]*\]", "", s or "")
    t = re.sub(r"\s+", " ", t).strip(" ,;:-.")
    t = re.sub(r"\b(\w+)\s+(and|with|on|in|of|at|to)\s+", r"\1 ", t, flags=re.I)
    t = re.sub(r"\s*,\s*(and|with|or)\s*", " ", t, flags=re.I)
    for junk in ("clearly", "visible", "detailed", "realistic",
                 "the ", "a ", "an ", "is ", "are ", "being "):
        t = re.sub(r"\b" + junk + r"\b", "", t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,;:-.")
    t = t.rstrip(".。;；,，")   # 速记不带句尾标点
    if len(t) > limit:
        # 在最后一个分隔符处收刀，尽量不砍掉信息单元
        cut = max(t.rfind(" ", 0, limit), t.rfind("·", 0, limit))
        if cut > limit * 0.6:
            return t[:cut]
        return t[:limit]
    return t


def _seg(visual: str, key: str, limit: int = 60) -> str:
    """按 key 取要素段并转成中文速记（供单点查询用）。

    v0.3.7：LLM 常把镜头句和角色描述混在同一段
    （"…Expression: grim_resolve. Wide establishing shot, low angle…"），
    所以 key=camera 时若没有独立的 CAMERA 段，就到 subject 段里
    按镜头线索再找一遍，否则「景别」一栏会是空的。
    """
    segs = _split_segments(visual or "")
    cands = [c for k, c in segs if k == key]
    if not cands:
        if key == "camera":
            for c in [c for k, c in segs if k == "subject"]:
                if _looks_like_camera(c):
                    cands = [c]
                    break
        if not cands:
            return ""
    return _from_segment(cands[-1], limit)


def _seg_from_text(s: str, limit: int = 60) -> str:
    """英文要素文本 → 中文速记（词表翻译路径）。

    策略：能译出 ≥2 个片段就用中文；只译出 1 个且原文很短也用；
    否则保留完整英文（诚实，不误导用户）。
    """
    s = (s or "").strip()
    if not s:
        return ""

    hits: list[tuple[int, str]] = []
    for table in (_ENTITY_ZH, _VERB_ZH, _TERM_ZH):
        for en, zh in table.items():
            for m2 in re.finditer(re.escape(en), s, flags=re.I):
                hits.append((m2.start(), zh))
    # 长词优先（extreme wide shot 要压过 wide shot）
    hits.sort(key=lambda x: (x[0], -len(x[1])))
    picked: list[tuple[int, str]] = []
    last_end = -1
    for pos, zh in hits:
        if pos >= last_end:
            picked.append((pos, zh))
            last_end = pos + len(zh)
    parts = [zh for _, zh in picked]
    parts = [z for z in parts
             if not any(z != other and z in other for other in parts)]

    if not parts:
        return _final(s)

    zh_out = " ".join(dict.fromkeys(parts))
    # 残留英文词数：用来判断"半吊子中文"还是"读得懂的中文"
    residual = len(re.findall(r"[a-zA-Z]{3,}", s))
    if len(parts) >= 2 or residual <= 2:
        return _final(zh_out)
    # 只译出一小半 → 与其给半吊子中文，不如给完整英文（诚实优先）
    return _final(s)


def _final(s: str, limit: int = 60) -> str:
    """收尾清理：去尾标点、去零散尾词、保证不出现「…」残缺。"""
    t = _tidy(s, limit).rstrip(".。;；,，")
    # 结尾若是单个残留英文虚词（a / the / with），切掉
    t = re.sub(r"\s+(?:a|an|the|with|and|of|in|on|at|to|for)$", "", t, flags=re.I)
    return t.strip(" ,;:-.")


def page_elements(p) -> list[tuple[str, str]]:
    """单页分镜要素 → [(中文标签, 内容), ...]，空内容剔除。

    供 layout_preview.html 在图位旁展示"这页要画什么"。

    p 可以是 StoryPage dataclass，也可以是 dict（storyboard.json）。
    """
    if isinstance(p, dict):
        visual = p.get("visual") or ""
    else:
        visual = getattr(p, "visual", "") or ""

    segs = _split_segments(visual)
    by_key: dict[str, list[str]] = {}
    for k, c in segs:
        by_key.setdefault(k, []).append(c)

    out: list[tuple[str, str]] = []
    for key, label in SEG_ORDER:
        cands = by_key.get(key) or []
        if not cands and key == "camera":
            # 镜头句常混在角色描述段里
            for c in by_key.get("subject", []):
                if _looks_like_camera(c):
                    cands = [c]
                    break
        if not cands:
            continue
        s = _from_segment(cands[-1])
        if s:
            out.append((label, s))

    # 整页末尾的 // 速记（LLM 有时只写一条全页摘要）—— 用来补空缺，
    # 但不能替代已有要素，否则会张冠李戴。
    if len(out) < 3:
        page_note = _page_note(visual)
        if page_note:
            out.append(("画面", page_note))

    if not out and visual.strip():
        out.append(("画面", visual.strip()[:80]))
    return out


def _page_note(visual: str) -> str:
    """取整页末尾的 // 中文速记（若它不在任何要素段内）。"""
    segs = _split_segments(visual)
    tail = visual
    for _, c in segs:
        tail = tail.replace(c, "", 1)
    m = _ZH_NOTE.search(tail)
    if not m:
        return ""
    note = m.group(1).strip().strip("·、,， ")
    # 已被要素段消费的不重复用
    if any(note in c for _, c in segs):
        return ""
    return note


def _from_segment(segment: str, limit: int = 60) -> str:
    """段内容 → 中文速记。"""
    segment = segment or ""
    zn = _ZH_NOTE.search(segment)
    if zn:
        note = zn.group(1).strip().strip("·、,， ")
        if note:
            return note[:limit]
    return _seg_from_text(segment, limit)
