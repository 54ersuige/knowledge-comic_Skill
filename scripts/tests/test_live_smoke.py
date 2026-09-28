"""真实题材冒烟测试（v0.3.4 新增）——调真 LLM，会烧额度。

为什么需要这个：
    v0.3.2 / v0.3.3 的审核都做了完整静态审查 + mock 回归，但**两个真 bug
    （苏武牧羊分类失败、keywords 被解析层丢弃）都是只有真跑才现形的**。
    纯 mock 测试看不见「LLM 是否真的按 schema 输出」「解析层是否接住了」。

设计：
    默认 **skip**（不烧额度），加 --live 才真跑。
    所以它适合放进手动流程 / 改完 planner、prompts 后主动跑一次，
    而不是挂到每次自检里。

用法：
    python scripts/tests/test_live_smoke.py            # skip，只打印计划
    python scripts/tests/test_live_smoke.py --live     # 真跑（烧 LLM 额度）

断言的重点（都是踩过坑的）：
    1. 风格推荐正确 —— 历史题材必须是 chinese_lianhuanhua_classic
    2. 模板跟随风格 —— 必须是 c（曾出现「风格对、模板错」的分裂输出）
    3. keywords 非空 —— 曾因解析层漏字段而 10/10 全空
    4. [GENDER:xx] 齐全 —— 曾因漏标导致男性主角被性转
    5. 页数符合 num_pages —— 曾因两处漏传被丢弃
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core import prompts as P  # noqa: E402

# 题材刻意选「苏武牧羊」：苏武不在人名表里、又无朝代词，
# 是 v0.3.3 兜底层上线后最容易回退的用例。
TOPIC = "苏武牧羊"
BULLETS = [
    "天汉元年使节出使匈奴，苏武率副使赴冥鹿台",
    "匈奴扣押苏武，威逼降汉，苏武宁死不屈",
    "苏武吞毡饮雪、食草根毡子苦撑十九载",
    "汉使诈称昭帝已崩，苏武悲痛万分",
    "李陵劝降不成，含泪离去",
    "常惠密奏光武帝，求归苏武骸骨归乡",
]
NUM_PAGES = 10

FAIL: list[str] = []


def ck(name: str, cond: bool, extra: str = "") -> None:
    print(("  PASS " if cond else "  FAIL "), name, extra)
    if not cond:
        FAIL.append(name)


def offline_checks() -> None:
    """不烧额度的部分：分类器 + 审阅模块本身。"""
    print("=== 1. 分类器（离线）===")
    s, _ = P.recommend_style(TOPIC)
    t, _ = P.recommend_template(TOPIC)
    ck(f"{TOPIC} -> 连环画", s == "chinese_lianhuanhua_classic", f"(got {s})")
    ck(f"{TOPIC} -> 模板 c", t == "c", f"(got {t})")

    print()
    print("=== 2. 审阅模块（离线，用 mock 数据）===")
    from scripts.core.review_page import check_quality, render_html, render_markdown

    good = {
        "topic": "T", "title": "测试标题", "subtitle": "副标题",
        "style_id": "chinese_lianhuanhua_classic",
        "recommended_template": "c",
        "pages": [{
            "page": 1, "visual": "SUBJECT: A [GENDER:male]; SECONDARY: B, C. " + "x" * 320
            + " NO TEXT", "caption": "章节题", "body": "正" * 120,
            "highlight": "起", "keywords": ["苏武", "匈奴", "北海"],
        }],
    }
    h = check_quality(good)
    ck("合格分镜 0 error", h["stats"]["errors"] == 0,
       f"(errors={h['stats']['errors']}, warns={h['stats']['warns']})")

    bad = json_deepcopy(good)
    bad["pages"][0]["keywords"] = []
    bad["pages"][0]["body"] = ""
    bad["pages"][0]["visual"] = "单人物无标记"
    h2 = check_quality(bad)
    fields = {i.field for i in h2["issues"] if i.level == "error"}
    ck("问题分镜能抓出 keywords/body/visual", {"keywords", "body", "visual"} <= fields,
       f"(got {sorted(fields)})")

    md = render_markdown(good, h)
    html = render_html(good, h)
    ck("Markdown 审阅卡含体检看板", "自动体检" in md)
    ck("HTML 审阅页含看板与页块", "class=\"board\"" in html and "PAGE 01" in html)
    ck("HTML 无未替换占位符", "__TITLE__" not in html and "__BOARD__" not in html)


def json_deepcopy(d):
    import copy
    return copy.deepcopy(d)


def live_checks() -> None:
    """真跑：调 LLM 生成 10 页分镜。"""
    from scripts.run import step_plan, step_review_storyboard

    print()
    print(f"=== 3. 真实分镜生成（调 LLM，约 1-3 分钟）===")
    tmp = Path(tempfile.mkdtemp())
    try:
        sb, job_id, work_dir = step_plan(
            topic=TOPIC, bullets=BULLETS, num_pages=NUM_PAGES, data_dir=tmp
        )
        ck("风格 = 连环画", sb.style_id == "chinese_lianhuanhua_classic", f"({sb.style_id})")
        ck(f"页数 = {NUM_PAGES}", len(sb.pages) == NUM_PAGES, f"(got {len(sb.pages)})")

        kw_pages = [p for p in sb.pages if p.keywords]
        ck("每页都有 keywords（曾整条链路失效）",
           len(kw_pages) == len(sb.pages),
           f"({len(kw_pages)}/{len(sb.pages)})")

        gender_pages = [p for p in sb.pages if "[GENDER:" in (p.visual or "").upper()]
        ck("每页都有 [GENDER:xx]",
           len(gender_pages) == len(sb.pages),
           f"({len(gender_pages)}/{len(sb.pages)})")

        body_ok = [p for p in sb.pages
                   if 100 <= len((p.body or "").strip()) <= 150]
        body_over = [p for p in sb.pages if len((p.body or "").strip()) > 150]
        # 正文长度是 LLM 提示的软约束，有合理波动，不适合做硬 PASS/FAIL：
        # 真正必须守住的是上限（用户硬偏好：文字太重会压过画面），
        # 偶发偏短（<100）只提示不强判。
        ck("正文无超标页（>150 字必须为 0）",
           len(body_over) == 0,
           f"(超长 {len(body_over)} 页: {[p.page for p in body_over]})")
        print(f"  INFO  正文达标 {len(body_ok)}/{len(sb.pages)} 页 "
              f"(偏短 {[p.page for p in sb.pages if len((p.body or '').strip()) < 100]} 页，仅提示)")

        # 审阅模块在真实数据上跑通
        md, html_path = step_review_storyboard(job_id, data_dir=tmp)
        ck("真实分镜能生成审阅产物", bool(md) and html_path is not None and html_path.exists())
        ck("审阅卡含自动体检", "自动体检" in md)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="真跑 LLM（烧额度）。不加则只跑离线部分。")
    args = ap.parse_args()

    if not args.live:
        print("[skip] 未加 --live，跳过真实 LLM 调用（不烧额度）")
        print("       要真跑: python scripts/tests/test_live_smoke.py --live\n")
    offline_checks()
    if args.live:
        live_checks()
    else:
        print()
        print("[skip] 已跳过 step_plan 真跑。如需验证 LLM 输出链路请加 --live")

    print()
    print("=" * 46)
    print("FAILED:", FAIL if FAIL else "NONE — 全部通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
