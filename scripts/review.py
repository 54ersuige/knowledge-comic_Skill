"""分镜审阅工具（轻量 v0.2）。

v0.2 重构（2026-09-20）：
  - 去掉 stdin input() 交互（Mavis 对话接不到，子进程直接 EOFError）
  - 改成纯 JSON 读写工具 + Mavis 用 ask_user 拍板
  - 保留 3 个命令：
      python review.py dump <job_id>           # 导出 storyboard 摘要（json 格式）
      python review.py set <job_id> <page> <field> <value>  # 改某页某字段
      python review.py reset <job_id>           # 重置 storyboard.json 为原始

Mavis 对话里推荐直接用：
    from scripts.run import step_plan
    from scripts.review import dump_storyboard, set_page_field
    sb, job_id, work_dir = step_plan(topic, bullets, ...)
    print(dump_storyboard(job_id))  # 给用户看
    # 用户拍板后：
    set_page_field(job_id, page=2, field="caption", value="新 caption")
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core.config import get_config  # noqa: E402

VALID_FIELDS = ("highlight", "caption", "visual", "body", "dialogue", "narration")


def dump_storyboard(job_id: str, data_dir: Path | None = None) -> dict:
    """读 storyboard.json,返回 dict（含 title/subtitle/pages 等）。"""
    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    sb_path = work_root / job_id / "storyboard.json"
    if not sb_path.exists():
        raise FileNotFoundError(f"storyboard.json not found: {sb_path}")
    return json.loads(sb_path.read_text(encoding="utf-8"))


def set_page_field(
    job_id: str,
    page: int,
    field: str,
    value: str,
    data_dir: Path | None = None,
) -> bool:
    """改 storyboard.json 第 N 页某字段。返回是否成功。"""
    if field not in VALID_FIELDS:
        raise ValueError(f"Invalid field: {field}, must be one of {VALID_FIELDS}")

    cfg = get_config()
    work_root = data_dir or cfg.data_dir
    sb_path = work_root / job_id / "storyboard.json"
    if not sb_path.exists():
        raise FileNotFoundError(f"storyboard.json not found: {sb_path}")

    raw = json.loads(sb_path.read_text(encoding="utf-8"))
    target_page = None
    for p in raw["pages"]:
        if p["page"] == page:
            target_page = p
            break
    if target_page is None:
        raise ValueError(f"Page {page} not found")

    old = target_page.get(field, "") or ""
    target_page[field] = value
    sb_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[set] p{page}.{field}: {old[:60]!r} -> {value[:60]!r}")
    return True


def render_summary_for_user(job_id: str, data_dir: Path | None = None) -> str:
    """生成给用户看的可读 storyboard 摘要（Markdown 表格）。"""
    raw = dump_storyboard(job_id, data_dir)
    lines = [
        f"## Storyboard · `{job_id}`",
        f"- Title: **{raw.get('title', '?')}**",
        f"- Style: `{raw.get('style_id', '?')}`",
        f"- Template 推荐: `{raw.get('recommended_template', '?')}`",
        f"- Pages: {len(raw['pages'])}",
        "",
        "| # | highlight | caption | visual (前 80 字) |",
        "|---|-----------|---------|---------------------|",
    ]
    for p in raw["pages"]:
        highlight = p.get("highlight", "")
        caption = p.get("caption", "")
        visual = (p.get("visual", "") or "")[:80]
        lines.append(f"| {p['page']} | {highlight} | {caption} | {visual}… |")
    return "\n".join(lines)


def _cli_main() -> int:
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python review.py dump <job_id>")
        print("  python review.py set <job_id> <page> <field> <value>")
        print("  python review.py summary <job_id>")
        return 1

    cmd = sys.argv[1]
    if cmd == "dump":
        if len(sys.argv) < 3:
            print("Usage: python review.py dump <job_id>")
            return 1
        raw = dump_storyboard(sys.argv[2])
        print(json.dumps(raw, ensure_ascii=False, indent=2))
        return 0

    if cmd == "set":
        if len(sys.argv) < 6:
            print("Usage: python review.py set <job_id> <page> <field> <value>")
            return 1
        job_id = sys.argv[2]
        page = int(sys.argv[3])
        field = sys.argv[4]
        value = sys.argv[5]
        set_page_field(job_id, page, field, value)
        return 0

    if cmd == "summary":
        if len(sys.argv) < 3:
            print("Usage: python review.py summary <job_id>")
            return 1
        print(render_summary_for_user(sys.argv[2]))
        return 0

    print(f"Unknown command: {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(_cli_main())