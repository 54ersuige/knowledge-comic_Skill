"""Diagnose prompt length for a job's storyboard.

Usage:
    python diagnose_prompt.py [job_id]

If job_id omitted, lists all jobs and asks via print.

Checks: prompt length per page, whether scene_description would be trimmed (>9800 chars),
which pages are at risk of style drift due to scene-too-long.
"""
import json, sys, os
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
from core.prompts import build_image_prompt  # noqa: E402


def diagnose_prompt(job_id: str) -> str:
    """Return markdown table of prompt length per page."""
    data_dir = SKILL_ROOT / "data" / job_id
    sb_path = data_dir / "storyboard.json"
    if not sb_path.exists():
        raise FileNotFoundError(f"No storyboard at {sb_path}")
    sb = json.loads(sb_path.read_text(encoding="utf-8"))
    style_id = sb.get("style_id", "new_yorker")

    lines = [
        "| 页 | visual 长度 | prompt 总长 | 超 9800 字符? | 截断后保 style + 七要素 + 砍 scene? |",
        "|---|---|---|---|---|",
    ]
    for p in sb["pages"]:
        visual_len = len(p["visual"])
        full = build_image_prompt(style_id, p["visual"])
        prompt_len = len(full)
        over = prompt_len > 9800
        scene_max = max(2000, 9800 - (prompt_len - visual_len))
        will_trim = over and visual_len > scene_max
        flag = "Y (scene 被砍)" if will_trim else ("Y (刚好)" if over else "N")
        lines.append(f"| p{p['page']:02d} | {visual_len} | {prompt_len} | {flag} | {'warn: 戴敦邦派术语可能被砍' if will_trim else 'ok'} |")
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
    print(diagnose_prompt(job_id))