"""v0.3.28 回归测试：三处输出质量缺陷的修复

背景（2026-10-08，真实 LLM + 真实出图实测）：

Bug 1 · `banner` 假阳性 —— 历史战争题材整篇跑不了图
    planner 写 `black and red banners of the Yan army`（**军旗 / 旌旗**），
    而 `TEXT_INVITING_WORDS` 里的裸词 `banner` 把它当成"诱导模型画字"。
    实测 kc_1791447274「张巡守睢阳」p1 阻塞 → 12/12 页一张图都跑不了。
    与 v0.3.26 的 `inscriptions`、v0.3.15 的 NO_TEXT_MISSING 同源：
    关卡把合规写法当违规（第 3 次同类复发）。

Bug 2 · `new_yorker` / `us_mid_century` 漂成照片写实
    三个来源：
      a) `LIANHUANHUA_STYLE_LOCK`（戴敦邦派宣纸工笔连环画）被**无条件**拼进
         所有风格 —— new_yorker 的 prompt 里同时出现「Risograph 平面印刷」和
         「宣纸工笔连环画」，两套互斥指令打架 → 模型退回写实摄影（主因）；
      b) 非中国风格没有前置风格声明、也没有 STRICT STYLE LOCK；
      c) 非中国风格不剥 `// 中文速记` 和 `35mm / shallow_dof` —— 实测每页混入
         9 条中文速记，正是 v0.3.9 记录过的"中文语义冲淡英文风格锁定"。

Bug 3 · 七要素只落到 4 段 + 正文偏薄
    §4.2 的**范例题只写了 5 段**（漏 PLACEMENT / DEPTH LAYERS / LIGHTING），
    LLM 照抄范例 → 实测 kc_1791447274 七段只落到四段。
    正文下限同样只写在 prompt 里、没有代码兜底（上限已有 `_clamp_body`）。

测试原则：正向 + 反向必须同时成立 —— 只测"该放行"会把判据放松过头而不自知。
"""
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core.planner import PLANNER_SYSTEM_PROMPT  # noqa: E402
from scripts.core.preflight import (  # noqa: E402
    TEXT_INVITING_WORDS,
    run_preflight,
)
from scripts.core.prompts import (  # noqa: E402
    LIANHUANHUA_STYLE_LOCK,
    PRINT_ILLUSTRATION_STYLES,
    PRINT_STYLE_LOCK,
    PRINT_STYLE_PREFIX,
    TRADITIONAL_CN_STYLES,
    build_image_prompt,
)

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        FAILS.append(f"{name}  {detail}")
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


def codes(sb: dict) -> set[str]:
    return {f.code for f in run_preflight(sb).findings}


def sb_with_visual(visual: str, style_id: str = "chinese_lianhuanhua_classic") -> dict:
    """最小 storyboard，只为跑 visual 相关的关卡。"""
    return {
        "topic": "t", "style_id": style_id, "title": "t",
        "characters": [{"name": "张巡", "role": "主角", "era": "唐代",
                        "gender": "male", "visual_signature": "方颌, 短须, 黑色软脚幞头"}],
        "pages": [{
            "page": 1,
            "visual": visual,
            "caption": "睢阳城头",
            "dialogue": "贼知我粮尽。",
            "body": "睢阳城小，叛军黑压压一片。张巡手里没好箭，只好让兵士砍竹枝当箭使。"
                    "城里的守军看着像撑不过一夜。其实睢阳卡着大运河咽喉，"
                    "退一步，江淮的钱粮就断了，这是拿几千人换一条命脉。",
            "keywords": ["睢阳", "张巡", "竹枝箭"],
            "punchline": "城可以不守，路不能断。",
        }],
    }


# ===== Bug 1：banner 不再进词表 =====
print("=== Bug 1: 军旗 / 旌旗 不该被当成诱导画字 ===")

check("裸词 banner 已移出 TEXT_INVITING_WORDS",
      "banner" not in TEXT_INVITING_WORDS)
check("banner text 仍在词表（真风险词不能丢）",
      "banner text" in TEXT_INVITING_WORDS)
check("signboard / calligraphy / characters on 仍在词表",
      all(w in TEXT_INVITING_WORDS
          for w in ("signboard", "calligraphy", "characters on", "written")))

# 正向：真实历史战争场景不得再被拦
CW_BANNERS = (
    "CONCEPT: 螳臂当车的绝境 → 巨大叛军旗帜遮天蔽日。"
    "SUBJECT: 张巡与残兵 [GENDER:male]. "
    "ACTION: Zhang Xun points a dry bamboo spear at the sea of enemy flags. "
    "BACKGROUND: The vast horizon filled with black and red banners of the Yan army. "
    "CAMERA: extreme_wide, high_angle, 24mm, deep_focus. "
    "STRICT NO TEXT — plain fabric robes with NO characters/symbols/inscriptions."
)
got = codes(sb_with_visual(CW_BANNERS))
check("旌旗场景不再触发 TEXT_INVITING", "TEXT_INVITING" not in got, f"实际: {sorted(got)}")

# 反向：真正会诱导画字的写法必须继续拦
for word, text in (
    ("calligraphy", "the wall is covered with calligraphy"),
    ("signboard", "a wooden signboard above the entrance"),
    ("banner text", "a red banner text hangs above the gate"),
    ("written", "the oath is written on the tablet"),
    ("characters on", "characters on the blade"),
):
    sb = sb_with_visual(
        "CONCEPT: x. SUBJECT: 张巡 [GENDER:male]. ACTION: points. "
        f"BACKGROUND: {text}. CAMERA: wide, eye_level, 50mm, deep_focus. STRICT NO TEXT."
    )
    check(f"反向仍拦 {word!r}", "TEXT_INVITING" in codes(sb))


# ===== Bug 2：印刷插画风格的 prompt 构成 =====
print("=== Bug 2: 印刷插画风格（new_yorker / us_mid_century） ===")

NEUTRAL = (
    "CONCEPT: theory birth // 概念\n"
    "SUBJECT: a person [GENDER:male]\n"
    "ACTION: pointing at a chart\n"
    "CAMERA: wide shot, eye level, 35mm lens, shallow_dof // 中景 平视\n"
    "LIGHTING: cool overhead // 冷光 顶光\n"
)

for style in sorted(PRINT_ILLUSTRATION_STYLES):
    pr = build_image_prompt(style_id=style, scene_description=NEUTRAL)
    check(f"{style}: 不含连环画锁（互斥指令已拆）",
          "Dai Dunbang" not in pr and "lianhuanhua" not in pr.lower())
    check(f"{style}: 含前置印刷风格声明", PRINT_STYLE_PREFIX[:40] in pr)
    check(f"{style}: 含 STRICT STYLE LOCK 夹击", PRINT_STYLE_LOCK[:40] in pr)
    check(f"{style}: 中文速记已剥（// 之后无中文）",
          "// 中文速记" not in pr and "// 中景 平视" not in pr)
    # 只断言**场景段落**里没有摄影词 —— CAMERA_LANGUAGE_KIT 作为构图词汇表
    # 仍会提到 shallow_dof（v0.3.28 实测：把它拿掉反而漂成"线稿人贴照片"，
    # 已回退，见 prompts.build_image_prompt 里的实测记录）。
    scene_seg = pr.split("Scene: ", 1)[1].split("CAMERA FRAMING RULES", 1)[0]
    check(f"{style}: 场景里的摄影词已剥（35mm lens / shallow_dof）",
          "35mm lens" not in scene_seg and "shallow_dof" not in scene_seg)
    check(f"{style}: CONCEPT 已提到开头最高权重区",
          pr.lstrip("\n").startswith("=== WHAT THIS FRAME MUST SHOW"))

# 反向：中国画风格的行为不能被本次改动破坏
print("=== 反向：中国画风格行为不变 ===")
for style in sorted(TRADITIONAL_CN_STYLES):
    pr = build_image_prompt(style_id=style, scene_description=NEUTRAL)
    check(f"{style}: 仍含连环画锁", LIANHUANHUA_STYLE_LOCK[:40] in pr)
    check(f"{style}: 不含印刷锁", PRINT_STYLE_LOCK[:40] not in pr)
    check(f"{style}: 仍含宣纸前置声明",
          "classical Chinese painted illustration on rice paper" in pr)


# ===== Bug 3：七要素范例必须完整 =====
print("=== Bug 3: planner prompt 的七要素范例 ===")

SEVEN = ("SUBJECT:", "ACTION:", "CAMERA:", "PLACEMENT:", "DEPTH LAYERS:", "LIGHTING:", "MOOD")
missing = [s for s in SEVEN if s not in PLANNER_SYSTEM_PROMPT]
check("七要素范例含全部 7 段", not missing, f"缺失: {missing}")

check("正文下限已写明（不足 100 字 = 不合格）",
      "不足 100 字" in PLANNER_SYSTEM_PROMPT)

print("=" * 60)
if FAILS:
    print(f"FAILED {len(FAILS)}:")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print("ALL PASS (v0.3.28 输出质量三修)")
sys.exit(0)
