"""Skill 端到端 · 非交互版（绕开 argparse + input + 加 review/canon）

流程：
  plan → review → (重试 if score < 80) → image gen → render → publish

调用：
  python scripts/run_plain.py <topic> <style> <template> <bullets...> [--publish]
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core.config import get_config
from scripts.core.planner import plan_storyboard, Storyboard
from scripts.core.image_gen import generate_pages
from scripts.core import article as article_mod
from scripts.core import publisher as pub_mod
from scripts.canon import get_canon_injection
from scripts.review import review_storyboard

logger = logging.getLogger(__name__)

# 自动重试阈值（参考 style_guide.md §5）
RETRY_THRESHOLD = 80
MAX_RETRIES = 2


def banner(s: str) -> None:
    print()
    print("=" * 60)
    print(f"  {s}")
    print("=" * 60)
    # 强制 UTF-8 输出（兼容 Windows GBK）
    import sys
    sys.stdout.reconfigure(encoding="utf-8")


def _plan_with_review(topic: str, bullets: list[str], style_id: str, canon_inj: str):
    """planner → review → 必要时重试 → 返回 (storyboard, review_result)。

    返回最后一个 review_result（即使失败），让调用方决定是否继续。
    """
    attempts = []
    for i in range(MAX_RETRIES + 1):
        sb = plan_storyboard(topic, bullets, style_id, use_llm=True, canon_injection=canon_inj)
        review = review_storyboard(sb.to_dict())
        attempts.append((sb, review))
        print(f"  [Review #{i+1}] total={review.total}/100 "
              f"(depth={review.dimensions['depth']}/30 "
              f"consistency={review.dimensions['consistency']}/30 "
              f"voice={review.dimensions['voice']}/40) "
              f"{'✅ PASS' if review.passed else '❌ FAIL'}")
        if review.feedback:
            print(f"    feedback: {'; '.join(review.feedback[:2])}")
        marker = "[PASS]" if review.passed else "[FAIL]"
        print(f"  [Review #{i+1}] {marker} total={review.total}/100 "
              f"(depth={review.dimensions['depth']}/30 "
              f"consistency={review.dimensions['consistency']}/30 "
              f"voice={review.dimensions['voice']}/40)")
        if review.feedback:
            print(f"    feedback: {'; '.join(review.feedback[:2])}")
        if review.passed:
            return sb, review
        if i < MAX_RETRIES:
            print(f"  -> retrying (max {MAX_RETRIES + 1})...")
    return attempts[-1]


def run_end_to_end(
    topic: str,
    bullets: list[str],
    style_id: str,
    template: str = "a",
    auto_publish: bool = False,
) -> dict:
    """端到端：plan → review → image → render → publish（或 dry-run）"""
    cfg = get_config()
    job_id = f"kc_{int(time.time())}"

    # 加载 Canon
    canon_inj = get_canon_injection()
    if canon_inj:
        banner("Step 0: Canon loaded")
        print(f"  ({len(canon_inj.splitlines())} lines injected into planner)")

    # Step 1: Planner + Review
    banner("Step 1: Planner + Review (LLM-as-Judge)")
    sb, review = _plan_with_review(topic, bullets, style_id, canon_inj)
    print(f"  title:  {sb.title}")
    print(f"  pages:  {len(sb.pages)}")
    for p in sb.pages:
        print(f"    p{p.page:02d}  cap={p.caption[:30]!r}")

    # Step 2: Image gen
    banner(f"Step 2: Image gen ({len(sb.pages)} pages)")
    t0 = time.time()
    image_paths = generate_pages(sb, job_id)
    print(f"  total: {time.time()-t0:.0f}s, {len(image_paths)} images")

    # Step 3: Render article
    banner(f"Step 3: Render article (template={template})")
    publish_html_local = article_mod.render_publish_article(
        sb, [str(p) for p in image_paths], template=template,
    )

    work_dir = cfg.data_dir / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    import json
    from dataclasses import asdict, is_dataclass

    def _default(o):
        return asdict(o) if is_dataclass(o) else str(o)

    (work_dir / "storyboard.json").write_text(
        json.dumps(sb, default=_default, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (work_dir / f"article_{template}.html").write_text(
        publish_html_local, encoding="utf-8",
    )
    print(f"  storyboard: {work_dir / 'storyboard.json'}")
    print(f"  html:       {work_dir / f'article_{template}.html'}")

    # Save review result for record
    (work_dir / "review.json").write_text(
        json.dumps(review.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if not auto_publish:
        banner("DRY-RUN: 跳过发布")
        print(f"  job_id:       {job_id}")
        print(f"  review total: {review.total}/100")
        print(f"  passed:       {review.passed}")
        print(f"  pages:        {len(image_paths)}")
        print(f"  article html: {work_dir / f'article_{template}.html'}")
        return {"job_id": job_id, "storyboard": sb, "image_paths": image_paths, "draft_media_id": None}

    # Step 4: Publish
    banner("Step 4: Publish to WeChat MP")
    uploaded = []
    wechat_urls = []
    for i, path in enumerate(image_paths, start=1):
        print(f"  [{i}/{len(image_paths)}] uploading {path.name}", end=" ... ")
        result = pub_mod.add_permanent_image(path)
        uploaded.append({"page": i, "media_id": result["media_id"], "url": result["url"]})
        wechat_urls.append(result["url"])
        print(f"OK -> {result['media_id'][:20]}...")

    publish_html_final = article_mod.render_publish_article(
        sb, wechat_urls, template=template,
    )
    (work_dir / f"publish_{template}.html").write_text(
        publish_html_final, encoding="utf-8",
    )

    draft_id = pub_mod.create_draft(
        title=sb.title,
        content_html=publish_html_final,
        thumb_media_id=uploaded[0]["media_id"],
    )

    banner("DONE")
    print(f"  job_id:         {job_id}")
    print(f"  review total:   {review.total}/100")
    print(f"  draft_media_id: {draft_id}")
    print(f"  title:          {sb.title}")
    print(f"  uploaded:       {len(uploaded)} images")
    print(f"  go to:          https://mp.weixin.qq.com → 草稿箱")

    return {
        "job_id": job_id,
        "storyboard": sb,
        "image_paths": image_paths,
        "draft_media_id": draft_id,
        "review": review.to_dict(),
    }


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python run_plain.py <topic> <style> <template> <bullets...> [--publish]")
        print('Example: python run_plain.py "黑死病" new_yorker c "1347年港口" "老鼠跳蚤" "1/3人口"')
        sys.exit(1)

    topic = sys.argv[1]
    style_id = sys.argv[2]
    template = sys.argv[3]
    bullets = sys.argv[4:] if "--publish" not in sys.argv else sys.argv[4:-1]
    auto_publish = "--publish" in sys.argv

    result = run_end_to_end(topic, bullets, style_id, template, auto_publish=auto_publish)

    print()
    print("JSON_RESULT_START")
    import json
    print(json.dumps({
        "job_id": result["job_id"],
        "draft_media_id": result["draft_media_id"],
        "title": result["storyboard"].title,
        "review_total": result.get("review", {}).get("total", "?"),
        "review_passed": result.get("review", {}).get("passed", "?"),
    }, ensure_ascii=False))
    print("JSON_RESULT_END")