"""Re-render article with a different template, reusing existing PNG + storyboard.

No image regen, no LLM call - just re-render HTML.
"""
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core.config import get_config
from scripts.core.planner import Storyboard, StoryPage
from scripts.core import article as article_mod


def main():
    if len(sys.argv) < 3:
        print("Usage: python render_only.py <job_id> <template_id>")
        print("Example: python render_only.py kc_1789723858 c")
        return 1

    job_id = sys.argv[1]
    template_id = sys.argv[2]

    cfg = get_config()
    work_dir = cfg.data_dir / job_id
    sb_path = work_dir / "storyboard.json"

    if not sb_path.exists():
        print(f"NOT FOUND: {sb_path}")
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

    # Load image paths
    pages_dir = work_dir / "pages"
    image_paths = sorted(pages_dir.glob("*.png"))
    if not image_paths:
        print(f"NO images in {pages_dir}")
        return 1

    # Render
    html = article_mod.render_publish_article(sb, [str(p) for p in image_paths], template=template_id)
    out = work_dir / f"article_{template_id}.html"
    out.write_text(html, encoding="utf-8")
    print(f"  saved: {out}  ({len(html)} chars)")
    print(f"  pages: {len(image_paths)}  template: {template_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())