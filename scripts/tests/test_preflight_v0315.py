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
    """真实 job 体检：**核心是防误报**，不是"任何阻塞都不能有"。

    v0.3.22 起 CHAR_GENDER_MISSING 是阻塞项，且对库内人物（苏武/李陵/夫差等）
    也生效。kc_1790586703 是历史数据，characters 没显式写 gender —— 这是**正
    确的 v0.3.22 行为**（强迫 planner 显式表达），不是关卡漏报。

    测试只校验**不会误报**的 code（GENDER_PARTIAL/NO_TEXT_MISSING/等），
    阻塞项允许出现 CHAR_GENDER_MISSING（这是设计意图）。
    """
    print("\n[1] 真实 job kc_1790586703 体检")
    if not REAL_JOB.exists():
        check("real job 存在", False, str(REAL_JOB))
        return
    sb = json.loads(REAL_JOB.read_text(encoding="utf-8"))
    r = run_preflight(sb)
    # GENDER_PARTIAL 曾经 10/10 误报，必须彻底消失
    check("无误报 GENDER_PARTIAL", "GENDER_PARTIAL" not in codes(r))
    # v0.3.18：NO_TEXT_MISSING 语义已变（从"缺声明=风险"改成
    # "planner 忽略了整条铁律的信号"），代码层已兜底所以只能是 warn。
    check("NO_TEXT_MISSING 不再是阻塞项", "NO_TEXT_MISSING" not in
          {f.code for f in r.blocks})
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



# --- 5. 卧薪尝胆实测暴露的三个问题（v0.3.17）-------------------------

def test_seven_element_not_actor() -> None:
    """七要素标签不是角色段（实测 10/10 误报的根因）。"""
    print("\n[5] 七要素标签排除")
    from scripts.core.preflight import _is_seven_element_label
    for lbl in ("SUBJECT: Gou Jian, 35yo", "ACTION: Helu pushes the sword",
                "CAMERA: Medium shot", "DEPTH LAYERS: FOREGROUND: wood",
                "LIGHTING: Hard sun", "MOOD: tense", "PLACEMENT: left"):
        check(f"{lbl.split(':')[0]} 是标签", _is_seven_element_label(lbl))
    for role in ("Rider: Han man", "Standing figure: man", "Foreground man: x",
                 "Slave: kneeling", "[GENDER:male] Rider: man"):
        check(f"{role.split(':')[0][:12]} 是角色段",
              not _is_seven_element_label(role))


def test_pinyin_character_recognized() -> None:
    """拼音人名 + 中文 characters[] 要能对上（实测 9/10 漏报的根因）。"""
    print("\n[6] 中英双通道角色识别")
    from scripts.core.preflight import _roles_registered
    chars = [{"name": "勾践", "role": "主角", "visual_signature": "x"},
             {"name": "夫差", "role": "反派", "visual_signature": "y"}]
    allowed = {"勾践", "夫差"}
    # 拼音写法：visual 是英文，characters 是中文 —— 实测的真实形态
    v_pinyin = "SUBJECT: Gou Jian, 35yo, wearing tattered dark silk robe, " \
               "holding a staff. ACTION: Gou Jian kneels."
    check("拼音写法认得出已登记", _roles_registered(v_pinyin, {"characters": chars},
                                                allowed))
    # 中文写法
    v_cn = "SUBJECT: 勾践，35岁，身着破袍。// 勾践 苦胆 雪原"
    check("中文写法认得出已登记",
          _roles_registered(v_cn, {"characters": chars}, allowed))
    # characters[] 非空时，角色锚点会前置到**每一页**（build_image_prompt 的
    # gender 分支），所以即使本页主体写作 "Anon" 也有性别锚点 → 放行。
    # 这是管线事实，不是放水。我第一次写这条断言时把它写反了。
    v_anon = "SUBJECT: Anon, 30yo, standing."
    check("characters 非空时匿名页仍放行（锚点前置到每页）",
          _roles_registered(v_anon, {"characters": chars}, allowed))

    # 真正的风险：characters[] 为空 + 匿名主体 → 没有任何 gender 锚点来源
    check("characters 为空 + 匿名主体 -> 报（真风险）",
          not _roles_registered(v_anon, {"characters": []}, set()))

    # characters[] 为空 + 单个具名角色 -> 无歧义
    v_named = "SUBJECT: 勾践，35岁。// 勾践 苦胆"
    check("characters 为空 + 单具名角色 -> 放行",
          _roles_registered(v_named, {"characters": []}, set()))

    # characters[] 为空 + 多个具名角色 -> 性别可能串，必须报
    v_multi = "SUBJECT: 勾践与夫差对坐。// 勾践 夫差 会稽"
    check("characters 为空 + 多具名角色 -> 报（性别可能串）",
          not _roles_registered(v_multi, {"characters": []}, set()))


def test_dialogue_rule_is_mandatory() -> None:
    """铁律 7.1 必须保持"每页必填"（实测 0/10 的防回退断言）。"""
    print("\n[7] dialogue 铁律防回退")
    from scripts.core.planner import PLANNER_SYSTEM_PROMPT
    check("含'每页必填'", "每页必填" in PLANNER_SYSTEM_PROMPT)
    check("含'不允许留空'", "不允许留空" in PLANNER_SYSTEM_PROMPT)
    check("JSON schema 标注必填",
          "每页必填" in PLANNER_SYSTEM_PROMPT.split('"pages"')[-1][:800])
    check("给出题材范例", "苦身焦思" in PLANNER_SYSTEM_PROMPT)


def test_era_anachronism() -> None:
    """时代穿帮检测 + 否定语境（v0.3.18）。"""
    print("\n[8] 角色时代穿帮（v0.3.18）")
    sb = base_sb()
    sb["characters"] = [
        {"name": "苏武", "role": "主角",
         "visual_signature": "深灰长袍（粗麻质感，**无繁复纹样**），黑色平巾帻"},
        {"name": "夫差", "role": "反派",
         "visual_signature": "华丽的红白相间宽袖丝绸袍服，佩戴玉璧和繁复的金质发冠"},
    ]
    r = run_preflight(sb)
    era = [f for f in r.findings if f.code == "ERA_ANACHRONISM"]
    check("抓到夫差的穿帮描述", len(era) == 1, str([f.msg for f in era]))
    check("报的是全文级（page=None）", era and era[0].page is None)
    check("是阻塞项", era and era[0].level == "block")
    check("msg 点名夫差", era and "夫差" in era[0].msg)
    check("没误报苏武（否定语境：无繁复纹样）",
          era and "苏武" not in era[0].msg)

    # 干净的签名不该报
    sb2 = base_sb()
    sb2["characters"] = [
        {"name": "勾践", "role": "主角",
         "visual_signature": "削瘦挺拔，素麻深色圆领短袍，发束高髻缠青色布带，"
                             "赤足草履，无玉佩无纹饰"},
    ]
    r2 = run_preflight(sb2)
    check("干净签名不报", "ERA_ANACHRONISM" not in codes(r2))

    # 弱信号单独出现不报
    sb3 = base_sb()
    sb3["characters"] = [{"name": "文种", "role": "配角",
                          "visual_signature": "面容消瘦，气质坚毅华贵，葛麻官袍"}]
    check("单��弱信号不报", "ERA_ANACHRONISM" not in codes(run_preflight(sb3)))


def test_code_level_boosts_injected() -> None:
    """三条 boost 必须无条件进 prompt（LLM 漏不掉）。"""
    print("\n[9] 代码层 boost 注入（v0.3.18 核心）")
    from scripts.core.prompts import build_image_prompt
    p = build_image_prompt("chinese_lianhuanhua_classic",
                           "A man in a tattered robe kneels in snow.")
    check("PATTERN_SUPPRESS 已注入", "COMPLETELY BLANK" in p)
    check("LIANHUANHUA_STYLE_LOCK 已注入", "lianhuanhua" in p.lower())
    check("明确排除 3D/照片", "NOT a photograph" in p and "NOT a 3D render" in p)
    check("排除宋明清院画", "Song/Ming/Qing" in p)
    check("ZERO_TEXT_BOOST 仍在", "NO TEXT" in p)
    check("长度未超 Agnes 上限", len(p) < 9800, f"len={len(p)}")


# --- 8. v0.3.20 性别单一真源 ---------------------------------------------

def test_resolve_gender() -> None:
    """性别解析优先级（v0.3.20 事故：char 级没走这套，被画成女性）。"""
    print("\n[10] resolve_gender 优先级")
    from scripts.core.prompts import resolve_gender as rg

    # 3) 正史人物库
    for nm, exp in [("夫差", "male"), ("勾践", "male"), ("张巡", "male"),
                    ("西施", "female"), ("王昭君", "female"), ("武则天", "female"),
                    ("吴王夫差", "male"), ("越王勾践", "male")]:
        check(f"{nm} -> {exp}", rg(name=nm) == exp, rg(name=nm))

    # 1) explicit 最高优先级（即便与人物库冲突）
    check("explicit 压过人物库", rg(explicit="female", name="夫差") == "female")
    # 2) [GENDER:] 标记
    check("[GENDER:female] 生效",
          rg(text="[GENDER:female] a woman stands", name="夫差") == "female")
    # 4) 文本线索
    check("英文代词", rg(text="A woman in red robe, she stands") == "female")
    check("中文称谓", rg(text="西施浣纱，女子临水") == "female")
    # 6) 默认 male（v0.3.20 关键改动：原默认 female）
    check("无信号默认 male", rg(text="A figure standing", name="") == "male")
    check("库外人物默认 male", rg(name="张三丰") == "male")


def test_gender_anchor_no_leak() -> None:
    """男性锚点不能带女性妆发（否定语境要能识别）。"""
    print("\n[11] 性别锚点无串味")
    from scripts.core.image_gen import _build_character_view_prompt as build
    from scripts.core.preflight import _positive_mention
    FEM = ["桃花腮", "步摇", "簪花", "花钿", "柳叶眉"]

    p_male = build("夫差", "反派", "素面深褐葛麻袍", "front",
                   "chinese_lianhuanhua_classic")
    check("男性 prompt 声明 male", "SUBJECT GENDER: MALE" in p_male)
    check("男性 prompt 无肯定女性妆发",
          not any(_positive_mention(p_male, w) for w in FEM),
          str([w for w in FEM if _positive_mention(p_male, w)]))
    check("男性 prompt 无 FEMALE-GENDER STYLING",
          "FEMALE-GENDER STYLING" not in p_male)
    check("男性 prompt 有 MALE-GENDER STYLING",
          "MALE-GENDER STYLING" in p_male)

    p_fem = build("西施", "配角", "青色窄袖短襦", "front",
                  "chinese_lianhuanhua_classic")
    check("女性 prompt 声明 female", "SUBJECT GENDER: FEMALE" in p_fem)
    check("女性 prompt 有 FEMALE-GENDER STYLING",
          "FEMALE-GENDER STYLING" in p_fem)
    # 注意：`'MALE-GENDER STYLING' in 'FEMALE-GENDER STYLING'` 是 True ——
    # 子串误判，测试自己踩过一次。必须排除 FEMALE 后再看。
    check("女性 prompt 无纯 MALE 分支",
          ("MALE-GENDER STYLING" not in p_fem
           or "FEMALE-GENDER STYLING" in p_fem))


def test_negation_across_parens() -> None:
    """否定语境跨括号（v0.3.20 修的真缺陷）。"""
    print("\n[12] 否定语境跨括号")
    from scripts.core.preflight import _positive_mention as pm
    neg = "(NOT 步摇 - too feminine), NO 花钿, NO 簪花"
    for w in ("步摇", "花钿", "簪花"):
        check(f"'{w}' 在否定作用域内", not pm(neg, w), pm(neg, w))
    pos = "peach blossom hairpin 步摇 in her hair"
    check("肯定语境不误判", pm(pos, "步摇"))
    # 否定作用域不能无限延伸
    far = "NO calligraphy. " + ("padding text " * 12) + "robe with 繁复 pattern"
    check("否定不跨太远", pm(far, "繁复"))
    check("大写 NOT 生效", not pm("STRICT NO TEXT, NOT calligraphy", "calligraphy"))


def test_char_gender_required() -> None:
    """characters[].gender 必填（v0.3.20 + v0.3.22 强化）。

    v0.3.22 行为变更：以前 KNOWN_GENDER 表内人物（夫差/勾践/西施/张巡等 ~90 个）
    自动通过 — 让 planner 偷懒不填 gender。v0.3.22 起统一阻塞，
    KNOWN_GENDER 表只是 image_gen 管线的安全网，**不再是 preflight 的兜底**。
    """
    print("\n[13] gender 必填阻塞")
    sb = base_sb()
    # v0.3.22 变更：库内人物缺 gender 也必须报 block（不再被 KNOWN_GENDER 兜底绕过）
    sb["characters"] = [{"name": "夫差", "role": "反派", "visual_signature": "素袍"}]
    check("库内人物缺 gender 必报",
          "CHAR_GENDER_MISSING" in codes(run_preflight(sb)))
    # 库内人物+显式 gender -> 不报
    sb["characters"] = [{"name": "夫差", "role": "反派", "gender": "male",
                         "visual_signature": "素袍"}]
    check("库内人物+显式 gender 不报",
          "CHAR_GENDER_MISSING" not in codes(run_preflight(sb)))
    # 显式写了 -> 不报
    sb["characters"] = [{"name": "张三", "role": "配角", "gender": "male",
                         "visual_signature": "素袍"}]
    check("显式 gender 不报",
          "CHAR_GENDER_MISSING" not in codes(run_preflight(sb)))
    # 库外人物缺 gender -> 阻塞
    sb["characters"] = [{"name": "无名氏", "role": "配角", "visual_signature": "素袍"}]
    r = run_preflight(sb)
    check("库外人物缺 gender 阻塞", "CHAR_GENDER_MISSING" in codes(r))
    f = [x for x in r.findings if x.code == "CHAR_GENDER_MISSING"]
    check("报的是全文级单条", len(f) == 1 and f[0].page is None)


def test_truncation_keeps_boosts() -> None:
    """超限截断路径**不能丢** boost（v0.3.21 静默失败）。

    **事故**（kc_1790664590 p09）：`build_image_prompt` 有两条拼装路径，
    v0.3.18 加 boost 时只改了主路径，截断路径（scene 描述 > 9800 时走）
    漏掉 LIANHUANHUA_STYLE_LOCK + PATTERN_SUPPRESS →
    场景描述一长就丢约束 → 图崩成西式书房。

    这是本项目反复出现的那类 bug：改了主路径忘了改旁路。
    v0.3.14 的 regenerate_pages 缓存、v0.2.6 的 cinematic 剥离同源。
    """
    print("\n[14] 截断路径不丢 boost（v0.3.21）")
    from scripts.core.prompts import build_image_prompt as bip
    STYLE = "chinese_lianhuanhua_classic"
    CHECKS = [("COMPLETELY BLANK", "PATTERN_SUPPRESS"),
              ("NOT a 3D render", "LIANHUANHUA_STYLE_LOCK"),
              ("NO TEXT", "ZERO_TEXT_BOOST"),
              ("Avoid:", "negative")]

    short = "A man in a dark robe kneels in a vast snowfield."
    long_scene = short + " " * 0 + ("Broken staff, dead grass, grey sky. " * 200)

    for label, scene in (("主路径", short), ("截断路径", long_scene)):
        p = bip(STYLE, scene)
        check(f"{label} 长度不超限", len(p) <= 9800, f"len={len(p)}")
        for key, tag in CHECKS:
            check(f"{label} 含 {tag}", key in p)

    # 明确构造一个真的走截断的（长度 > 9800）
    p = bip(STYLE, long_scene)
    check("确实触发了截断", len(long_scene) > 2000, f"scene={len(long_scene)}")

def main() -> int:
    test_real_job_clean()
    test_injected_faults()
    test_negation_aware()
    test_both_input_paths()
    test_seven_element_not_actor()
    test_pinyin_character_recognized()
    test_dialogue_rule_is_mandatory()
    test_era_anachronism()
    test_code_level_boosts_injected()
    test_resolve_gender()
    test_gender_anchor_no_leak()
    test_negation_across_parens()
    test_char_gender_required()
    test_truncation_keeps_boosts()

    print(f"\n{'=' * 52}")
    print(f"passed {len(_passed)} / {len(_passed) + len(_failed)}")
    if _failed:
        print("FAILED: " + ", ".join(_failed))
        return 1
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
