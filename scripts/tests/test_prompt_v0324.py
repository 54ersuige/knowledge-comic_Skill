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

print("\n=== 朝代速查表已移出 system prompt（改条件注入）===")
check("planner prompt 内不再内联速查表", "春秋战国（前770-前221）" not in P)
check("仍保留 era 规则摘要", "朝代服饰考据" in P)

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
