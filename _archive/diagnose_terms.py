"""Diagnose whether storyboard visual descriptions contain style-critical terms.

Usage:
    python diagnose_terms.py [job_id]

For chinese_lianhuanhua_classic style, checks:
- "brush" / "rice paper" / "gongbi" / "baimiao" (英文锚点)
- 毛笔 / 宣纸 / 工笔 / 白描 / 写意 / 朱砂 / 飞白 / 留白 (中文术语)
- 是否有 candle / lantern / desk / porcelain 等"现代写实"物件词（会带偏模型）

If terms missing → model may drift to modern realistic style.
If 写实物件词 present → model may drift to 3D / photorealistic rendering.
"""
import json, sys, os
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent

# 风格专属术语库（按风格）
STYLE_TERMS = {
    "chinese_lianhuanhua_classic": {
        "en": ["brush", "rice paper", "gongbi", "baimiao", "dry-brush", "vermilion", "xuan paper"],
        "zh": ["毛笔", "宣纸", "工笔", "白描", "写意", "朱砂", "飞白", "留白"],
    },
    "guochao_manhua": {
        "en": ["manhua", "cel-shaded", "topknot", "hanfu", "cinnabar", "jade"],
        "zh": ["国潮", "赛璐璐", "古风", "条漫", "朱砂", "鸦青"],
    },
    "cn_xuanfeng": {
        "en": ["ink wash", "rice paper", "xieyi", "cinnabar", "dry-brush"],
        "zh": ["水墨", "宣纸", "写意", "朱砂", "飞白", "留白"],
    },
}

# 现代写实物件词（带偏警示）
MODERN_PHOTOREALISM_WORDS = [
    "candle", "lantern", "desk", "porcelain rest", "modern Chinese minimalism",
    "cinematic studio lighting", "volumetric light", "3D render", "photorealistic skin pores",
]


def diagnose_terms(job_id: str) -> str:
    """Return markdown table of terms per page + drift risk."""
    data_dir = SKILL_ROOT / "data" / job_id
    sb_path = data_dir / "storyboard.json"
    if not sb_path.exists():
        raise FileNotFoundError(f"No storyboard at {sb_path}")
    sb = json.loads(sb_path.read_text(encoding="utf-8"))
    style_id = sb.get("style_id", "new_yorker")
    terms = STYLE_TERMS.get(style_id, STYLE_TERMS["chinese_lianhuanhua_classic"])

    lines = [
        f"**风格**: `{style_id}`",
        f"**英文锚点**: {terms['en']}",
        f"**中文术语**: {terms['zh']}",
        "",
        "| 页 | visual 长度 | 英文锚点 | 中文术语 | 现代写实物件词(警告) | 风险 |",
        "|---|---|---|---|---|---|",
    ]
    for p in sb["pages"]:
        v = p["visual"]
        v_lower = v.lower()
        en_hit = sum(1 for t in terms["en"] if t.lower() in v_lower)
        zh_hit = sum(1 for t in terms["zh"] if t in v)
        drift = sum(1 for w in MODERN_PHOTOREALISM_WORDS if w.lower() in v_lower)
        if en_hit == 0 and zh_hit == 0:
            risk = "高 (无锚点,易跑偏)"
        elif drift > 0:
            risk = f"中 ({drift} 个写实词带偏)"
        elif en_hit + zh_hit < 2:
            risk = "中 (锚点少)"
        else:
            risk = "低"
        lines.append(f"| p{p['page']:02d} | {len(v)} | {en_hit} | {zh_hit} | {drift} | {risk} |")
    return "\n".join(lines)


def list_jobs() -> list[str]:
    data_dir = SKILL_ROOT / "data"
    if not data_dir.exists():
        return []
    return sorted([p.name for p in data_dir.iterdir() if p.is_dir() and p.name.startswith("kc_")])


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        job_id = sys.argv[1]
    else:
        jobs = list_jobs()
        if not jobs:
            print("No kc_* jobs found in data/")
            sys.exit(0)
        print(f"Available jobs: {jobs}")
        print(f"Usage: python {__file__} <job_id>")
        sys.exit(0)
    print(diagnose_terms(job_id))