"""v0.3.22 架构修复专项测试。

覆盖 4 项不可降级约束（每一项都对应一次真实事故）：

[1] LIANHUANHUA_STYLE_LOCK 加室内物品 + 写实盔甲拒词
    事故依据：卧薪尝胆 p06（3D 铠甲）+ p09（现代办公环境）崩坏。
    连环画强锚对"现代物品"吸引力弱，必须硬拒。

[2] planner schema gender enum 强制
    事故依据：planner 写出"男"/"man"/"M" 等乱七八糟的 gender 值，
    preflight 校验全靠字符串相等（g in (male, female, mixed)），
    LLM 不看 prompt 注释。enum 强制两个之一。

[3] preflight CHAR_GENDER_MISSING 强制阻塞（不绕 KNOWN_GENDER）
    事故依据：v0.3.20 设计"gender 必填"，但 KNOWN_GENDER 兜底让
    库内 90 个正史人物（夫差/勾践/西施/张巡等）自动通过 ——
    planner 偷懒不填就过。v0.3.22 强制阻塞。

[4] preflight + visual_qa to_dict() 落盘 JSON
    事故依据：跑图复盘靠记忆 + console 输出，事后无法对比两次跑图
    的差异。v0.3.22 落盘 data/<job>/preflight_report.json 和
    visual_qa_report.json。

[5] 长 scene 截断保留 ZERO_TEXT_BOOST + Avoid
    事故依据：v0.2.4 fallback `assembled[:9790]` 硬切前 N 字符，
    当 LIANHUANHUA_STYLE_LOCK 加长后（v0.3.22）scene 超限 fallback
    触发，ZERO_TEXT_BOOST 和 Avoid:negative 被切掉。
    修复：fallback 只砍 scene，永保末段 boost。

跑法（任意目录）：
    python -X utf8 scripts/tests/test_v0322.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.core.prompts import (                                    # noqa: E402
    LIANHUANHUA_STYLE_LOCK, ZERO_TEXT_BOOST, build_image_prompt,
)
from scripts.core.planner import PLANNER_SYSTEM_PROMPT                # noqa: E402
from scripts.core.preflight import PreflightResult, run_preflight     # noqa: E402
from scripts.core.visual_qa import VisualQAResult, VisualFinding      # noqa: E402

STYLE = "chinese_lianhuanhua_classic"

_passed: list[str] = []
_failed: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        _passed.append(label)
        print(f"  PASS  {label}")
    else:
        _failed.append(label)
        print(f"  FAIL  {label}  {detail}")


# --- [1] LIANHUANHUA_STYLE_LOCK 加室内物品 + 写实盔甲拒词 ---------------------

def test_style_lock_rejects_modern_interior() -> None:
    """p06/p09 崩坏根因：现代室内物品 + 写实盔甲。"""
    print("\n[1] LIANHUANHUA_STYLE_LOCK 硬拒词")
    # 现代室内物品（p09 崩坏）
    for w in ("bookshelf", "floor-to-ceiling window", "office chair",
              "sofa", "glass window pane"):
        check(f"拒 {w}", w in LIANHUANHUA_STYLE_LOCK)
    # 写实盔甲（p06 崩坏）
    for w in ("chrome", "metallic shine", "polished leather",
              "specular highlight"):
        check(f"拒 {w}", w in LIANHUANHUA_STYLE_LOCK)
    # 兜底：原来的"NOT a photograph"仍保留（regression）
    check("保留 NOT a photograph", "NOT a photograph" in LIANHUANHUA_STYLE_LOCK)
    check("保留 NOT a 3D render", "NOT a 3D render" in LIANHUANHUA_STYLE_LOCK)


# --- [2] planner schema gender enum ------------------------------------------

def test_planner_schema_gender_enum() -> None:
    """planner prompt 里的 JSON schema 必须用 enum 而不是字符串。"""
    print("\n[2] planner schema gender enum")
    # 直接字符串搜：JSON schema 段必须出现 `enum: ["male", "female"]`
    check(
        "JSON schema 含 enum: male/female",
        '"enum": ["male", "female"]' in PLANNER_SYSTEM_PROMPT
        or "'enum': ['male', 'female']" in PLANNER_SYSTEM_PROMPT
        or "enum: [\"male\", \"female\"]" in PLANNER_SYSTEM_PROMPT,
    )
    # 铁律 7.4 必须显式提到 enum
    check("铁律 7.4 提到 enum 强化",
          "enum" in PLANNER_SYSTEM_PROMPT and "v0.3.22" in PLANNER_SYSTEM_PROMPT)


# --- [3] preflight CHAR_GENDER_MISSING 强制阻塞 ------------------------------

def _mk_sb() -> dict:
    return {
        "topic": "测试", "style_id": STYLE,
        "characters": [], "pages": [
            {"page": 1, "caption": "x", "dialogue": "x", "body": "x" * 200,
             "keywords": [], "punchline": "x", "visual": "x" * 200},
        ],
    }


def test_char_gender_blocks_known_char() -> None:
    """v0.3.22 行为变更：库内人物（夫差/勾践等）缺 gender 也必须阻塞。"""
    print("\n[3] preflight CHAR_GENDER_MISSING 强制阻塞")
    sb = _mk_sb()
    # 库内人物
    sb["characters"] = [{"name": "夫差", "role": "反派", "visual_signature": "素袍"}]
    pre = run_preflight(sb)
    codes = [f.code for f in pre.findings]
    check("库内人物缺 gender 阻塞", "CHAR_GENDER_MISSING" in codes)

    # 库外人物
    sb["characters"] = [{"name": "路人甲", "role": "配角", "visual_signature": "素袍"}]
    pre = run_preflight(sb)
    codes = [f.code for f in pre.findings]
    check("库外人物缺 gender 阻塞", "CHAR_GENDER_MISSING" in codes)

    # 显式填了
    sb["characters"] = [{"name": "夫差", "role": "反派", "gender": "male",
                         "visual_signature": "素袍"}]
    pre = run_preflight(sb)
    codes = [f.code for f in pre.findings]
    check("显式 gender 不阻塞", "CHAR_GENDER_MISSING" not in codes)


# --- [4] preflight + visual_qa to_dict() 落盘 JSON ---------------------------

def test_preflight_to_dict() -> None:
    print("\n[4a] preflight.to_dict()")
    sb = _mk_sb()
    sb["characters"] = [{"name": "夫差", "role": "反派", "visual_signature": "素袍"}]
    pre = run_preflight(sb)
    d = pre.to_dict()
    check("kind=preflight", d["kind"] == "preflight")
    check("blocked=True（库内人物缺 gender）", d["blocked"] is True)
    check("findings 是 list", isinstance(d["findings"], list))
    check("至少 1 条 finding", len(d["findings"]) > 0)
    f0 = d["findings"][0]
    for k in ("page", "level", "code", "msg", "hint"):
        check(f"finding 含字段 {k}", k in f0)
    check("ts 是数字", isinstance(d["ts"], (int, float)))


def test_visual_qa_to_dict() -> None:
    print("\n[4b] visual_qa.to_dict()")
    # 不调 LLM,只验空结构
    res = VisualQAResult()
    res.checked = 5
    res.findings.append(VisualFinding(
        page=3, level="block", code="TEXT_ON_IMAGE",
        msg="图上有字", confidence=0.9, evidence="墙上的伪汉字"))
    d = res.to_dict()
    check("kind=visual_qa", d["kind"] == "visual_qa")
    check("checked=5", d["checked"] == 5)
    check("ok=False", d["ok"] is False)
    check("findings 含 confidence", d["findings"][0]["confidence"] == 0.9)
    check("findings 含 evidence", d["findings"][0]["evidence"] == "墙上的伪汉字")
    # JSON 序列化能 round-trip
    s = json.dumps(d, ensure_ascii=False)
    d2 = json.loads(s)
    check("JSON round-trip", d2["kind"] == "visual_qa")


# --- [5] 长 scene 截断保留 ZERO_TEXT_BOOST + Avoid ---------------------------

def test_truncation_keeps_zero_text_and_avoid() -> None:
    """v0.3.22 强化：长 scene fallback 永远保 ZERO_TEXT_BOOST 和 Avoid。"""
    print("\n[5] 长 scene 截断保留 boost")
    # 拼一个 > 10000 字符的 scene
    base = "A man in a dark robe kneels in a vast snowfield."
    long_scene = base + (" Broken staff, dead grass, grey sky." * 400)
    check("scene 长度 > 10000", len(long_scene) > 10000)

    p = build_image_prompt(STYLE, long_scene)
    check("输出 < 9800（ag nes 上限）", len(p) <= 9800, f"len={len(p)}")
    check("保 ZERO_TEXT_BOOST (NO TEXT)", "NO TEXT" in p)
    check("保 Avoid: 负向词", "Avoid:" in p)
    check("保 LIANHUANHUA 强锚 (lianhuanhua)",
          "lianhuanhua" in p.lower())
    check("保 PATTERN_SUPPRESS (COMPLETELY BLANK)", "COMPLETELY BLANK" in p)
    # v0.3.22 新硬拒词也必须保留
    check("保室内物品硬拒词 (bookshelf)", "bookshelf" in p)
    check("保写实盔甲硬拒词 (chrome)", "chrome" in p)


# --- 入口 --------------------------------------------------------------------

def main() -> int:
    test_style_lock_rejects_modern_interior()
    test_planner_schema_gender_enum()
    test_char_gender_blocks_known_char()
    test_preflight_to_dict()
    test_visual_qa_to_dict()
    test_truncation_keeps_zero_text_and_avoid()

    print(f"\n{'=' * 52}")
    print(f"passed {len(_passed)} / {len(_passed) + len(_failed)}")
    if _failed:
        print("FAILED: " + ", ".join(_failed))
        return 1
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())