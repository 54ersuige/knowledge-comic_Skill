# -*- coding: utf-8 -*-
"""视觉文字对齐审查 (v0.2.6)

检查 storyboard 里每页的:
- body / caption 里的关键人物名是否在 visual 里被提及
- body / caption 里的关键动作是否在 visual 里被描述
- visual ↔ caption 实体覆盖度

输出 warnings，提示哪些页需要手动复审（用 read tool 看图 vs body）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path


# === 关键人物名（中文 → 英文同义词） ===
# 历史典故 / 人物故事类的常见实体。可扩展。
NAMED_ENTITY_MAP: dict[str, list[str]] = {
    # 郭子仪相关
    "郭子仪": ["guo ziyi", "gao ziyi", "ziyi", "guo"],
    "郭令公": ["guo", "ziyi", "commander"],
    # 回纥相关
    "回纥": ["hu", "uyghur", "uyghurs", "tiele"],
    "回纥可汗": ["khan", "hu khan", "yao geluo", "yaogelu"],
    "药葛罗": ["yao geluo", "yaogelu", "yao", "geluo", "khan"],
    # 仆固怀恩
    "仆固怀恩": ["pugu", "huai'en", "huaien", "pugu huai'en"],
    # 吐蕃
    "吐蕃": ["tubo", "tibetan", "tibet"],
    # 唐
    "唐": ["tang", "tang dynasty", "han-chinese"],
    # 长安
    "长安": ["chang'an", "changan"],
    # 安史之乱
    "安禄山": ["an lushan", "lushan"],
    "史思明": ["shi siming", "siming"],
    # 其它常见人物 (可扩展)
}

# === 关键动作词（中文 → 英文模式） ===
# v0.2.6: 只保留"必须身体动作"——隐喻/抽象词（推/撕/摔）已被剔除，
# 否则 body 里"推向外部"、"撕开诚意"这种隐喻会被误判。
ACTION_VERB_MAP: dict[str, list[str]] = {
    "翻身下马": ["dismount", "on foot", "on the ground", "foot on the ground", "standing beside horse", "off horse"],
    "下马": ["dismount", "on foot", "on the ground", "off horse"],
    "上马": ["mount", "mounting horse", "climb onto"],
    "下跪": ["kneel", "kneeling", "on bended knee"],
    "跪": ["kneel", "kneeling"],
    "拜迎": ["bow", "bowing", "long bow", "deep bow", "formal bow", "长揖"],
    "长揖": ["long bow", "deep bow", "formal bow", "clasped hands"],
    "拔剑": ["draw sword", "unsheathe", "sword drawn"],
    "举剑": ["raise sword", "sword raised", "sword high"],
    "砍": ["slash", "swing sword", "cut"],
    "策马": ["ride", "riding", "gallop", "on horseback"],
    "闯入": ["burst into", "rush into", "storm into", "ride into"],
    "逃": ["flee", "retreat", "escape"],
    "撤退": ["retreat", "withdraw", "fall back", "departing", "departure"],
    "围": ["surround", "encircle", "besiege"],
    "攻城": ["besiege", "storm", "attack city wall"],
    "举旗": ["raise flag", "banner held high", "flag raised"],
    "放火": ["set fire", "burning", "torch", "ignite"],
    "点灯": ["light candle", "candle lit", "lantern lit"],
    "喝酒": ["drink wine", "wine cup", "raise cup", "杯酒"],
    "敬酒": ["offer wine", "raise cup", "toast"],
    "看一眼": ["look at", "glance at", "gaze at", "eyes on"],
    "跪拜": ["kowtow", "deep bow", "长揖"],
    "策马扬鞭": ["whip horse", "gallop", "lash horse"],
    "大笑": ["laugh", "laughing", "smile"],
    "怒视": ["glare", "scowl", "angry stare", "eyes glaring"],
    "挥手": ["wave", "waving", "beckon"],
    "勒马": ["rein in horse", "pull rein", "stop horse"],
    "举杯": ["raise cup", "raise wine cup", "toast"],
    "拔刀": ["draw blade", "unsheathe blade", "blade drawn"],
    "接旨": ["receive edict", "accept imperial order", "kneel receive"],
    "系": ["tie", "bind"],
    "拉弓": ["draw bow", "arrow drawn", "bow pulled"],
    "射箭": ["shoot arrow", "arrow shot", "loose arrow"],
}


# === v0.3.18 CONCEPT 具象化检查 ===
# 背景：v0.2.3 七要素只管镜头语言，产出全是"古风场景快照" —— 正文讲"算账"，
# 画面画"两人说话"，图文各说各话（用户实图反馈：「图片与内容符合度关联性偏弱」）。
# v0.3.18 在 planner 里强制每页 visual 首段写 CONCEPT，把概念转成可见元素。
# 本模块**验**这条铁律有没有被遵守。

# CONCEPT 右侧（→ 之后）出现这些词 = 没具象化，还在写抽象概念
_ABSTRACT_MARKERS = (
    "concept", "idea", "abstract", "metaphor", "symbol", "symbolise", "symbolize",
    "represents", "representing", "the concept of", "spirit", "feeling of",
    "strategy", "thinking", "notion", "theme",
)

# CONCEPT 段里出现这些词 = 有画面载体（可信的具象化）
_VISIBLE_MARKERS = (
    "table", "board", "map", "scroll", "coin", "token", "tally", "pebble", "stone",
    "scale", "balance", "chess", "piece", "wall", "gate", "tent", "army", "soldier",
    "fire", "smoke", "water", "river", "mountain", "bamboo", "wooden", "hand", "finger",
    "gesture", "pointing", "pushing", "spreading", "open", "closed", "row", "line",
    "sword", "bow", "arrow", "horse", "cart", "ladder", "rope", "torch", "lamp",
)


def check_concept(visual: str) -> dict:
    """v0.3.18: 检查 visual 首段有没有 CONCEPT，且有没有真的具象化。

    返回 {"has_concept": bool, "abstract": [...], "visible": bool}
    """
    m = re.search(r"CONCEPT\s*[:：](.*?)(?=\n\s*(?:SUBJECT|ACTION|CAMERA|\[GENDER)|\Z)",
                  visual, re.IGNORECASE | re.DOTALL)
    if not m:
        return {"has_concept": False, "abstract": [], "visible": False}

    seg = m.group(1)
    low = seg.lower()
    abstract = [w for w in _ABSTRACT_MARKERS if w in low]
    visible = any(w in low for w in _VISIBLE_MARKERS)
    return {"has_concept": True, "abstract": abstract, "visible": visible}


def extract_named_entities(text: str) -> set[str]:
    """从 body/caption 抽取关键人物名（中文）。"""
    entities: set[str] = set()
    for name in NAMED_ENTITY_MAP.keys():
        if name in text:
            entities.add(name)
    return entities


def extract_action_verbs(text: str) -> set[str]:
    """从 body/caption 抽取关键动作词（中文）。"""
    actions: set[str] = set()
    for action in ACTION_VERB_MAP.keys():
        if action in text:
            actions.add(action)
    return actions


def entity_in_visual(entity: str, visual: str) -> bool:
    """判断 visual 里是否提及某个中文人物名（用 NAMED_ENTITY_MAP 映射英文同义词）。"""
    visual_lower = visual.lower()
    synonyms = NAMED_ENTITY_MAP.get(entity, [])
    return any(syn.lower() in visual_lower for syn in synonyms)


def action_in_visual(action: str, visual: str) -> bool:
    """判断 visual 里是否描述某个中文动作。

    v0.2.6: 处理否定语境 — "No dismount" / "not on foot" 等应判为 FALSE。
    """
    visual_lower = visual.lower()
    synonyms = ACTION_VERB_MAP.get(action, [])
    # 1) 简单标记否定模式
    # "no dismount", "not dismount", "without dismount", "avoid dismount", "never dismount"
    for syn in synonyms:
        syn_lower = syn.lower()
        # 简单 substring 检测 (可能误报)
        if syn_lower in visual_lower:
            # 检查是否被否定修饰
            negation_patterns = [
                f"no {syn_lower}", f"not {syn_lower}",
                f"without {syn_lower}", f"avoid {syn_lower}",
                f"never {syn_lower}", f"don't {syn_lower}",
                f"do not {syn_lower}", f"no longer {syn_lower}",
            ]
            if any(neg in visual_lower for neg in negation_patterns):
                continue  # 这个 syn 被否定，跳过
            return True
    return False


def check_page(page: dict) -> dict:
    """检查单页的对齐情况。v0.2.6:
    - caption 是场景说明 = 必须 100% 在 visual 体现（动作、主角）
    - body 是上下文叙述 = 仅做参考检查，缺失不算 HIGH
    """
    pno = page.get("page", "?")
    caption = page.get("caption", "")
    body = page.get("body", "")
    visual = page.get("visual", "")

    # caption 单独抽 (严格)
    caption_entities = extract_named_entities(caption)
    caption_actions = extract_action_verbs(caption)

    # body 抽 (参考)
    body_entities = extract_named_entities(body)
    body_actions = extract_action_verbs(body)

    # visual 是否提及
    cap_ent_missing = [e for e in caption_entities if not entity_in_visual(e, visual)]
    cap_act_missing = [a for a in caption_actions if not action_in_visual(a, visual)]
    body_ent_missing = [e for e in body_entities if not entity_in_visual(e, visual)]
    body_act_missing = [a for a in body_actions if not action_in_visual(a, visual)]

    # caption 覆盖率
    cap_total = len(caption_entities) + len(caption_actions)
    cap_covered = (len(caption_entities) - len(cap_ent_missing)) + (len(caption_actions) - len(cap_act_missing))
    cap_coverage = cap_covered / cap_total if cap_total > 0 else 1.0

    # 严重度: caption 是场景说明，HIGH 仅在 caption 缺失时触发。
    # body 是上下文叙述，body 缺失只是 LOW (请 Mavis 复审)。
    #
    # v0.3.18: 加入 CONCEPT 检查 —— 「图文关联性偏弱」的直接防线。
    # visual 没写 CONCEPT = 没交代这页在画什么概念（MEDIUM，人工补）
    # CONCEPT 里全是抽象词 = 没具象化，等于没画（HIGH，图一定对不上正文）
    concept = check_concept(visual)
    concept_issue = None
    if not concept["has_concept"]:
        concept_issue = "缺 CONCEPT 段"
    elif concept["abstract"] and not concept["visible"]:
        concept_issue = f"CONCEPT 未具象化（抽象词 {concept['abstract']}，无可见载体）"

    severity = "ok"
    if concept_issue:
        severity = "high"
    elif cap_act_missing:
        severity = "high"  # caption 动作缺失 = 图肯定不对
    elif cap_ent_missing and cap_coverage < 0.7:
        severity = "medium"  # caption 主角缺失
    elif body_act_missing and len(body_act_missing) >= 2:
        severity = "medium"  # body 多动作缺失 (请复审)
    elif body_ent_missing and len(body_ent_missing) >= 2:
        severity = "low"  # body 多配角缺失 (信息缺失，不一定错)

    return {
        "page": pno,
        "caption": caption,
        "caption_missing_entities": cap_ent_missing,
        "caption_missing_actions": cap_act_missing,
        "body_missing_entities": body_ent_missing,
        "body_missing_actions": body_act_missing,
        "caption_coverage": cap_coverage,
        "concept_issue": concept_issue,
        "severity": severity,
    }


def check_storyboard(storyboard_path: Path) -> dict:
    """检查整个 storyboard。"""
    raw = json.loads(storyboard_path.read_text(encoding="utf-8"))
    pages = raw.get("pages", [])
    
    results = [check_page(p) for p in pages]
    
    # 汇总
    high_risk = [r for r in results if r["severity"] == "high"]
    medium_risk = [r for r in results if r["severity"] == "medium"]
    
    return {
        "total_pages": len(results),
        "high_risk_pages": [r["page"] for r in high_risk],
        "medium_risk_pages": [r["page"] for r in medium_risk],
        "results": results,
        "ok_count": sum(1 for r in results if r["severity"] == "ok"),
    }


def print_report(report: dict) -> None:
    """打印审查报告。"""
    print(f"\n=== 视觉文字对齐审查 ({report['total_pages']} 页) ===")
    print(f"OK: {report['ok_count']}/{report['total_pages']}")
    if report["high_risk_pages"]:
        print(f"[HIGH RISK] {report['high_risk_pages']}")
    if report["medium_risk_pages"]:
        print(f"[MEDIUM RISK] {report['medium_risk_pages']}")
    print()
    for r in report["results"]:
        if r["severity"] != "ok":
            print(f"--- 第 {r['page']} 页 [{r['severity'].upper()}] ---")
            print(f"  caption: {r['caption']}")
            if r.get("concept_issue"):
                print(f"  [CONCEPT 问题] {r['concept_issue']}")
            if r["caption_missing_actions"]:
                print(f"  [CAPTION 动作缺失] {r['caption_missing_actions']}")
            if r["caption_missing_entities"]:
                print(f"  [CAPTION 人物缺失] {r['caption_missing_entities']}")
            if r["body_missing_actions"]:
                print(f"  [BODY 动作缺失] {r['body_missing_actions']}")
            if r["body_missing_entities"]:
                print(f"  [BODY 人物缺失] {r['body_missing_entities']}")
            print(f"  caption 覆盖率: {r['caption_coverage']:.0%}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python check_alignment.py <storyboard.json>")
        sys.exit(1)
    report = check_storyboard(Path(sys.argv[1]))
    print_report(report)
    sys.exit(0 if not report["high_risk_pages"] else 2)