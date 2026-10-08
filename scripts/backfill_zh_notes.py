# -*- coding: utf-8 -*-
"""给已有 storyboard 补中文速记（v0.3.7）。

背景：
    v0.3.7 让 planner prompt 要求每段写 `// 中文速记`，但**已生成的
    storyboard 里没有**（prompt 改动只对新跑生效）。这些老数据在
    layout_preview 里会显示成英文 + 截断，用户看不懂。

    本脚本为指定 job（或全部 job）的每页 visual 补 `// 中文速记`。
    优先用词表翻译（抽取而非翻译，译不出就留英文），写回 storyboard.json。

用法：
    python scripts/backfill_zh_notes.py <job_id> [<job_id> ...]
    python scripts/backfill_zh_notes.py --all     # 扫 data/ 下所有 job
    python scripts/backfill_zh_notes.py --dry-run <job_id>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core.story_script import _seg  # noqa: E402

# 复用 story_script 的切分逻辑 —— 两处逻辑必须一致，
# 否则抽取和注入会对不上（v0.3.7 踩过：backfill 用自己的正则切，
# story_script 用另一套，导致 // 插错位置、整段被吞）。
from scripts.core.story_script import _split_segments  # noqa: E402

_ORDER = ("subject", "action", "secondary", "background", "camera", "mood")


def backfill_visual(visual: str) -> str:
    """逐段补 `// 中文速记`。已有速记的段跳过。

    插点规则：插在**该段末尾的收尾标点之后**（含标点），
    下一段标签之前。插在标点前会把 "SECONDARY: ..." 吞进速记。
    """
    if not visual:
        return visual

    segs = _split_segments(visual)
    if not segs:
        return visual

    out = visual
    # 从后往前插，避免偏移量失效
    # _split_segments 返回的内容起点 = 标签结束位置
    pos = 0
    spans: list[tuple[int, int, str]] = []   # (start, end, key)
    for key, content in segs:
        start = visual.find(content[:40], pos) if content else pos
        if start < 0:
            start = pos
        end = start + len(content)
        spans.append((start, end, key))
        pos = end

    for start, end, key in reversed(spans):
        if key not in _ORDER:
            continue
        content = visual[start:end]
        if "//" in content:
            continue
        note = _seg(visual, key)
        if not note:
            continue
        trimmed = content.rstrip()
        m_end = re.search(r"[.;。；]\s*$", trimmed)
        at = start + (m_end.end() if m_end else len(trimmed))
        out = out[:at] + f"  // {note}" + out[at:]
    return out


def process_job(job_dir: Path, dry_run: bool = False) -> tuple[int, int]:
    sb_path = job_dir / "storyboard.json"
    if not sb_path.exists():
        return 0, 0
    raw = json.loads(sb_path.read_text(encoding="utf-8"))
    changed = 0
    for p in raw.get("pages", []):
        old = p.get("visual", "")
        new = backfill_visual(old)
        if new != old:
            changed += 1
            p["visual"] = new
    if changed and not dry_run:
        sb_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed, len(raw.get("pages", []))


def main() -> int:
    args = [a for a in sys.argv[1:]]
    dry = "--dry-run" in args
    args = [a for a in args if not a.startswith("--")]
    data_dir = SKILL_ROOT / "data"

    if "--all" in sys.argv or not args:
        jobs = sorted(d for d in data_dir.iterdir()
                      if d.is_dir() and (d / "storyboard.json").exists())
    else:
        jobs = [data_dir / a for a in args]

    total_changed = 0
    for j in jobs:
        if not j.exists():
            print(f"  跳过 {j.name}（不存在）")
            continue
        c, n = process_job(j, dry_run=dry)
        if c:
            total_changed += c
            tag = "DRY" if dry else "已写入"
            print(f"  {tag} {j.name}: {c}/{n} 页补上中文速记")

    print()
    print(f"共 {len(jobs)} 个 job, 改动 {total_changed} 页"
          + ("（dry-run，未写盘）" if dry else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
