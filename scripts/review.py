"""Review storyboard against style_guide.md (LLM-as-Judge).

流程：
  1. 加载 references/style_guide.md
  2. 把 storyboard JSON + style_guide 一起发给 LLM
  3. 让 LLM 按 3 个维度（深度 30 / 一致性 30 / 作者风格 40）0-100 打分
  4. 输出 {total, dimensions: {depth, consistency, voice}, feedback: [...]}
  5. 通过：total >= 80 且所有维度 >= 60% 满分
"""
from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core.config import get_config

logger = logging.getLogger(__name__)

STYLE_GUIDE_PATH = SKILL_ROOT / "references" / "style_guide.md"
PASS_THRESHOLD = 90  # 总分 v2 - 严化（之前是 80）
DIMENSION_PASS_THRESHOLD = 0.7  # 任一维度 >= 70% 满分
FACT_CHECK_THRESHOLD = 0.7  # fact_check 维度 < 70% → 直接 FAIL


@dataclass
class ReviewResult:
    total: int
    dimensions: dict[str, int]
    feedback: list[str]
    passed: bool
    fact_check_passed: bool

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "dimensions": self.dimensions,
            "feedback": self.feedback,
            "passed": self.passed,
            "fact_check_passed": self.fact_check_passed,
        }


@dataclass
class ReviewResult:
    total: int
    dimensions: dict[str, int]
    feedback: list[str]
    passed: bool

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "dimensions": self.dimensions,
            "feedback": self.feedback,
            "passed": self.passed,
        }


REVIEW_SYSTEM_PROMPT = """你是 Knowledge Comic Skill 的内容评审（LLM-as-Judge）。

你的输入：
  1. references/style_guide.md（评分标准）
  2. 一篇 storyboard JSON（含 topic / style_id / pages / title / summary / preface / epigraph / postscript 等）

你的输出（严格 JSON）：
{
  "depth": 0-30,             // 维度 1: 表达深度（参考 §2）
  "consistency": 0-30,      // 维度 2: 一致性（参考 §3）
  "voice": 0-40,            // 维度 3: 作者风格（参考 §4）
  "fact_check": 0-20,       // 维度 5: 硬性事实核查（参考 §6 规则）
  "feedback": ["问题1", "问题2", ...],  // 3-5 条具体可执行的反馈
  "passed": true|false      // 总分 >= 90 且 fact_check >= 70%
}

评分要求：
  - 严格按 style_guide.md 的 §2/§3/§4/§6 维度逐项打分
  - fact_check 必须检查历史人物时间线、数字出处、避免元叙事（§6 硬性规则）
  - 发现硬性事实错误（如引用死于某年的人讨论该年后事件）必须 fact_check 严减分（最低 0）
  - "feedback" 必须是具体的、可执行的（如「p3 caption 没数字」「结尾没说教但缺反直觉」）
  - 不要泛泛而谈（「还可以」「不错」），必须说具体在哪条出问题
  - 不要重复文档里的话，直接给可执行的改进建议
"""


def _load_style_guide() -> str:
    if not STYLE_GUIDE_PATH.exists():
        raise RuntimeError(
            f"style_guide.md not found: {STYLE_GUIDE_PATH}. "
            f"Create one or copy from references/style_guide.md"
        )
    return STYLE_GUIDE_PATH.read_text(encoding="utf-8")


def _call_judge_llm(style_guide: str, storyboard_json: str) -> str:
    """调 LLM 评审，返回 JSON 字符串。"""
    cfg = get_config()
    from openai import OpenAI

    if not cfg.llm_api_key or cfg.llm_api_key.startswith("sk-placeholder"):
        raise RuntimeError(
            "LLM_API_KEY not configured. Fill it in Skill .env or project .env."
        )

    client = OpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)
    user_msg = (
        "请评审以下 storyboard 是否符合 style_guide.md 的标准。\n\n"
        "## style_guide.md\n" + style_guide + "\n\n"
        "## storyboard JSON\n" + storyboard_json + "\n\n"
        "请按系统提示的 JSON schema 严格输出（不要任何 markdown 包裹或解释文字）。"
    )

    try:
        resp = client.chat.completions.create(
            model=cfg.llm_model,
            messages=[
                {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
        )
    except Exception as e:
        raise RuntimeError(f"LLM review call failed: {e}") from e

    content = resp.choices[0].message.content or ""

    # 处理 thinking 模式（Agnes 3.0-flash）
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.S)
    if m:
        content = m.group(1)
    if not content.strip().startswith("{"):
        m = re.search(r"\{[\s\S]*\}\s*$", content)
        if m:
            content = m.group(0)

    return content


def _parse_review_response(content: str) -> dict[str, Any]:
    """解析 LLM 返回的 JSON，缺失字段给默认值。"""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"LLM review returned invalid JSON. Content: {content[:500]!r}"
        ) from e

    return {
        "depth": int(data.get("depth", 0)),
        "consistency": int(data.get("consistency", 0)),
        "voice": int(data.get("voice", 0)),
        "fact_check": int(data.get("fact_check", 0)),
        "feedback": list(data.get("feedback", [])),
        "passed": bool(data.get("passed", False)),
    }


def review_storyboard(storyboard: dict[str, Any]) -> ReviewResult:
    """主入口：评审 storyboard，返回 ReviewResult。

    Args:
        storyboard: Storyboard.to_dict() 的输出

    Returns:
        ReviewResult(total, dimensions, feedback, passed)
    """
    style_guide = _load_style_guide()
    sb_json = json.dumps(storyboard, ensure_ascii=False, indent=2)
    content = _call_judge_llm(style_guide, sb_json)
    parsed = _parse_review_response(content)

    total = parsed["depth"] + parsed["consistency"] + parsed["voice"]
    dimensions = {
        "depth": parsed["depth"],
        "consistency": parsed["consistency"],
        "voice": parsed["voice"],
        "fact_check": parsed["fact_check"],
    }

    # 硬性检查 v2: fact_check 必须达标
    fact_check_passed = parsed["fact_check"] >= 20 * FACT_CHECK_THRESHOLD

    # 总分 + 各维度 v2: 70% 阈值（之前 60%）
    dim_pass = (
        dimensions["depth"] >= 30 * DIMENSION_PASS_THRESHOLD
        and dimensions["consistency"] >= 30 * DIMENSION_PASS_THRESHOLD
        and dimensions["voice"] >= 40 * DIMENSION_PASS_THRESHOLD
    )

    # PASS 条件 v2: 总分 ≥ 90 + fact_check ≥ 70% + 各维度 ≥ 70%
    passed = total >= PASS_THRESHOLD and dim_pass and fact_check_passed

    return ReviewResult(
        total=total,
        dimensions=dimensions,
        feedback=parsed["feedback"],
        passed=passed,
        fact_check_passed=fact_check_passed,
    )


# ---- CLI ----
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python review.py <job_id>")
        print("Example: python review.py kc_1789723858")
        sys.exit(1)

    job_id = sys.argv[1]
    from scripts.core.config import get_config
    cfg = get_config()
    sb_path = cfg.data_dir / job_id / "storyboard.json"

    if not sb_path.exists():
        print(f"NOT FOUND: {sb_path}")
        sys.exit(1)

    sb = json.loads(sb_path.read_text(encoding="utf-8"))
    result = review_storyboard(sb)

    print()
    print("=" * 60)
    print(f"  Review · {job_id}")
    print("=" * 60)
    print(f"  Depth       {result.dimensions['depth']}/30")
    print(f"  Consistency {result.dimensions['consistency']}/30")
    print(f"  Voice       {result.dimensions['voice']}/40")
    print(f"  Fact-check  {result.dimensions['fact_check']}/20  "
          f"{'[OK]' if result.fact_check_passed else '[FAIL]'}")
    print(f"  -----------")
    print(f"  TOTAL       {result.total}/100  "
          f"{'[PASS]' if result.passed else '[FAIL]'}")
    print()
    print(f"  Feedback:")
    for fb in result.feedback:
        print(f"    - {fb}")

    sys.exit(0 if result.passed else 2)