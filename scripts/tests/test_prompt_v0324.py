"""verify_prompt.py — v0.3.24 一次性校验：prompt 瘦身结果 + JSON 示例合法性。

这个校验本身也应该留下 —— JSON 示例非法是**阻塞级**问题
（LLM 照抄 `{"gender": {"enum": [...]}}` → preflight CHAR_GENDER_MISSING
→ 一张图都不跑），靠肉眼很难每次都发现。
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.core.planner import PLANNER_SYSTEM_PROMPT as P  # noqa: E402

fails = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{('  ' + detail) if detail else ''}")
    if not cond:
        fails.append(label)


print("=== prompt 体积 ===")
n = len(P)
print(f"  当前 {n} 字符 (v0.3.23 为 22064)")
check("压到 14000 以内", n < 14000, f"实际 {n}")
check("压掉至少 35%", n < 22064 * 0.65, f"实际降幅 {100 - n / 22064 * 100:.0f}%")

print("\n=== JSON 输出示例必须是合法 JSON（阻塞级）===")
m = re.search(r"```json\n(.*?)\n```", P, re.S)
check("找到 ```json 示例块", m is not None)
if m:
    try:
        d = json.loads(m.group(1))
        check("json.loads 通过", True)
        check("顶层含 characters", "characters" in d)
        check("顶层含 pages", "pages" in d)
        ch = d.get("characters", [{}])[0]
        check("gender 是裸字符串 male/female",
              ch.get("gender") in ("male", "female"),
              f"实际={ch.get('gender')!r} type={type(ch.get('gender')).__name__}")
        check("gender 不是嵌套对象/数组",
              not isinstance(ch.get("gender"), (dict, list)))
        check("era 存在且是字符串", isinstance(ch.get("era"), str), f"era={ch.get('era')!r}")
        pg = d.get("pages", [{}])[0]
        for f in ("page", "visual", "caption", "dialogue", "narration",
                  "body", "keywords", "punchline", "key_visual", "highlight"):
            if f not in pg:
                check(f"page 含 {f}", False)
        check("page 九字段齐全", True)
    except Exception as e:
        check("json.loads 通过", False, repr(e))

print("\n=== 硬规则不得在瘦身中丢失 ===")
must_keep = {
    "CONCEPT 段": "CONCEPT:",
    "三拍-说破": "说破",
    "术语翻译": "术语（大白话解释）",
    "裸术语清单": "上兵",
    "专有名词免解释": "专有名词不需要解释",
    "五件套 bible": "FIVE ANCHORS",
    "GENDER 标记": "[GENDER:male]",
    "gender 硬约束": '"gender": "male"',
    "era 必填": "era",
    "零文字强化句": "STRICT NO TEXT",
    "七要素 SUBJECT": "**SUBJECT**",
    "七要素 DEPTH": "**DEPTH LAYERS**",
    "中文速记": "// 中文",
    "表情 anchor": "rage_scream",
    "连环画多人物": "主人物 ≥ 3 个",
    "镜头分配": "开-推-特-退",
    "caption 匹配": "画面与 caption 严格匹配",
    "对话每页必填": "留空 = 图下蒙版空着",
    "史实只用正史": "《资治通鉴》",
    "不编人物": "不编人物",
    "不写 hedging": "不写 hedging",
    "关键词 3-6": "3-6 个",
    "正文 100-150": "100-150 字",
}
for label, needle in must_keep.items():
    check(f"保留 {label}", needle in P)

print("\n=== 应被删掉的噪音 ===")
must_drop = {
    "版本考古": "v0.2.3 升级",
    "事故复盘(粗体根因)": "**根因**：",
    "事故复盘(根因块)": "**问题根因**：",
    "job_id 引用": "kc_1790664590",
    "Mavis 流程元叙述": "Mavis 拿到 storyboard",
    "layout_preview 元叙述": "layout_preview 展示分镜",
    "假 enum 写法": '{"enum": ["male", "female"]}',
}
for label, needle in must_drop.items():
    check(f"已删 {label}", needle not in P)

print("\n=== 结构性规则必须在「写它的那个章节」里（v0.3.25 live 回归）===")
# v0.3.25 实测事故：重排 prompt 时把 [GENDER:xx] 从 §4（visual 章节）挪到了
# §5（characters 章节），结果 LLM 写 visual 时根本看不到那条要求 ——
# live 冒烟 0/10 页带标记（改之前是 10/10）。规则放在错误的章节 = 规则不存在。
# 下面这些断言的是"规则与它约束的字段在同一章节"，不只是"全文出现过"。
SECTION_RULES = [
    ("[GENDER:xx] 在 visual 章节", "### 4.5", "[GENDER:male]"),
    ("CONCEPT 在七要素之前", "### 4.1", "必须在 SUBJECT 之前"),
    ("中文速记在七要素章节", "### 4.2", "**每段末尾必须追加"),
    ("零文字在 visual 章节", "### 4.6", "STRICT NO TEXT"),
    ("dialogue 必填在 §3", "### 3.4", "每一页都要写"),
    ("三拍结构在 §3", "### 3.1", "说破"),
    ("术语翻译在 §3", "### 3.2", "术语（大白话解释）"),
    ("朝代考据在 §7", "## 7.", "三件错配"),
]
for label, section, needle in SECTION_RULES:
    idx = P.find(section)
    check(f"{label}", idx >= 0 and needle in P[idx:idx + 2600],
          "章节缺失或规则不在该章节附近" if idx >= 0 else "章节不存在")

# 反向：GENDER 规则不许只出现在 §5（characters）而不在 §4
i45 = P.find("### 4.5")
i5 = P.find("## 5. characters[]")
i6 = P.find("## 6. 输出格式")
check("§4.5 之前就有 GENDER 三值枚举（不是只在 §5 引用）",
      i45 >= 0 and "[GENDER:female]" in P[i45:i45 + 2600])
# §5 只许引用 §4.5，不许再抄一份三值枚举（第二份复制品 = 下次重排又会漂）
check("§5 里 GENDER 只作引用、不重复正文",
      "见 **§4.5 c**" in P and i5 > 0 and i6 > i5
      and "[GENDER:mixed]" not in P[i5:i6],
      f"§5 区间内 [GENDER:mixed] 出现 {P[i5:i6].count('[GENDER:mixed]')} 次")

print("\n=== 朝代速查表已移出 system prompt（改条件注入）===")
check("仍保留 era 规则摘要", "朝代服饰考据" in P)
check("planner prompt 内不再内联速查表", "春秋战国（前770-前221）" not in P)

print("\n=== 条件注入：历史风格必须拿回速查表 ===")
from scripts.core.planner import build_system_prompt, _CN_HISTORY_STYLES  # noqa: E402
from scripts.core.prompts import CN_DYNASTY_COSTUME_GUIDE  # noqa: E402

for s in sorted(_CN_HISTORY_STYLES):
    p = build_system_prompt(s, 10)
    check(f"{s} 注入速查表", "春秋战国（前770-前221）" in p)
    check(f"{s} 页数已替换", "输出 10 页" in p)
    # 内容完整性：抽查 3 个稳定锚点（不能用切片比对 —— 页数替换会让
    # "输出 6-10 页"→"输出 10 页" 长度差 2，后面所有字符都偏移）
    check(f"{s} 内容完整非截断",
          all(a in p for a in ("## 4. visual 字段结构", "### 4.2 七要素",
                               "## 6. 输出格式", "## 7. 朝代服饰考据")))

for s in ("new_yorker", "us_mid_century"):
    p = build_system_prompt(s, 10)
    check(f"{s} 不注入速查表（省 {len(P) - len(p)} 字符）",
          "春秋战国（前770-前221）" not in p and len(p) < len(P) + 200)

check("速查表与 preflight 用的是同一份常量",
      CN_DYNASTY_COSTUME_GUIDE.strip() in build_system_prompt("cn_xuanfeng"))
check("未指定页数时保留原始页数文案",
      "输出 6-10 页分镜脚本" in build_system_prompt("cn_xuanfeng"))

print()
if fails:
    print(f"FAILED: {len(fails)} 项 -> {fails}")
    raise SystemExit(1)
print("ALL GREEN")
