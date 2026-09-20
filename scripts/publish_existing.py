"""Publish existing kc_<id>/ images to WeChat (without regen).

用法:
  python publish_existing.py <job_id> [--template c]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core.config import get_config
from scripts.core.planner import Storyboard, StoryPage
from scripts.core import article as article_mod
from scripts.core import publisher as pub_mod


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python publish_existing.py <job_id> [--template c]")
        return 1

    job_id = sys.argv[1]
    template = "c"
    for i, arg in enumerate(sys.argv):
        if arg == "--template" and i + 1 < len(sys.argv):
            template = sys.argv[i + 1]

    cfg = get_config()
    work_dir = cfg.data_dir / job_id
    sb_path = work_dir / "storyboard.json"
    pages_dir = work_dir / "pages"

    if not sb_path.exists() or not pages_dir.exists():
        print(f"NOT FOUND: {sb_path} or {pages_dir}")
        return 1

    # Load storyboard
    raw = json.loads(sb_path.read_text(encoding="utf-8"))
    sb = Storyboard(
        topic=raw["topic"],
        style_id=raw["style_id"],
        title=raw.get("title", raw["topic"]),
        subtitle=raw.get("subtitle", ""),
        summary=raw.get("summary", ""),
        preface=raw.get("preface", ""),
        epigraph=raw.get("epigraph", ""),
        postscript=raw.get("postscript", ""),
        pages=[StoryPage(**p) for p in raw["pages"]],
    )

    # Load images
    image_paths = sorted(pages_dir.glob("*.png"))
    if not image_paths:
        print(f"NO images in {pages_dir}")
        return 1

    print(f"Found {len(image_paths)} images in {job_id}")
    print(f"  template: {template}")
    print(f"  title:    {sb.title}")
    print()

    # Step 1: Upload all images
    print("=" * 60)
    print("  Upload images to WeChat")
    print("=" * 60)
    uploaded = []
    wechat_urls = []
    for i, path in enumerate(image_paths, start=1):
        print(f"  [{i}/{len(image_paths)}] uploading {path.name}", end=" ... ")
        result = pub_mod.add_permanent_image(path)
        uploaded.append({"page": i, "media_id": result["media_id"], "url": result["url"]})
        wechat_urls.append(result["url"])
        print(f"OK -> {result['media_id'][:20]}...")

    # Step 2: Re-render article with WeChat URLs
    print()
    print("=" * 60)
    print("  Re-render article with WeChat URLs")
    print("=" * 60)
    publish_html = article_mod.render_publish_article(sb, wechat_urls, template=template)
    out_html = work_dir / f"publish_{template}_wechat.html"
    out_html.write_text(publish_html, encoding="utf-8")
    print(f"  saved: {out_html}  ({len(publish_html)} chars)")

    # Step 3: Create draft
    print()
    print("=" * 60)
    print("  Create WeChat draft")
    print("=" * 60)
    thumb_media_id = uploaded[0]["media_id"]
    draft_id = pub_mod.create_draft(
        title=sb.title,
        content_html=publish_html,
        thumb_media_id=thumb_media_id,
    )
    print(f"  DRAFT CREATED: {draft_id}")
    print()
    print("=" * 60)
    print("  DONE")
    print("=" * 60)
    print(f"  job_id:         {job_id}")
    print(f"  draft_media_id: {draft_id}")
    print(f"  title:          {sb.title}")
    print(f"  uploaded:       {len(uploaded)} images")
    print(f"  go to:          https://mp.weixin.qq.com → 草稿箱")
    return 0


if __name__ == "__main__":
    sys.exit(main())