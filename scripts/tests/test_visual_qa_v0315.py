"""v0.3.15 visual_qa（跑图后 LLM 视觉审核）回归测试。

**不调 LLM** —— 只测纯函数层：JSON 解析、置信度归一化、阈值分级、
错误降级。真机效果由 _smoke_visualqa.py 实跑验证（kc_1790586703）。

**设计原则（与 preflight 同源）**：宁可漏报也不误报。
所以只有 confidence >= BLOCK_CONFIDENCE 才升级为 block，
其余一律 warn —— LLM 视觉判断有方差，不能让它拦住用户的流程。

真机验证记录（kc_1790586703，用户已人工验收画风的 job）：
  p01 干净无字        → LLM 未报                       ✅ 无误报
  p04 袍上画满伪汉字  → LLM 报 TEXT_ON_IMAGE 95%      ✅ 抓真阳性
                          （肉眼复核确认：用户验收时漏掉的真 bug）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.core import visual_qa as vq  # noqa: E402

_passed: list[str] = []
_failed: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        _passed.append(name)
        print(f"  PASS  {name}")
    else:
        _failed.append(name)
        print(f"  FAIL  {name}  {detail}")


def test_parser() -> None:
    print("\n[1] 回复解析（容忍 markdown / think / 尾随文字）")
    cases = {
        "纯 JSON": '{"has_text": false}',
        "markdown 包裹": '```json\n{"has_text": true}\n```',
        "think 前缀": '<think>let me look at it</think>\n{"has_text": true}',
        "尾随文字": '{"has_text": false}\n\n以上是我的分析。',
        "嵌套花括号": '{"people": [{"gender": "male"}], "has_text": false}',
        "前有解释": '根据图像分析：\n{"has_text": true}',
    }
    for name, raw in cases.items():
        try:
            d = vq._parse_reply(raw)
            ok = "has_text" in d
        except Exception as e:
            d, ok = str(e), False
        check(f"解析 {name}", ok, d)

    try:
        vq._parse_reply("完全不是 JSON的一段话")
        check("非 JSON 报错", False, "应该抛异常")
    except ValueError:
        check("非 JSON 报错", True)


def test_norm_pair() -> None:
    print("\n[2] [bool, confidence] 归一化")
    check("标准二元组", vq._norm_pair([True, 0.9]) == (True, 0.9))
    check("裸 bool 降置信", vq._norm_pair(True) == (True, 0.5))
    check("None 安全", vq._norm_pair(None) == (False, 0.0))
    check("字符串 bool", vq._norm_pair("yes") == (True, 0.5))
    check("缺 confidence", vq._norm_pair([False]) == (False, 0.0))


def test_confidence_gating() -> None:
    print("\n[3] 置信度分级（误报的最后一道闸）")
    hi = vq.VisualFinding(1, "block", "X", "m", vq.BLOCK_CONFIDENCE)
    lo = vq.VisualFinding(1, "warn", "X", "m", vq.BLOCK_CONFIDENCE - 0.2)
    check("高置信 -> block", hi.level == "block")
    check("低置信 -> warn", lo.level == "warn")
    check("BLOCK_CONFIDENCE 是 0.85", vq.BLOCK_CONFIDENCE == 0.85)
    r = vq.VisualQAResult(findings=[hi, lo])
    check("result 分流正确",
          len(r.blocks) == 1 and len(r.warns) == 1)


def test_expected_genders() -> None:
    print("\n[4] 从 visual 读预期性别")
    p1 = {"visual": "[GENDER:male] Rider: Han man, on horse."}
    p2 = {"visual": "Character bible: Su Wu, ... [GENDER:male] ..."}
    p3 = {"visual": "[GENDER:female] A: woman. [GENDER:male] B: man."}
    p4 = {"visual": "Su Wu walking, no gender mark."}
    check("单个男性", vq._expected_genders(p1) == ["male"])
    check("bible 式", vq._expected_genders(p2) == ["male"])
    check("多角色", vq._expected_genders(p3) == ["female", "male"])
    check("无标记", vq._expected_genders(p4) == [])


def test_page_no_parsing() -> None:
    print("\n[5] 页码解析")
    check("04-page.png -> 4", vq._page_no_from_name(Path("04-page.png")) == 4)
    check("10-page.png -> 10", vq._page_no_from_name(Path("10-page.png")) == 10)
    check("乱名不崩", vq._page_no_from_name(Path("cover.png")) == 0)


def test_report_shapes() -> None:
    print("\n[6] 报告可读性")
    ok = vq.VisualQAResult(checked=10)
    check("全通过报告", "通过" in ok.report())
    bad = vq.VisualQAResult(
        checked=10,
        findings=[vq.VisualFinding(4, "block", "TEXT_ON_IMAGE",
                                   "画面里出现了文字", 0.95, "袍上有汉字")])
    rep = bad.report()
    check("阻塞报告含页码", "p04" in rep)
    check("阻塞报告含依据", "袍上有汉字" in rep)
    check("阻塞报告含置信", "95%" in rep)


def test_prompt_safety() -> None:
    print("\n[7] prompt 不泄漏整段英文 visual")
    page = {"visual": "Su Wu in snow, 600 chars of English... // 苏武 雪原 枯草",
            "caption": "北海", "page": 1}
    prompt = vq._build_prompt("chinese_lianhuanhua_classic", page)
    check("喂了中文速记", "苏武" in prompt)
    check("没喂整段英文", "600 chars of English" not in prompt)
    check("要求 JSON 输出", '"has_text"' in prompt)
    check("连环画风格问题在", "lianhuanhua" in prompt)


def main() -> int:
    test_parser()
    test_norm_pair()
    test_confidence_gating()
    test_expected_genders()
    test_page_no_parsing()
    test_report_shapes()
    test_prompt_safety()

    print(f"\n{'=' * 52}")
    print(f"passed {len(_passed)} / {len(_passed) + len(_failed)}")
    if _failed:
        print("FAILED: " + ", ".join(_failed))
        return 1
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
