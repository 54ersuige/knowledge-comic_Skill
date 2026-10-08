"""v0.3.26 回归测试：preflight 两个判据反转 bug

**背景（实测 kc_1791440435「修建颐和园」）**：12 页分镜跑完 preflight，
报出 13 个阻塞项，一张图都跑不了。而这两条阻塞**都不是内容问题**，
是关卡把最标准的合规写法当成违规 —— 与 v0.3.15 那次判据反转事故同源。

Bug 1 · 零文字声明里的枚举被误判为「诱导画字」
    planner 每页都以这句结尾：
        `STRICT NO TEXT ... NO characters/symbols/inscriptions ...`
    `inscriptions` 就在否定词 `NO` 的**枚举第三项**里 —— 它本身是
    零文字声明的组成部分。但 `_negated_before` 要求否定词与被检词之间
    「只隔连接符」，撞上枚举项里的实词 `characters` 就判定否定作用域
    已断 → 12/12 页全误报。后果：最标准的合规写法反而跑不了图。

Bug 2 · 清代皇帝穿龙袍被判时代穿帮
    `ANACHRONIC_MARKERS` 是为「春秋吴王被写成明清帝王」设计的先秦词表，
    却对清代角色照样开火。characters 里的乾隆（era=清中）签名写
    「戴双龙朝冠, 穿明黄色团龙袍」—— 这是清代皇帝的**正统朝服**，
    被判 ERA_ANACHRONISM 阻塞。若照提示改成「素麻袍+发束高髻」，
    等于把乾隆画成先秦布衣，比穿帮更糟。

**测试原则**：正向（该放行）+ 反向（该拦）必须同时成立。
只测正向会把判据放松过头而不自知 —— v0.3.26 第一版修复就发生过：
新增的枚举扫描走到窗口尽头时无条件放行，导致 `NO banner`、
`(NOT calligraphy)`、`无繁复纹样` 三条既有行为全部回归。
"""
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core.preflight import (  # noqa: E402
    ANACHRONIC_MARKERS,
    _WEAK_ANACHRONISM,
    _ANACHRONIC_IMPERIAL_ONLY,
    _era_has_imperial_dress,
    _positive_mention,
)

FAILS: list[str] = []


def expect_flag(word: str, text: str, should_flag: bool, label: str) -> None:
    """被检词在该文本里是否应被判为「肯定出现」。"""
    got = _positive_mention(text, word)
    if got != should_flag:
        FAILS.append(
            f"{label}: {word!r} in {text[:60]!r} -> {got}, 期望 {should_flag}")
    mark = "PASS" if got == should_flag else "FAIL"
    print(f"  [{mark}] {label}: {word!r} -> {should_flag}")


def era_hits(sig: str, era: str) -> list[str]:
    """复现 _f_era_anachronism 的判定链（含 v0.3.26 时代门槛）。"""
    hits = [w for w in ANACHRONIC_MARKERS if _positive_mention(sig, w)]
    if _era_has_imperial_dress(era):
        hits = [w for w in hits if w not in _ANACHRONIC_IMPERIAL_ONLY]
    weak = [w for w in hits if w in _WEAK_ANACHRONISM]
    strong = [w for w in hits if w not in _WEAK_ANACHRONISM]
    if not strong and len(weak) < 2:
        return []
    return strong + weak[:1]


def expect_era(sig: str, era: str, should_block: bool, label: str) -> None:
    hits = era_hits(sig, era)
    got = bool(hits)
    if got != should_block:
        FAILS.append(
            f"{label}: era={era!r} sig={sig[:44]!r} -> {hits}, "
            f"期望 {'阻塞' if should_block else '放行'}")
    mark = "PASS" if got == should_block else "FAIL"
    print(f"  [{mark}] {label}: era={era} -> "
          f"{'阻塞 ' + str(hits) if hits else '放行'}")


# ===== Bug 1：否定作用域跨枚举 =====
print("=== Bug 1: 零文字声明里的枚举 ===")

ZERO_TEXT = ("STRICT NO TEXT - plain fabric robes with "
             "NO characters/symbols/inscriptions, map shows ONLY "
             "abstract terrain without any writing")

# 正向：planner 的标准零文字声明，三个枚举项都应放行
expect_flag("inscription", ZERO_TEXT, False, "枚举第三项")
expect_flag("characters", ZERO_TEXT, False, "枚举第一项")
expect_flag("symbols", ZERO_TEXT, False, "枚举第二项")
expect_flag("written", ZERO_TEXT, False, "声明尾部 written")

# 正向：更短的形态
SHORT_ENUM = "no characters/symbols/inscriptions, plain fabric robes"
expect_flag("inscription", SHORT_ENUM, False, "短形态-第三项")
expect_flag("symbols", SHORT_ENUM, False, "短形态-第二项")

# 反向：真的在诱导画字的必须继续拦
expect_flag("banner", "a red banner hangs above the gate", True, "反向-肯定 banner")
expect_flag("signboard", "a wooden signboard above the entrance", True, "反向-肯定 signboard")
expect_flag("calligraphy", "the wall is covered with calligraphy", True, "反向-肯定 calligraphy")
expect_flag("inscription", "robes with bright patterns and inscription", True, "反向-肯定 inscription")
# 否定被普通词截断 → 后面的 banner 不受否定保护
expect_flag("banner", "no text here, a banner is red", True, "反向-否定被截断")

# 既有能力不能退化（v0.3.18 / v0.3.20 的行为）
expect_flag("calligraphy", "(NOT calligraphy) plain fabric only", False, "既有-NOT括号")
expect_flag("banner", "NO banner, no signboard, plain field", False, "既有-全否定")
expect_flag("inscription", "plain robes with NO inscription", False, "既有-紧邻否定")
expect_flag("written", "no written marks anywhere", False, "既有-written否定")

# 记录一条既有限制（v0.3.26 未改动它，避免与本轮修 bug 混在一起）：
# _NEGATION_CUES 只有英文线索，中文「无」不在表内 → 「无繁复纹样」会命中。
# 这是 v0.3.18 起就存在的行为，原始版本实测同样为 True。
expect_flag("繁复", "长袍素净，无繁复纹样", True, "既有限制-中文无不被识别")


# ===== Bug 2：时代门槛 =====
print("=== Bug 2: 清代角色穿龙袍 ===")

# 正向：清代皇帝的朝服不该被判穿帮
expect_era("清中皇帝, 50 岁, 方颌, 浓眉, 短须, 戴双龙朝冠, 穿明黄色团龙袍, 手持玉如意",
           "清中", False, "乾隆龙袍朝冠")
expect_era("晚清太后, 60 岁, 戴金凤冠, 穿深青色团龙旗装, 手持翡翠如意",
           "晚清", False, "慈禧凤冠团龙")
expect_era("明代官员, 戴乌纱帽, 穿补服, 佩朝珠",
           "明", False, "明代乌纱补服")

# 反向：先秦角色穿明清帝王服必须继续拦
expect_era("春秋吴王, 方颌, 浓眉, 戴华丽的金质发冠, 穿繁复的丝绸锦袍",
           "春秋战国", True, "先秦-金冠丝绸")
expect_era("春秋吴王, 戴乌纱帽, 穿补服",
           "春秋战国", True, "先秦-乌纱补服")

# 反向：现代器物对任何古代角色都是穿帮，不受时代门槛影响
expect_era("清中皇帝, 身穿龙袍, 坐在沙发上, 旁边是机械钟",
           "清中", True, "清代-现代器物仍拦")


print("=" * 60)
if FAILS:
    print(f"FAILED {len(FAILS)}:")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print("ALL PASS (v0.3.26 preflight 判据反转修复)")
sys.exit(0)