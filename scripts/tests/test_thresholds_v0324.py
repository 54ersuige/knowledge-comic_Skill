"""阈值漂移回归测试（v0.3.24）

背景
----
2026-10-08 审计发现项目有 5 道检查层（preflight / visual_qa / review_page /
check_alignment / story_script），各自定义同一批阈值，已经实际漂移：

    body > 150   preflight=warn  vs  review_page=error   ← 同一次跑两份矛盾结论
    body > 170   preflight=block  vs  review_page 无此档   ← 阻塞线比报告线还松
    body < 90    preflight=warn  vs  review_page 无此档
    keywords <3  preflight 无检查 vs review_page=warn      ← 1 个关键词的页能过阻塞关卡
    punchline    preflight 实按 30 放行，但文案写「10-22 字」← 代码与自己的提示打架
    dialogue     preflight 实按 90 放行，与规则 50 脱节

根因不是某个值定错，而是**同一个值被复制了 2~3 份**。本测试的作用不是
「再检查一遍数值对不对」，而是**让"某层偷偷自己写死一个数字"这件事失败** ——
这才是能防住下一次漂移的东西。

跑法：python scripts/tests/test_thresholds_v0324.py
"""
import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core import thresholds as T          # noqa: E402
from scripts.core import preflight as PF          # noqa: E402
from scripts.core import review_page as RP        # noqa: E402

fails = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{('  ' + detail) if detail else ''}")
    if not cond:
        fails.append(label)


print("=== 1. 两层实际行为一致（端到端，不看源码）===")
# review_page 对 160 字正文：应为 warn（目标带超一点），**不能**是 error
p160 = {"page": 1, "body": "字" * 160, "keywords": ["苏武"], "visual": "x" * 400}
iss = RP._check_body(p160, is_story=True)
check("body 160 字 -> review_page 只报 warn 不报 error",
      iss is not None and iss.level == "warn", f"level={getattr(iss, 'level', None)}")

# preflight 对同一个 160 字：必须是 warn（不是 block）
sb = {"style_id": "chinese_lianhuanhua_classic",
      "pages": [dict(p160, keywords=["苏武"])], "characters": []}
r = PF.run_preflight(sb)
codes = {f.code for f in r.findings}
check("body 160 字 -> preflight 不阻塞", not r.blocked)
check("body 160 字 -> preflight 给 BODY_LONG_SOFT", "BODY_LONG_SOFT" in codes,
      f"codes={sorted(codes)}")

# 200 字：两层都当 error/block
p200 = {"page": 1, "body": "字" * 200, "keywords": ["苏武"], "visual": "x" * 400}
iss2 = RP._check_body(p200, is_story=True)
sb2 = {"style_id": "chinese_lianhuanhua_classic",
       "pages": [dict(p200, keywords=["苏武"])], "characters": []}
r2 = PF.run_preflight(sb2)
check("body 200 字 -> review_page error", iss2 is not None and iss2.level == "error")
check("body 200 字 -> preflight block",
      any(f.code == "BODY_LONG" and f.level == "block" for f in r2.findings))

# 95 字：target 下沿之下但 > warn_lo，两层都不该报
p95 = {"page": 1, "body": "字" * 95, "keywords": ["苏武"], "visual": "x" * 400}
iss3 = RP._check_body(p95, is_story=True)
sb3 = {"style_id": "chinese_lianhuanhua_classic",
       "pages": [dict(p95, keywords=["苏武"])], "characters": []}
r3 = PF.run_preflight(sb3)
check("body 95 字 -> review_page 放行", iss3 is None, f"msg={getattr(iss3, 'msg', None)}")
check("body 95 字 -> preflight 不报 BODY_SHORT",
      "BODY_SHORT" not in {f.code for f in r3.findings})

# keywords 只有 1 个：preflight 现在必须能抓到（v0.3.24 补的漏洞）
pkw = {"page": 1, "body": "字" * 120, "keywords": ["苏武"], "visual": "x" * 400}
sb4 = {"style_id": "chinese_lianhuanhua_classic",
       "pages": [dict(pkw)], "characters": []}
r4 = PF.run_preflight(sb4)
check("keywords 1 个 -> preflight 报 KW_TOO_FEW",
      "KW_TOO_FEW" in {f.code for f in r4.findings})

print("\n=== 2. punchline / dialogue 与自身文案一致 ===")
p_long_punch = {"page": 1, "body": "字" * 120, "keywords": ["苏武"], "visual": "x" * 400,
                "punchline": "字" * 25, "dialogue": "古" * 10}
r5 = PF.run_preflight({"style_id": "chinese_lianhuanhua_classic",
                       "pages": [p_long_punch], "characters": []})
c5 = {f.code for f in r5.findings}
check("punchline 25 字 > 22 被抓 PUNCH_LONG", "PUNCH_LONG" in c5, f"codes={sorted(c5)}")
check("punchline 22 字不报（边界内）",
      "PUNCH_LONG" not in {f.code for f in PF.run_preflight(
          {"style_id": "chinese_lianhuanhua_classic",
           "pages": [dict(p_long_punch, punchline="字" * 22)], "characters": []}).findings})

p_long_q = dict(p_long_punch, dialogue="古" * 55)
r6 = PF.run_preflight({"style_id": "chinese_lianhuanhua_classic",
                       "pages": [p_long_q], "characters": []})
check("dialogue 55 字 > 50 被抓 QUOTE_LONG",
      "QUOTE_LONG" in {f.code for f in r6.findings})
check("dialogue 50 字不报（边界内）",
      "QUOTE_LONG" not in {f.code for f in PF.run_preflight(
          {"style_id": "chinese_lianhuanhua_classic",
           "pages": [dict(p_long_q, dialogue="古" * 50)], "characters": []}).findings})

print("\n=== 3. 两层引用的是同一份常量（不是各自复制）===")
check("review_page.BODY_MIN 指向 thresholds.BODY_TARGET_LO",
      RP.BODY_MIN is T.BODY_TARGET_LO, f"{RP.BODY_MIN} vs {T.BODY_TARGET_LO}")
check("review_page.BODY_MAX 指向 thresholds.BODY_TARGET_HI",
      RP.BODY_MAX is T.BODY_TARGET_HI)
check("preflight._f_body_len 默认值即 thresholds",
      PF._f_body_len.__defaults__ == (T.BODY_TARGET_LO, T.BODY_TARGET_HI,
                                      T.BODY_HARD_HI, T.BODY_WARN_LO),
      f"defaults={PF._f_body_len.__defaults__}")

print("\n=== 4. 源码里不得再出现裸字面量阈值 ===")
# 允许的例外：thresholds.py 自己、测试文件、docstring 里的举例
LAYERS = {
    "preflight.py": SKILL_ROOT / "scripts" / "core" / "preflight.py",
    "review_page.py": SKILL_ROOT / "scripts" / "core" / "review_page.py",
}
# (正则, 说明) —— 匹配"函数签名/比较里直接写死数字"的形态
BAD = [
    (re.compile(r"def _f_body_len\([^)]*hard_hi\s*=\s*\d"), "body_len 形参写死数字"),
    (re.compile(r"len\(pl\)\s*>\s*\d+"), "punchline 长度比较写死数字"),
    (re.compile(r"len\(d\)\s*>\s*\d+"), "dialogue 长度比较写死数字"),
    (re.compile(r"len\(kws\)\s*[<>]\s*\d+"), "keywords 数量比较写死数字"),
    (re.compile(r"^\s*BODY_(MIN|MAX)\s*=\s*\d", re.M), "review_page 自行定义 BODY_MIN/MAX"),
    (re.compile(r"^\s*KEYWORDS_(MIN|IDEAL)\s*=\s*\d", re.M), "review_page 自行定义 KEYWORDS_*"),
]
for fname, path in LAYERS.items():
    src = path.read_text(encoding="utf-8")
    for pat, desc in BAD:
        m = pat.search(src)
        check(f"{fname} 无「{desc}」", m is None,
              (m.group(0).strip()[:60] if m else ""))

print("\n=== 5. thresholds.py 自洽 ===")
check("target_lo < target_hi <= hard_hi",
      T.BODY_TARGET_LO < T.BODY_TARGET_HI <= T.BODY_HARD_HI)
check("warn_lo < target_lo", T.BODY_WARN_LO < T.BODY_TARGET_LO)
check("keywords min <= ideal <= max",
      T.KEYWORDS_MIN <= T.KEYWORDS_IDEAL <= T.KEYWORDS_MAX)
check("punch min < max", T.PUNCH_MIN < T.PUNCH_MAX)
check("quote min < max", T.QUOTE_MIN < T.QUOTE_MAX)
check("describe_body_policy 口径与数值一致",
      str(T.BODY_HARD_HI) in T.describe_body_policy()
      and str(T.BODY_TARGET_LO) in T.describe_body_policy())

print()
if fails:
    print(f"FAILED: {len(fails)} 项 -> {fails}")
    raise SystemExit(1)
print("ALL GREEN")
