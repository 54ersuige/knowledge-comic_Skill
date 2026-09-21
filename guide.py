"""guide.py · Mavis 触发引导脚本（v0.2.4）。

用法：
    python guide.py                          # 列出所有 step + 推荐矩阵
    python guide.py "Transformer"            # 拿主题推荐（英文）
    python guide.py "张巡守睢阳"             # 中文主题
    python guide.py recommend "王阳明心学"    # 显式 recommend 子命令

返回 JSON（脚本调用时）：
    {
      "style_id": "chinese_lianhuanhua_classic",
      "template_id": "c",
      "alternates": [
        ("guochao_manhua", "c"),
        ("cn_xuanfeng", "c")
      ],
      "rationale_zh": "...",
      "rationale_en": "..."
    }
"""
from __future__ import annotations
import json, sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from core.prompts import (  # noqa: E402
    recommend_style,
    recommend_style_rationale,
    recommend_template,
    list_styles,
    RECOMMEND_MATRIX,
    RECOMMEND_TEMPLATE_MATRIX,
)


def recommend(topic: str) -> dict:
    """根据主题返回推荐风格 + 模板 + 备选 + 理由。"""
    style_id, style_alts = recommend_style(topic)
    template_id, tpl_alts = recommend_template(topic)
    rationale_zh = recommend_style_rationale(topic)

    # 风格 → 模板配对（取风格第一备选 + 模板推荐）
    style_template_pairs = []
    for s in [style_id] + style_alts:
        for k, v in RECOMMEND_MATRIX.items():
            if s in v:
                pair_tpl = RECOMMEND_TEMPLATE_MATRIX.get(k, ("e",))[0]
                style_template_pairs.append((s, pair_tpl))
                break

    return {
        "topic": topic,
        "style_id": style_id,
        "template_id": template_id,
        "style_alternates": style_alts,
        "template_alternates": tpl_alts,
        "pairs": style_template_pairs,  # 风格 + 模板配对列表
        "rationale_zh": rationale_zh,
    }


def show_overview() -> str:
    """列出所有可用 step + 推荐矩阵（人类可读）。"""
    lines = [
        "=" * 60,
        "Knowledge Comic Skill · v0.2.4",
        "=" * 60,
        "",
        "## 锁定风格（5 种）",
    ]
    for s in list_styles():
        lines.append(f"  - {s['id']:35s} {s['name_zh']} ({s['category']})")

    lines += [
        "",
        "## 锁定模板（3 种）",
        "  - a  撕纸手账风   (黄便签 + 胶带 + 手写体)",
        "  - c  中国古典故事专版 (朱砂红 + 印章) ★ 历史典故第一推荐",
        "  - e  典雅知识风   (深蓝灰 + 印章) ★ 知识科普第一推荐",
        "",
        "## 推荐矩阵（主题 → 风格）",
    ]
    for kw, styles in RECOMMEND_MATRIX.items():
        lines.append(f"  - {kw:30s} → {styles[0]} (备选: {', '.join(styles[1:])})")

    lines += [
        "",
        "## Step API 入口（Python 直接 import）",
        "  from scripts.run import (",
        "      step_plan,              # Step 1",
        "      step_gen_images,        # Step 2",
        "      step_render_article,    # Step 3",
        "      step_publish_draft,     # Step 4",
        "      # v0.2.4 新增辅助",
        "      step_rewrite_visual,    # 重写某页 visual + 立即重跑",
        "      step_show_intent_vs_actual,  # 输出对照表",
        "      step_dry_publish,       # dry-run 渲染 publish html",
        "      step_preflight,         # 发布前自检（6 项）",
        "  )",
        "",
        "## 诊断工具",
        "  python diagnose_prompt.py <job_id>  # 检查 prompt 是否超 9800 字符",
        "  python diagnose_terms.py <job_id>   # 检查 visual 是否含风格锚点",
        "",
        "## Mavis 对话工作流（端到端）",
        "  /knowledge-comic → 问主题 → 推荐风格 + 模板 → ask_user 拍板 → ",
        "  step_plan → step_gen_images → step_render_article → step_publish_draft",
        "",
        "## 详细文档",
        "  SKILL.md · 主入口",
        "  references/handraw_styles.md · 5 个锁定风格完整定义",
        "  references/templates.md · 3 个排版模板",
        "  references/user-review.md · Mavis 对话流 + 对照表模板",
        "  references/workflow.md · 端到端流程图 + 调试指南",
        "  references/style_guide.md · 文章内容评分维度",
    ]
    return "\n".join(lines)


def main():
    if len(sys.argv) == 1:
        print(show_overview())
        return 0

    cmd = sys.argv[1]
    if cmd == "recommend" or cmd == "rec":
        if len(sys.argv) < 3:
            print("Usage: python guide.py recommend <topic>")
            return 1
        topic = " ".join(sys.argv[2:])
        result = recommend(topic)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # 否则把第一个参数当 topic
    topic = " ".join(sys.argv[1:])
    result = recommend(topic)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())