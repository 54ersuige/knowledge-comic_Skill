"""v0.3.15 preflight（生图前硬关卡）回归测试。

设计原则：**双向验证**。
  1. 真 job（kc_1790586703）必须 0 阻塞 —— 防误报
  2. 注入故障必须被对上的 code 抓到 —— 防漏报
只测第 1 条的关卡是废的：它永远绿，用户就再也不看了。

v0.3.15 修掉的三个误报根因（都来自苏武牧羊真数据）：
  - NO_TEXT_MISSING 10/10 误报：零文字约束由 ZERO_TEXT_BOOST 注入，与 visual 无关
  - GENDER_PARTIAL 每页误报：把 `Lake Baikal (Bei Hai)` / `Zhang Zhong` 当地名/修饰
  - BODY_SHORT 93 字被警告：100-150 是目标带，不是硬边界

跑法（任意目录）：
    python -X utf8 scripts/tests/test_preflight_v0315.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.core.planner import StoryPage, Storyboard          # noqa: E402
from scripts.core.preflight import run_preflight                 # noqa: E402

REAL_JOB = ROOT / "data" / "kc_1790586703" / "storyboard.json"
STYLE = "chinese_lianhuanhua_classic"

_passed: list[str] = []
_failed: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        _passed.append(name)
        print(f"  PASS  {name}")
    else:
        _failed.append(name)
        print(f"  FAIL  {name}  {detail}")


def codes(result) -> set[str]:
    return {f.code for f in result.findings}


def base_sb() -> dict:
    """一份最小但完全合规的 storyboard。"""
    return {
        "topic": "t", "style_id": STYLE, "title": "t",
        "characters": [{"name": "苏武", "role": "主角", "visual_signature": "x"}],
        "pages": [{
            "page": 1,
            "visual": ("Character bible: Su Wu, 45yo envoy, dark robe. [GENDER:male] "
                       "Wide shot, snow field, plain unadorned fabric, "
                       "STRICT NO TEXT, no characters, no symbols."),
            "caption": "北海", "dialogue": "律谓武曰。", "body": "正文内容。",
            "keywords": ["苏武", "北海"], "punchline": "他走的时候，节上的毛还是新的。",
        }],
    }


# --- 1. 真实 job：0 阻塞，且不能有误报 code -------------------------------

def test_real_job_clean() -> None:
    print("\n[1] 真实 job kc_1790586703 体检")
    if not REAL_JOB.exists():
        check("real job 存在", False, str(REAL_JOB))
        return
    sb = json.loads(REAL_JOB.read_text(encoding="utf-8"))
    r = run_preflight(sb)
    check("0 阻塞项", not r.blocked,
          f"blocks={[f.code for f in r.blocks]}")
    # 曾经误报的两个 code 必须彻底消失
    check("无误报 NO_TEXT_MISSING", "NO_TEXT_MISSING" not in codes(r))
    check("无误报 GENDER_PARTIAL", "GENDER_PARTIAL" not in codes(r))
    # 0 字节图静默污染的变体：pages 为空时不能崩
    empty = run_preflight({"style_id": STYLE, "pages": [], "characters": []})
    check("空 pages 不崩", empty is not None)


# --- 2. 注入故障：每条必须被对上 code 抓到 ---------------------------------

def test_injected_faults() -> None:
    print("\n[2] 注入故障必须被拦截")

    sb = base_sb(); sb["pages"][0]["keywords"] = []
    check("KW_EMPTY 抓空 keywords", "KW_EMPTY" in codes(run_preflight(sb)))

    sb = base_sb()
    sb["pages"][0]["body"] = "他被流放（实际为十九年），后来回来了。这段历史很有趣，值得一读再读，值得一读再读，值得一读再读，值得一读再读，值得一读再读，值得一读再读，值得一读再读，值得一读再读，值得一读再读，值得一读再读，值得一读再读，值得一读再读，值得一读再读，值得一读再读。"
    check("HEDGING 抓自我不确定表述", "HEDGING" in codes(run_preflight(sb)))

    sb = base_sb(); sb["pages"][0]["body"] = "字" * 200
    check("BODY_LONG 抓超长正文", "BODY_LONG" in codes(run_preflight(sb)))

    sb = base_sb(); sb["pages"][0]["punchline"] = ""
    check("PUNCH_EMPTY 抓空 punchline", "PUNCH_EMPTY" in codes(run_preflight(sb)))

    sb = base_sb(); sb["pages"][0]["dialogue"] = ""
    check("QUOTE_EMPTY 抓空引文", "QUOTE_EMPTY" in codes(run_preflight(sb)))

    sb = base_sb()
    sb["pages"][0]["visual"] = ("Su Wu in a dim tent, robe covered with intricate "
                                "calligraphy embroidery, plain background.")
    check("TEXT_INVITING 抓诱导画字词", "TEXT_INVITING" in codes(run_preflight(sb)))

    # 前缀式多角色：第二段漏标 [GENDER] → 正是 p9 常惠事故
    sb = base_sb()
    sb["pages"][0]["visual"] = (
        "[GENDER:male] Rider: Han man age 35, fur coat, on horseback in midground.\n"
        "Standing figure: Han man age 50, plain dark robe, on a distant ridge.\n"
        "Wide shot, snow road, plain fabric, no calligraphy, no symbols.")
    check("GENDER_PARTIAL 抓前缀式漏标", "GENDER_PARTIAL" in codes(run_preflight(sb)))

    # 同样的两段，两段都标了 → 必须放行（判据对称，不能只测阳性）
    sb["pages"][0]["visual"] = sb["pages"][0]["visual"].replace(
        "Standing figure:", "[GENDER:male] Standing figure:")
    check("GENDER_PARTIAL 标全则放行",
          "GENDER_PARTIAL" not in codes(run_preflight(sb)))

    sb = base_sb()
    sb["pages"][0]["body"] = "阿提拉单于率骑兵南下，苏武出使匈奴 negotiating 和谈，气氛紧张，双方僵持不下，最终各自散去，故事到此结束。"
    check("NAME_UNKNOWN 抓编造人物", "NAME_UNKNOWN" in codes(run_preflight(sb)))

    sb = base_sb(); sb["pages"][0]["body"] = "这是一场破防的极限测试，情绪价值拉满。" * 3
    check("MODERN_TONE 抓现代口水词", "MODERN_TONE" in codes(run_preflight(sb)))


# --- 3. 否定语境不能误判（p09 原文用的是否定句式）--------------------------

def test_negation_aware() -> None:
    print("\n[3] 否定语境不误判")
    sb = base_sb()
    sb["pages"][0]["visual"] = (
        "[GENDER:male] Su Wu standing in snow, plain unadorned robe, "
        "STRICT NO TEXT — no calligraphy, no characters, no symbols, "
        "without any writing on the fabric.")
    check("否定式零文字声明放行",
          "TEXT_INVITING" not in codes(run_preflight(sb)))


# --- 4. dataclass 路径与 dict 路径结果一致 ---------------------------------

def test_both_input_paths() -> None:
    print("\n[4] Storyboard 对象 / dict 两条输入路径")
    raw = base_sb()
    d_res = run_preflight(raw)

    sb = Storyboard(
        topic="t", style_id=STYLE, title="t", characters=raw["characters"],
        pages=[StoryPage(**p) for p in raw["pages"]],
    )
    o_res = run_preflight(sb)
    check("两条路径 findings 一致",
          codes(d_res) == codes(o_res),
          f"dict={codes(d_res)} obj={codes(o_res)}")


def main() -> int:
    test_real_job_clean()
    test_injected_faults()
    test_negation_aware()
    test_both_input_paths()

    print(f"\n{'=' * 52}")
    print(f"passed {len(_passed)} / {len(_passed) + len(_failed)}")
    if _failed:
        print("FAILED: " + ", ".join(_failed))
        return 1
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
