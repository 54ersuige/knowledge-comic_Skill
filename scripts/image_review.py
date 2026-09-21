"""图片审阅工具（轻量 v0.2）。

v0.2 重构（2026-09-20）：
  - 去掉 stdin input() 交互
  - 改成纯 JSON 读写工具 + Mavis 用 ask_user 拍板
  - 保留 3 个命令：
      python image_review.py list <job_id>          # 列出所有图片 + size
      python image_review.py rerender <job_id> <page|all>  # 标记重画
      python image_review.py clear <job_id>         # 清空重画列表

Mavis 对话里推荐直接用：
    from scripts.image_review import list_images, mark_rerender
    images = list_images(job_id)
    # → Mavis 用 deliver-assets 展示 + ask_user 拍板
    mark_rerender(job_id, [3, 5])  # 重画第 3、5 页
    # → run.py step_gen_images(regenerate_pages=[3, 5])
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core.config import get_config  # noqa: E402


RERENDER_FILE = "rerender.json"


def list_images(job_id: str, data_dir: Path | None = None) -> list[dict]:
    """列出所有 PNG + 元数据。"""
    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    pages_dir = work_root / job_id / "pages"
    if not pages_dir.exists():
        return []

    sb_path = work_root / job_id / "storyboard.json"
    captions = {}
    if sb_path.exists():
        raw = json.loads(sb_path.read_text(encoding="utf-8"))
        captions = {p["page"]: p.get("caption", "") for p in raw.get("pages", [])}

    results = []
    for p in sorted(pages_dir.glob("*.png")):
        try:
            page_no = int(p.stem.split("-")[0])
        except (ValueError, IndexError):
            page_no = 0
        results.append({
            "page": page_no,
            "path": str(p),
            "size_kb": p.stat().st_size // 1024,
            "caption": captions.get(page_no, ""),
        })
    return results


def get_rerender_list(job_id: str, data_dir: Path | None = None) -> list[int]:
    """读 rerender.json,返回待重画页码列表。"""
    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    p = work_root / job_id / RERENDER_FILE
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def mark_rerender(
    job_id: str,
    pages: list[int],
    data_dir: Path | None = None,
) -> list[int]:
    """标记要重画的页码。返回最新重画列表。"""
    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    work_dir = work_root / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    rerender_path = work_dir / RERENDER_FILE

    existing = get_rerender_list(job_id, data_dir)
    merged = sorted(set(existing + pages))

    rerender_path.write_text(
        json.dumps(merged, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[rerender] {merged}")
    return merged


def clear_rerender(job_id: str, data_dir: Path | None = None) -> None:
    """清空重画列表。"""
    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    p = work_root / job_id / RERENDER_FILE
    if p.exists():
        p.unlink()
    print(f"[rerender] cleared")


def render_summary_for_user(job_id: str, data_dir: Path | None = None) -> str:
    """生成给用户看的图片清单（Markdown）。"""
    images = list_images(job_id, data_dir)
    if not images:
        return f"(no images yet for {job_id})"

    lines = [
        f"## 图片清单 · `{job_id}`",
        "",
        "| # | size | caption | path |",
        "|---|------|---------|------|",
    ]
    for img in images:
        cap = (img["caption"] or "")[:30]
        lines.append(f"| {img['page']} | {img['size_kb']} KB | {cap} | `{img['path']}` |")
    return "\n".join(lines)


def _cli_main() -> int:
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python image_review.py list <job_id>")
        print("  python image_review.py rerender <job_id> <page|all>")
        print("  python image_review.py clear <job_id>")
        return 1

    cmd = sys.argv[1]
    if cmd == "list":
        if len(sys.argv) < 3:
            print("Usage: python image_review.py list <job_id>")
            return 1
        images = list_images(sys.argv[2])
        for img in images:
            print(f"  p{img['page']:02d}  {img['size_kb']:>4} KB  {img['caption'][:40]}  {img['path']}")
        return 0

    if cmd == "rerender":
        if len(sys.argv) < 4:
            print("Usage: python image_review.py rerender <job_id> <page|all>")
            return 1
        job_id = sys.argv[2]
        arg = sys.argv[3]
        if arg == "all":
            images = list_images(job_id)
            pages = [img["page"] for img in images]
        else:
            pages = [int(arg)]
        mark_rerender(job_id, pages)
        return 0

    if cmd == "clear":
        if len(sys.argv) < 3:
            print("Usage: python image_review.py clear <job_id>")
            return 1
        clear_rerender(sys.argv[2])
        return 0

    print(f"Unknown command: {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(_cli_main())